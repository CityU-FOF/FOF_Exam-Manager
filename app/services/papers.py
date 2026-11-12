"""Exam document settings and physical printing quantities; no student notes exported."""
import hashlib
import json
import math
import re
from pathlib import Path
from app.models.records import ValidationError
from app.models.programmes import FACULTY

LANGUAGES={'cn':'中文卷','en':'英文卷'}


def default_settings():
    return dict(approval='pending',book='pending',sender='',submission_date='',
                sheets_per_ream=500,reams_per_box=5,
                cn=dict(pages=0,formula='pending',formula_pages=0,formula_sides='pending',formula_copies=0,formula_cover='pending'),
                en=dict(pages=0,formula='pending',formula_pages=0,formula_sides='pending',formula_copies=0,formula_cover='pending'))


def language_for_class(name):
    return 'en' if re.fullmatch(r'\d*A',name.strip().upper()) else 'cn'


def print_quantities(groups,settings):
    """Count one spare per teaching class, once even if split across rooms."""
    result=[]
    for language in LANGUAGES:
        selected=[g for g in groups if g['language']==language and g['students']>0]
        if not selected:continue
        config=settings[language];pages=int(config['pages'])
        if pages<=0:raise ValidationError(LANGUAGES[language]+'：請填試卷內容頁數（不含封面）。')
        n=sum(g['students'] for g in selected);spares=len(selected);copies=n+spares
        sheets=math.ceil(pages/2)+1
        mode=config['formula'];extra=0
        if mode not in ('none','included','separate'):
            raise ValidationError(LANGUAGES[language]+'：請選擇公式表是否已包括或獨立印刷。')
        if mode=='separate':
            fp=int(config['formula_pages']);fc=int(config['formula_copies'])
            if fp<=0 or fc<=0 or config['formula_sides'] not in ('single','double') or config['formula_cover'] not in ('none','single'):
                raise ValidationError(LANGUAGES[language]+'：獨立公式表須填頁數、實際份數、單雙面及是否另有封面。')
            extra=fc*((fp if config['formula_sides']=='single' else math.ceil(fp/2))+(config['formula_cover']=='single'))
        result.append(dict(language=language,label=LANGUAGES[language],students=n,classes=spares,spares=spares,
                           copies=copies,pages=pages,cover_pages=1,sheets_per_copy=sheets,paper_sheets=copies*sheets,
                           formula_sheets=extra,total_sheets=copies*sheets+extra))
    total=sum(r['total_sheets'] for r in result)
    ream=int(settings['sheets_per_ream']);box=int(settings['reams_per_box'])
    if ream<=0 or box<=0:raise ValidationError('每令張數及每箱令數須大於零。')
    return dict(rows=result,total_sheets=total,reams=math.ceil(total/ream),boxes=math.ceil(total/(ream*box)),
                full_reams=total//ream,loose_sheets=total%ream,sheets_per_ream=ream,reams_per_box=box)


class PaperManager:
    def __init__(self,manager):self.manager=manager;self.db=manager.db

    def settings(self,sid):
        result=default_settings();stored=self.db.one('SELECT settings_json FROM paper_settings WHERE session_id=?',(sid,))
        if stored:
            saved=json.loads(stored['settings_json'])
            for key,value in saved.items():
                if key in LANGUAGES:result[key].update(value)
                elif key in result:result[key]=value
        return result

    def save(self,sid,settings):
        if not self.db.one('SELECT id FROM sessions WHERE id=?',(sid,)):raise ValidationError('請先建立場次。')
        with self.db.conn:self.db.conn.execute('''INSERT INTO paper_settings VALUES(?,?)
            ON CONFLICT(session_id) DO UPDATE SET settings_json=excluded.settings_json''',(sid,json.dumps(settings,ensure_ascii=False)))

    def put_cover(self,sid,language,path):
        if language not in LANGUAGES:raise ValidationError('卷別不正確。')
        path=Path(path);data=path.read_bytes()
        if path.suffix.lower()!='.pdf' or not data.startswith(b'%PDF-'):raise ValidationError('請選擇已審批的 PDF 封面。')
        digest=hashlib.sha256(data).hexdigest()
        with self.db.conn:self.db.conn.execute('''INSERT INTO paper_covers VALUES(?,?,?,?,?) ON CONFLICT(session_id,language)
            DO UPDATE SET original_name=excluded.original_name,sha256=excluded.sha256,pdf=excluded.pdf''',(sid,language,path.name,digest,data))

    def covers(self,sid):
        return {r['language']:r for r in self.db.rows('SELECT language,original_name,sha256 FROM paper_covers WHERE session_id=?',(sid,))}

    def cover_bytes(self,sid,language):
        row=self.db.one('SELECT * FROM paper_covers WHERE session_id=? AND language=?',(sid,language))
        if not row:raise ValidationError(LANGUAGES[language]+'：尚未匯入已審批封面 PDF。')
        data=bytes(row['pdf'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValidationError('已審批封面檔案校驗失敗。')
        return data

    def context(self,sid):
        info=self.db.one('''SELECT se.*,e.batch_id,co.code,co.name_cn,co.name_en,co.programme,co.programme_en,
            b.academic_year,b.semester,b.exam_type FROM sessions se JOIN exams e ON e.id=se.exam_id
            JOIN courses co ON co.id=e.course_id JOIN batches b ON b.id=e.batch_id WHERE se.id=?''',(sid,))
        if not info:raise ValidationError('請先選擇場次。')
        info['faculty']=FACULTY
        participants=self.manager.participants(sid);groups={}
        for row in participants:
            key=row['class_id']
            if key not in groups:groups[key]=dict(name=row['class_name'],language=language_for_class(row['class_name']),students=0)
            groups[key]['students']+=1
        by_room={}
        for row in self.manager.assigned(sid):
            classes=by_room.setdefault(row['allocation_id'],{})
            group=classes.setdefault(row['class_name'],dict(count=0,ids=set()))
            group['count']+=1;group['ids'].add(row['class_id'])
        rooms=[];spare_holders=set()
        for allocation in self.manager.allocations(sid):
            classes=by_room.get(allocation['id'],{})
            details=[]
            for name in sorted(classes,key=str.casefold):
                group=classes[name];spares=len(group['ids']-spare_holders)
                spare_holders.update(group['ids'])
                details.append(dict(name=name,count=group['count'],spares=spares))
            count=sum(g['count'] for g in details);spares=sum(g['spares'] for g in details)
            rooms.append(dict(name=allocation['room_name'],count=count,spares=spares,print_copies=count+spares,
                              allocation_id=allocation['id'],classes=details))
        return dict(info=info,groups=list(groups.values()),rooms=rooms,pending=len(self.manager.pending(sid)))

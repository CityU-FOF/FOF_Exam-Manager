import os
import re
import tempfile
from pathlib import Path
from openpyxl import load_workbook
from app.database.store import uid, now
from app.models.records import ValidationError
from app.templates.engine import TemplateEngine


def safe_filename(info):
    value=f'{info["code"]}_{info["name_cn"]}_{info["date"]}_{info["start"].replace(":","")}_{info["room_name"]}'
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:180]
    return value+'.xlsx'


class ExcelExporter:
    def __init__(self,manager):
        self.manager=manager
        self.engine=TemplateEngine()

    @staticmethod
    def verify(path,students):
        wb=load_workbook(path,data_only=False,keep_links=False)
        try:
            if wb.sheetnames!=['Attendance','Seat Plan']:raise ValidationError('輸出工作表不完整。')
            for sheet in wb:
                if sheet['D14'].value!=len(students):raise ValidationError('輸出考生人數錯誤。')
                for i,st in enumerate(students,18):
                    actual=[sheet.cell(i,c).value for c in [2,3,4,5 if sheet.title=='Attendance' else 6]]
                    if actual!=[st['seat'],st['student_no'],st['chinese_name'] or None,st['english_name'] or None]:
                        raise ValidationError('輸出座位或名單不一致。')
                if any(c.data_type=='f' for row in sheet for c in row):
                    raise ValidationError('輸出不可含未計算公式。')
                if any(sheet.cell(i,3).value is not None for i in range(18+len(students),sheet.max_row+1)):
                    raise ValidationError('輸出有殘留學生資料。')
        finally:wb.close()

    def generate(self,aid,folder,policy='error'):
        info,students=self.manager.export_data(aid)
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/safe_filename(info)
        if path.exists():
            if policy=='skip':return None
            if policy=='rename':
                index=2
                while path.exists():
                    path=folder/(Path(safe_filename(info)).stem+f'_{index}.xlsx');index+=1
            elif policy!='overwrite':raise FileExistsError('同名文件已存在，請選擇覆蓋、另存或跳過。')
        temp=None
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx',prefix='.fof-',dir=folder,delete=False) as f:temp=Path(f.name)
            wb=self.engine.render(info,students)
            wb.save(temp);wb.close()
            self.verify(temp,students)
            if policy=='overwrite':os.replace(temp,path)
            elif os.name=='nt':
                # Windows rename refuses existing targets and also works on FAT/exFAT.
                os.rename(temp,path)
            else:
                # Hard-link publication is atomic and never replaces a raced destination.
                os.link(temp,path)
                temp.unlink()
            with self.manager.db.conn:
                self.manager.db.conn.execute('INSERT INTO generation_logs VALUES(?,?,?,?,?,?)',(uid(),aid,now(),str(path),'成功',''))
                allocated=[a for a in self.manager.allocations(info['id']) if a['count']]
                all_generated=all(self.manager.db.one("SELECT id FROM generation_logs WHERE allocation_id=? AND status='成功' AND created>=? LIMIT 1",(a['id'],info['modified'])) for a in allocated)
                self.manager.db.conn.execute('UPDATE sessions SET status=? WHERE id=?',('已生成文件' if all_generated else '已完成編排',info['id']))
            return path
        except Exception:
            with self.manager.db.conn:
                self.manager.db.conn.execute('INSERT INTO generation_logs VALUES(?,?,?,?,?,?)',(uid(),aid,now(),str(path),'失敗','生成失敗，請檢查權限、檔案佔用或編排驗證。'))
            raise
        finally:
            if temp:temp.unlink(missing_ok=True)

    def batch(self,aids,folder,policy='error',progress=None):
        results=[]
        for i,aid in enumerate(aids):
            try:
                path=self.generate(aid,folder,policy)
                results.append((aid,'成功' if path else '跳過',str(path or '')))
            except Exception as e:
                results.append((aid,'失敗',str(e)))
            if progress:progress(i+1,len(aids),results[-1])
        return results

import json
import re
from contextlib import contextmanager
from datetime import date, time
from app.database.store import uid, now
from app.models.records import ValidationError, CapacityError


class Manager:
    def __init__(self, store):
        self.db = store
        self.name_repair_count = self.repair_combined_names()

    def repair_combined_names(self):
        """Repair recognisable combined names saved by older importers."""
        from app.importers.roster import split_name
        updates = []
        for student in self.db.rows('SELECT * FROM students'):
            cn, en, issues = split_name(student['chinese_name'])
            if issues or not en:
                continue
            if (cn, en) == (student['chinese_name'], student['english_name']):
                continue
            raw = student['raw_name'] or '\n'.join(filter(None, [student['chinese_name'], student['english_name']]))
            updates.append((cn, en, raw, student['id']))
        self.name_repair_backup = None
        if not updates:
            return 0
        # Finish the backup before changing any identities or session status.
        self.name_repair_backup = self.db.path.with_name('before_name_split_' + uid()[:12] + '.sqlite3')
        self.db.backup(self.name_repair_backup)
        with self.db.conn:
            for cn, en, raw, identifier in updates:
                self.db.conn.execute('UPDATE students SET chinese_name=?,english_name=?,raw_name=? WHERE id=?',
                                     (cn, en, raw, identifier))
                self.db.conn.execute('''UPDATE sessions SET status='草稿',modified=? WHERE id IN
                    (SELECT al.session_id FROM allocations al JOIN assignments a ON a.allocation_id=al.id
                     WHERE a.student_id=?)''', (now(), identifier))
        return len(updates)

    def courses(self):
        return self.db.rows('SELECT * FROM courses ORDER BY code')

    def rooms(self):
        return self.db.rows('SELECT * FROM rooms ORDER BY name')

    def save_courses(self, records):
        allowed={'code','name_cn','name_en','teachers','programme','programme_en','language','notes'}
        seen=set()
        for values in records:
            if not set(values)<=allowed:raise ValidationError('科目欄位不正確。')
            code=values.get('code','')
            if not re.fullmatch(r'[A-Z]{2,6}\d{3,4}',code):raise ValidationError('請核對科目編號，例如 BAE305。')
            if code in seen:raise ValidationError('科目編號重複，請刪除多餘預覽列。')
            seen.add(code)
            if not all(values.get(k,'').strip() for k in ('name_cn','name_en','teachers')):
                raise ValidationError('請補齊中英文科名及教師。')
        with self.db.conn:
            for v in records:
                old=self.db.one('SELECT id FROM courses WHERE code=?',(v['code'],))
                if old:self.db.conn.execute('UPDATE courses SET '+','.join(k+'=?' for k in v)+' WHERE id=?',(*v.values(),old['id']))
                else:self.db.conn.execute('INSERT INTO courses(id,'+','.join(v)+') VALUES('+','.join('?' for _ in range(len(v)+1))+')',(uid(),*v.values()))
                if old:self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE exam_id IN (SELECT id FROM exams WHERE course_id=?)",(now(),old['id']))

    def classes(self, course_id=None):
        sql = '''SELECT c.*,co.code,co.name_cn,COUNT(CASE WHEN e.active=1 THEN 1 END) count
                 FROM classes c JOIN courses co ON co.id=c.course_id
                 LEFT JOIN enrollments e ON e.class_id=c.id'''
        if course_id:
            sql += ' WHERE c.course_id=?'
        return self.db.rows(sql+' GROUP BY c.id ORDER BY co.code,c.name', (course_id,) if course_id else ())

    def save_course(self, values, identifier=None):
        from app.models.programmes import programme_values
        if not identifier:values=dict(programme_values(),**values)
        if not values.get('code','').strip() or not values.get('name_cn','').strip():
            raise ValidationError('請填寫科目代碼及中文名稱。')
        return self._save('courses', values, identifier)

    def save_room(self, values, identifier=None):
        self.validate_room(values,identifier)
        return self._save('rooms', values, identifier)

    def validate_room(self, values, identifier=None):
        if not values.get('name','').strip() or int(values.get('capacity',0)) <= 0:
            raise ValidationError('請填寫考場名稱及正整數容量。')
        self.seat_pool(values)
        if identifier:
            count = self.db.one('''SELECT MAX(n) n FROM (SELECT COUNT(*) n FROM assignments a
               JOIN allocations al ON al.id=a.allocation_id WHERE al.room_id=? GROUP BY al.id)''',(identifier,))['n'] or 0
            if count > min(int(values['capacity']),len(self.seat_pool(values))):
                raise ValidationError('新容量或可用座位不足以保留現有編排。')
            for al in [a for a in self.allocations() if a['room_id']==identifier]:
                combined=al['count']
                for other in self.overlap_sessions(al['session_id']):
                    combined+=sum(a['count'] for a in self.allocations(other['id']) if a['room_id']==identifier)
                if combined>min(int(values['capacity']),len(self.seat_pool(values))):
                    raise ValidationError('新容量不足以保留現有合場編排。')
            used = self.db.rows('SELECT a.seat FROM assignments a JOIN allocations al ON al.id=a.allocation_id WHERE al.room_id=?',(identifier,))
            if any(x['seat'] not in self.seat_pool(values) for x in used):
                raise ValidationError('有已使用座位被移除，請先調整編排。')

    def save_rooms(self, records):
        prepared=[];seen=set()
        for row in records:
            name=str(row['name']).strip().upper()
            capacity=str(row['capacity']).strip()
            if not capacity.isascii() or not capacity.isdigit():raise ValidationError('最多人數須為正整數。')
            if name in seen:raise ValidationError('同一考場只能保留一列，請核對重複容量。')
            seen.add(name)
            old=self.db.one('SELECT * FROM rooms WHERE UPPER(name)=?',(name,))
            values=dict(name=name,capacity=int(capacity),usable_seats='')
            self.validate_room(values,old['id'] if old else None)
            prepared.append((old,values))
        with self.db.conn:
            for old,v in prepared:
                if old:
                    self.db.conn.execute('UPDATE rooms SET capacity=?,usable_seats=? WHERE id=?',(v['capacity'],'',old['id']))
                    self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id IN (SELECT session_id FROM allocations WHERE room_id=?)",(now(),old['id']))
                else:self.db.conn.execute('INSERT INTO rooms(id,name,capacity,enabled) VALUES(?,?,?,1)',(uid(),v['name'],v['capacity']))

    def delete_enrollments(self, identifiers):
        identifiers=set(identifiers)
        records=[r for r in self.db.rows('SELECT * FROM enrollments') if r['id'] in identifiers]
        if len(records)!=len(identifiers):raise ValidationError('名單已變更，請重新選取。')
        if not records:return
        self.db.backup(self.db.path.with_name('before_roster_delete_'+uid()[:12]+'.sqlite3'))
        classes={r['class_id'] for r in records}
        sessions={r['session_id'] for r in self.db.rows('SELECT * FROM session_classes') if r['class_id'] in classes}
        affected={r['allocation_id'] for r in self.assigned() if r['enrollment_id'] in identifiers}
        with self.db.conn:
            for identifier in identifiers:
                self.db.conn.execute('DELETE FROM assignments WHERE enrollment_id=?',(identifier,))
                self.db.conn.execute('DELETE FROM enrollments WHERE id=?',(identifier,))
            for aid in affected:self.renumber(aid)
            for cid in classes:
                if not self.db.one('SELECT id FROM enrollments WHERE class_id=?',(cid,)):
                    self.db.conn.execute('DELETE FROM session_classes WHERE class_id=?',(cid,))
                    self.db.conn.execute('DELETE FROM classes WHERE id=?',(cid,))
            for record in records:
                if (not self.db.one('SELECT id FROM enrollments WHERE student_id=?',(record['student_id'],))
                        and not self.db.one('SELECT student_id FROM student_flags WHERE student_id=?',(record['student_id'],))):
                    self.db.conn.execute('DELETE FROM students WHERE id=?',(record['student_id'],))
            for sid in sessions:
                self.db.conn.execute('DELETE FROM history WHERE session_id=?',(sid,))
                self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id=?",(now(),sid))

    def delete_allocations(self, identifiers):
        identifiers=set(identifiers)
        rows=[r for r in self.allocations() if r['id'] in identifiers]
        if len(rows)!=len(identifiers):raise ValidationError('考場項目已變更，請重新選取。')
        if not rows:return
        self.db.backup(self.db.path.with_name('before_allocation_delete_'+uid()[:12]+'.sqlite3'))
        with self.db.conn:
            for identifier in identifiers:self.db.conn.execute('DELETE FROM allocations WHERE id=?',(identifier,))
            for sid in {r['session_id'] for r in rows}:
                self.db.conn.execute('DELETE FROM history WHERE session_id=?',(sid,))
                self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id=?",(now(),sid))

    def save_batch(self, values, identifier=None):
        from app.models.programmes import FACULTY,programme_values
        values=dict(values)
        if not all(str(values.get(k,'')).strip() for k in ['academic_year','semester','exam_type']):
            raise ValidationError('請選擇學年、學期及期中／期末考試。')
        values['name']=f'{values["academic_year"]}學年{values["semester"]}{values["exam_type"]}考試'
        values['programme']=FACULTY+' / '+programme_values()['programme']
        if not identifier:
            values = dict(values, created=now())
        return self._save('batches', values, identifier)

    def _save(self, table, values, identifier=None):
        allowed = {
            'courses': {'code','name_cn','name_en','teachers','programme','programme_en','language','notes'},
            'rooms': {'name','capacity','usable_seats','notes','enabled'},
            'batches': {'name','academic_year','semester','exam_type','programme','notes','created'},
        }
        if table not in allowed or not set(values) <= allowed[table]:
            raise ValidationError('不支援的資料欄位。')
        identifier_new = identifier or uid()
        with self.db.conn:
            if identifier:
                self.db.conn.execute(f'UPDATE {table} SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', (*values.values(),identifier))
            else:
                self.db.conn.execute(f'INSERT INTO {table}(id,'+','.join(values)+') VALUES('+','.join('?' for _ in range(len(values)+1))+')',(identifier_new,*values.values()))
            if identifier:
                if table=='courses':
                    self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE exam_id IN (SELECT id FROM exams WHERE course_id=?)",(now(),identifier))
                elif table=='batches':
                    self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE exam_id IN (SELECT id FROM exams WHERE batch_id=?)",(now(),identifier))
                elif table=='rooms':
                    self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id IN (SELECT session_id FROM allocations WHERE room_id=?)",(now(),identifier))
        return identifier_new

    def delete_course(self, identifier):
        if self.db.one('SELECT id FROM classes WHERE course_id=?',(identifier,)) or self.db.one('SELECT id FROM exams WHERE course_id=?',(identifier,)):
            raise ValidationError('此科目已有班級或考試，不能刪除。')
        with self.db.conn:
            self.db.conn.execute('DELETE FROM courses WHERE id=?',(identifier,))

    def students(self, search='', course_id=None, class_id=None):
        sql = '''SELECT s.*,e.id enrollment_id,e.source,e.active,e.position,e.administrative_class,c.name class_name,c.id class_id,
        c.teaching_code,c.academic_year,c.semester,
        co.id course_id,co.code course_code,co.name_cn course_name,COALESCE(f.reason,'') flag_reason FROM students s
        JOIN enrollments e ON e.student_id=s.id JOIN classes c ON c.id=e.class_id JOIN courses co ON co.id=c.course_id
        LEFT JOIN student_flags f ON f.student_id=s.id
        WHERE e.active=1'''
        args=[]
        if search:
            sql += ' AND (s.student_no LIKE ? OR s.chinese_name LIKE ? OR s.english_name LIKE ?)'
            args += ['%'+search+'%']*3
        if course_id:
            sql += ' AND co.id=?'; args.append(course_id)
        if class_id:
            sql += ' AND c.id=?'; args.append(class_id)
        return self.db.rows(sql+' ORDER BY co.code,c.name,e.position',args)

    def set_student_flag(self,student_id,reason='',enabled=True):
        if not self.db.one('SELECT id FROM students WHERE id=?',(student_id,)):
            raise ValidationError('學生不存在，請重新選取。')
        reason=str(reason).strip()
        if enabled and not reason:raise ValidationError('請填寫特殊學生標記的原因。')
        with self.db.conn:
            if enabled:
                self.db.conn.execute('''INSERT INTO student_flags(student_id,reason,updated) VALUES(?,?,?)
                    ON CONFLICT(student_id) DO UPDATE SET reason=excluded.reason,updated=excluded.updated''',(student_id,reason,now()))
            else:self.db.conn.execute('DELETE FROM student_flags WHERE student_id=?',(student_id,))

    def flagged_students(self):
        return self.db.rows('''SELECT s.*,f.reason flag_reason,f.updated FROM student_flags f
            JOIN students s ON s.id=f.student_id ORDER BY s.student_no''')

    def flagged_in_allocations(self,identifiers):
        identifiers=list(dict.fromkeys(identifiers))
        if not identifiers:return []
        return self.db.rows('''SELECT a.id assignment_id,a.student_id,a.seat,al.id allocation_id,al.session_id,
            r.name room_name,co.code,co.name_cn,s.student_no,s.chinese_name,s.english_name,f.reason flag_reason
            FROM assignments a JOIN student_flags f ON f.student_id=a.student_id
            JOIN students s ON s.id=a.student_id JOIN allocations al ON al.id=a.allocation_id
            JOIN rooms r ON r.id=al.room_id JOIN sessions se ON se.id=al.session_id
            JOIN exams e ON e.id=se.exam_id JOIN courses co ON co.id=e.course_id
            WHERE al.id IN ('''+','.join('?' for _ in identifiers)+') ORDER BY co.code,r.name,a.position',identifiers)

    @staticmethod
    def check_student(record):
        from app.models.programmes import parse_teaching_code
        if record.teaching_code:
            teaching=parse_teaching_code(record.teaching_code,record.course_code)
            if not teaching or teaching.class_name!=record.class_name:
                raise ValidationError('科目編號或授課班與完整科目代碼不符，請核對。')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',record.student_no or ''):
            raise ValidationError('空白或錯誤學號。')
        if not (record.chinese_name or record.english_name):
            raise ValidationError('學生姓名不可為空。')
        if not record.course_code or not record.class_name:
            raise ValidationError('請填寫科目代碼及班級。')
        if record.issues:
            raise ValidationError('請先在預覽處理資料問題：'+ '；'.join(record.issues))

    def _legacy_can_adopt(self, class_id, record):
        batches=self.db.rows('''SELECT b.academic_year,b.semester FROM session_classes sc
            JOIN sessions s ON s.id=sc.session_id JOIN exams e ON e.id=s.exam_id
            JOIN batches b ON b.id=e.batch_id WHERE sc.class_id=?''',(class_id,))
        normalized=lambda v:re.sub('[-–—/]','',v)
        return all(normalized(b['academic_year'])==normalized(record.academic_year) and b['semester']==record.semester for b in batches)

    def _class_for_record(self, record):
        co=self.db.one('SELECT id FROM courses WHERE code=?',(record.course_code,))
        if not co:return None
        cl=self.db.one('SELECT * FROM classes WHERE course_id=? AND name=? AND teaching_code=?',
                       (co['id'],record.class_name,record.teaching_code))
        if cl or not record.teaching_code:return cl
        # Adopt an old administrative partition only when it has no teaching code.
        legacy=re.fullmatch(r'\d+([A-Z]+)',record.class_name)
        if legacy:
            candidate=self.db.one("SELECT * FROM classes WHERE course_id=? AND name=? AND teaching_code=''",(co['id'],legacy[1]))
            if candidate and self._legacy_can_adopt(candidate['id'],record):return candidate
        return None

    def _enrollment_for_record(self, record):
        cl=self._class_for_record(record)
        candidates=self.db.rows('''SELECT e.*,c.name old_class FROM enrollments e
            JOIN students s ON s.id=e.student_id JOIN classes c ON c.id=e.class_id
            JOIN courses co ON co.id=c.course_id WHERE co.code=? AND s.student_no=?
            AND (c.id=? OR (?<>'' AND e.teaching_code='' AND e.source=?))
            ORDER BY CASE WHEN c.id=? THEN 0 ELSE 1 END''',
            (record.course_code,record.student_no,cl['id'] if cl else '',record.teaching_code,record.source,cl['id'] if cl else ''))
        return next((e for e in candidates if (cl and e['class_id']==cl['id']) or self._legacy_can_adopt(e['class_id'],record)),None)

    def import_diff(self, records):
        grouped={};seen=set();identities={};memberships={}
        diff={'added':[], 'removed':[], 'changed':[], 'unchanged':[]}
        for r in records:
            self.check_student(r)
            name=(r.chinese_name,r.english_name)
            if r.student_no in identities and identities[r.student_no]!=name:
                raise ValidationError('同一學號在所選名單中的姓名不一致，請先人工核對。')
            identities[r.student_no]=name
            key=(r.course_code,r.class_name,r.teaching_code,r.student_no)
            if key in seen:raise ValidationError('所選名單重複，請勿重複選取同一科目授課班。')
            seen.add(key)
            member=(r.course_code,r.academic_year,r.semester,r.student_no)
            if member in memberships and memberships[member]!=r.class_name:
                raise ValidationError('同科目同學期學生出現在兩個授課班，請人工確認修讀關係。')
            memberships[member]=r.class_name
            grouped.setdefault((r.course_code,r.class_name,r.teaching_code),[]).append(r)
            old=self.db.one('SELECT * FROM students WHERE student_no=?',(r.student_no,))
            enrollment=self._enrollment_for_record(r)
            if not enrollment or not enrollment['active']:diff['added'].append(r)
            elif (old['chinese_name'],old['english_name'])!=name:diff['changed'].append(r)
            else:diff['unchanged'].append(r)
        for rr in grouped.values():
            r=rr[0];cl=self._class_for_record(r);wanted={x.student_no for x in rr}
            old=self.db.rows('''SELECT s.*,e.id enrollment_id,e.class_id FROM enrollments e JOIN students s ON s.id=e.student_id
                JOIN classes c ON c.id=e.class_id JOIN courses co ON co.id=c.course_id
                WHERE co.code=? AND e.active=1 AND (c.id=? OR (?<>'' AND e.teaching_code='' AND e.source=?))''',
                (r.course_code,cl['id'] if cl else '',r.teaching_code,r.source))
            diff['removed'] += [o for o in old if o['student_no'] not in wanted and ((cl and o['class_id']==cl['id']) or self._legacy_can_adopt(o['class_id'],r))]
        return diff

    def import_records(self, records, remove_missing=False):
        from app.models.programmes import programme_values,PROGRAMMES
        diff=self.import_diff(records)
        with self.db.conn:
            for index,r in enumerate(records):
                co=self.db.one('SELECT id FROM courses WHERE code=?',(r.course_code,))
                if not co:
                    co={'id':uid()};defaults=programme_values(r.programme_code if r.programme_code in PROGRAMMES else 'BAECF')
                    self.db.conn.execute('INSERT INTO courses(id,code,name_cn,teachers,programme,programme_en) VALUES(?,?,?,?,?,?)',
                        (co['id'],r.course_code,r.course_name or r.course_code,r.teachers,r.programme or defaults['programme'],defaults['programme_en']))
                cl=self._class_for_record(r)
                if not cl:
                    cl={'id':uid()}
                    self.db.conn.execute('INSERT INTO classes(id,course_id,name,teaching_code,academic_year,semester,programme_code,grade) VALUES(?,?,?,?,?,?,?,?)',
                        (cl['id'],co['id'],r.class_name,r.teaching_code,r.academic_year,r.semester,r.programme_code,r.grade))
                elif r.teaching_code and not cl['teaching_code']:
                    self.db.conn.execute('UPDATE classes SET name=?,teaching_code=?,academic_year=?,semester=?,programme_code=?,grade=? WHERE id=?',
                        (r.class_name,r.teaching_code,r.academic_year,r.semester,r.programme_code,r.grade,cl['id']))
                enrollment=self._enrollment_for_record(r)
                other=self.db.one('''SELECT c.name FROM enrollments e JOIN classes c ON c.id=e.class_id
                     JOIN students s ON s.id=e.student_id WHERE c.course_id=? AND c.id<>? AND s.student_no=? AND e.active=1
                     AND c.academic_year=? AND c.semester=? AND e.id<>?''',
                     (co['id'],cl['id'],r.student_no,r.academic_year,r.semester,enrollment['id'] if enrollment else ''))
                if other:raise ValidationError(f'此學生已在同科目同學期的 {other["name"]} 班，請先確認修讀關係。')
                st=self.db.one('SELECT id FROM students WHERE student_no=?',(r.student_no,))
                if not st:
                    st={'id':uid()}
                    self.db.conn.execute('INSERT INTO students VALUES(?,?,?,?,?)',(st['id'],r.student_no,r.chinese_name,r.english_name,r.raw_name))
                else:
                    self.db.conn.execute('UPDATE students SET chinese_name=?,english_name=?,raw_name=? WHERE id=?',(r.chinese_name,r.english_name,r.raw_name,st['id']))
                if enrollment:
                    # Move the existing membership ID, so seats and undo history survive.
                    self.db.conn.execute('UPDATE enrollments SET class_id=?,active=1,source=?,position=?,administrative_class=?,teaching_code=? WHERE id=?',
                        (cl['id'],r.source,index,r.administrative_class,r.teaching_code,enrollment['id']))
                    if enrollment['class_id']!=cl['id']:
                        sessions=self.db.rows('''SELECT DISTINCT al.session_id FROM assignments a JOIN allocations al ON al.id=a.allocation_id
                             WHERE a.enrollment_id=?''',(enrollment['id'],))
                        for session in sessions:self.db.conn.execute('INSERT OR IGNORE INTO session_classes VALUES(?,?)',(session['session_id'],cl['id']))
                else:
                    self.db.conn.execute('INSERT INTO enrollments(id,student_id,class_id,source,position,administrative_class,teaching_code) VALUES(?,?,?,?,?,?,?)',
                        (uid(),st['id'],cl['id'],r.source,index,r.administrative_class,r.teaching_code))
            if remove_missing:
                for old in diff['removed']:self.db.conn.execute('UPDATE enrollments SET active=0 WHERE id=?',(old['enrollment_id'],))
            self.db.conn.execute('INSERT INTO import_logs VALUES(?,?,?,?)',
                (uid(),'; '.join(sorted({r.source for r in records})),now(),json.dumps({k:len(v) for k,v in diff.items()})))
            self.db.conn.execute("UPDATE sessions SET status='草稿',modified=?",(now(),))
        return diff

    def edit_student(self, identifier, no, cn, en):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',no) or not (cn or en):
            raise ValidationError('請填寫正確的學號及姓名。')
        with self.db.conn:
            self.db.conn.execute('UPDATE students SET student_no=?,chinese_name=?,english_name=? WHERE id=?',(no,cn,en,identifier))
            self.db.conn.execute("UPDATE sessions SET status='草稿',modified=?",(now(),))

    def deactivate_enrollment(self, enrollment_id):
        with self.db.conn:
            self.db.conn.execute('UPDATE enrollments SET active=0 WHERE id=?',(enrollment_id,))
            self.db.conn.execute("UPDATE sessions SET status='草稿',modified=?",(now(),))

    def batches(self):
        return self.db.rows('SELECT * FROM batches ORDER BY created DESC')

    def sessions(self):
        return self.db.rows('''SELECT s.*,co.code,co.name_cn,co.id course_id,b.name batch_name,b.academic_year,b.semester,
            b.exam_type,b.id batch_id FROM sessions s JOIN exams e ON e.id=s.exam_id JOIN courses co ON co.id=e.course_id
            JOIN batches b ON b.id=e.batch_id ORDER BY s.date,s.start,co.code''')

    def create_session(self,batch_id,course_id,values,class_ids,room_ids):
        self.check_times(values)
        if not class_ids or not room_ids:
            raise ValidationError('至少選擇一個班級及考場。')
        if any(not self.db.one('SELECT id FROM classes WHERE id=? AND course_id=?',(c,course_id)) for c in class_ids):
            raise ValidationError('班級不屬於所選科目。')
        batch=self.db.one('SELECT * FROM batches WHERE id=?',(batch_id,))
        if not batch:raise ValidationError('學年考試設定不存在。')
        for cid in class_ids:
            cls=self.db.one('SELECT * FROM classes WHERE id=?',(cid,))
            year=lambda value:re.sub('[-–—/]','',value)
            if cls['academic_year'] and (year(cls['academic_year'])!=year(batch['academic_year']) or cls['semester']!=batch['semester']):
                raise ValidationError('授課班的學年學期與所選考試設定不符。')
        identifier=uid()
        with self.db.conn:
            existing=self.db.one('SELECT id FROM exams WHERE batch_id=? AND course_id=?',(batch_id,course_id))
            exam=existing['id'] if existing else uid()
            if not existing:self.db.conn.execute('INSERT INTO exams(id,batch_id,course_id) VALUES(?,?,?)',(exam,batch_id,course_id))
            self.db.conn.execute('INSERT INTO sessions(id,exam_id,date,start,end,teachers,intake,allow_merge,modified) VALUES(?,?,?,?,?,?,?,?,?)',
                (identifier,exam,values['date'],values['start'],values['end'],values.get('teachers',''),values.get('intake',''),int(values.get('allow_merge',0)),now()))
            self.db.conn.executemany('INSERT INTO session_classes VALUES(?,?)',[(identifier,c) for c in set(class_ids)])
            for room in set(room_ids):
                r=self.db.one('SELECT * FROM rooms WHERE id=?',(room,))
                if not r or not r['enabled']:
                    raise ValidationError('所選考場已停用或不存在。')
                self.check_room_conflict(identifier,room)
                self.db.conn.execute('INSERT INTO allocations VALUES(?,?,?)',(uid(),identifier,room))
        return identifier

    @staticmethod
    def check_times(v):
        try:
            date.fromisoformat(v['date'])
            start=time.fromisoformat(v['start']);end=time.fromisoformat(v['end'])
            if start>=end: raise ValueError()
        except (ValueError,KeyError):
            raise ValidationError('日期格式為 YYYY-MM-DD，時間為 HH:MM，結束時間須晚於開始時間。')

    def update_session(self,sid,values):
        self.check_times(values)
        with self.db.conn:
            self.db.conn.execute('UPDATE sessions SET date=?,start=?,end=?,teachers=?,intake=?,allow_merge=?,status=?,modified=? WHERE id=?',
              (values['date'],values['start'],values['end'],values.get('teachers',''),values.get('intake',''),int(values.get('allow_merge',0)),'草稿',now(),sid))
            for al in self.allocations(sid):
                self.check_room_conflict(sid,al['room_id'])
            for st in self.assigned(sid):
                self.check_student_conflict(sid,st['student_id'])

    def copy_session(self,sid):
        s=next(x for x in self.sessions() if x['id']==sid)
        # Copy to the following day so the copied settings do not instantly collide.
        from datetime import timedelta
        values=dict(s,date=(date.fromisoformat(s['date'])+timedelta(days=1)).isoformat())
        classes=[x['class_id'] for x in self.db.rows('SELECT class_id FROM session_classes WHERE session_id=?',(sid,))]
        return self.create_session(s['batch_id'],s['course_id'],values,classes,[a['room_id'] for a in self.allocations(sid)])

    def delete_session(self,sid):
        with self.db.conn:
            e=self.db.one('SELECT exam_id FROM sessions WHERE id=?',(sid,))
            self.db.conn.execute('DELETE FROM sessions WHERE id=?',(sid,))
            if e and not self.db.one('SELECT id FROM sessions WHERE exam_id=?',(e['exam_id'],)):
                self.db.conn.execute('DELETE FROM exams WHERE id=?',(e['exam_id'],))

    def overlap_sessions(self,sid):
        return self.db.rows('''SELECT o.* FROM sessions o JOIN sessions s ON s.id=?
           WHERE o.id<>s.id AND o.date=s.date AND o.start<s.end AND s.start<o.end''',(sid,))

    def check_room_conflict(self,sid,room_id):
        current=self.db.one('SELECT * FROM sessions WHERE id=?',(sid,))
        for other in self.overlap_sessions(sid):
            if self.db.one('SELECT id FROM allocations WHERE session_id=? AND room_id=?',(other['id'],room_id)):
                if not (current['allow_merge'] and other['allow_merge']):
                    raise ValidationError('同一時段考場已被另一考試使用；合場必須在雙方場次明確啟用。')

    def check_student_conflict(self,sid,student_id):
        for other in self.overlap_sessions(sid):
            if self.db.one('''SELECT a.id FROM assignments a JOIN allocations al ON al.id=a.allocation_id
                WHERE al.session_id=? AND a.student_id=?''',(other['id'],student_id)):
                raise ValidationError('學生同一時段已被安排另一科考試。')

    @staticmethod
    def seat_pool(room):
        raw=room.get('usable_seats','').strip()
        if not raw:
            return [f'{i:03d}' for i in range(1,int(room['capacity'])+1)]
        try:
            numbers=[int(x.strip()) for x in re.split(r'[,，\s]+',raw) if x.strip()]
            if not numbers or len(numbers)!=len(set(numbers)) or any(n<1 or n>999 for n in numbers):
                raise ValueError()
            return [f'{n:03d}' for n in sorted(numbers)]
        except ValueError:
            raise ValidationError('可用座位請輸入不重複的 1–999 座號，以逗號分隔；留空表示 001 起連續編號。')

    def allocations(self,sid=None):
        sql='''SELECT al.*,r.name room_name,r.capacity,r.usable_seats,r.enabled,
          COUNT(a.id) count FROM allocations al JOIN rooms r ON r.id=al.room_id
          LEFT JOIN assignments a ON a.allocation_id=al.id'''
        if sid: sql+=' WHERE al.session_id=?'
        return self.db.rows(sql+' GROUP BY al.id ORDER BY r.name',(sid,) if sid else ())

    def assigned(self,sid=None,aid=None):
        sql='''SELECT a.*,s.student_no,s.chinese_name,s.english_name,e.active,c.name class_name,c.id class_id,
          al.session_id,al.room_id,r.name room_name,COALESCE(f.reason,'') flag_reason FROM assignments a JOIN students s ON s.id=a.student_id
          LEFT JOIN student_flags f ON f.student_id=s.id
          JOIN enrollments e ON e.id=a.enrollment_id JOIN classes c ON c.id=e.class_id
          JOIN allocations al ON al.id=a.allocation_id JOIN rooms r ON r.id=al.room_id'''
        if aid: sql+=' WHERE a.allocation_id=?'; args=(aid,)
        elif sid: sql+=' WHERE al.session_id=?'; args=(sid,)
        else: args=()
        return self.db.rows(sql+' ORDER BY r.name,a.position',args)

    def participants(self,sid):
        return self.db.rows('''SELECT s.*,s.id student_id,e.id enrollment_id,c.name class_name,c.id class_id,e.position,COALESCE(f.reason,'') flag_reason
          FROM session_classes sc JOIN enrollments e ON e.class_id=sc.class_id AND e.active=1
          JOIN students s ON s.id=e.student_id JOIN classes c ON c.id=sc.class_id
          LEFT JOIN student_flags f ON f.student_id=s.id
          WHERE sc.session_id=? ORDER BY c.name,e.position''',(sid,))

    def pending(self,sid,class_id=None):
        assigned={s['student_id'] for s in self.assigned(sid)}
        return [s for s in self.participants(sid) if s['student_id'] not in assigned and (not class_id or s['class_id']==class_id)]

    def snapshot(self,sid):
        return self.db.rows('''SELECT a.* FROM assignments a JOIN allocations al ON al.id=a.allocation_id
            WHERE al.session_id=? ORDER BY a.id''',(sid,))

    @contextmanager
    def mutation(self,sid):
        with self.db.conn:
            before=self.snapshot(sid)
            yield
            after=self.snapshot(sid)
            if before!=after:
                self.db.conn.execute('DELETE FROM history WHERE session_id=? AND applied=0',(sid,))
                self.db.conn.execute('INSERT INTO history(session_id,before_json,after_json,created) VALUES(?,?,?,?)',
                     (sid,json.dumps(before),json.dumps(after),now()))
                self.db.conn.execute("UPDATE sessions SET modified=?,status='草稿' WHERE id=?",(now(),sid))

    def remaining(self,aid):
        al=self.db.one('''SELECT al.*,r.* FROM allocations al JOIN rooms r ON r.id=al.room_id WHERE al.id=?''',(aid,))
        mine=self.assigned(aid=aid)
        # Conservatively reserve all overlapping merged allocations; seat identities also cannot collide.
        others=[]
        for session in self.overlap_sessions(al['session_id']):
            others += [a for a in self.assigned(session['id']) if a['room_id']==al['room_id']]
        taken={a['seat'] for a in mine+others}
        available=[s for s in self.seat_pool(al) if s not in taken]
        return max(0,min(int(al['capacity'])-len(mine)-len(others),len(available))),available

    def assign(self,aid,class_id=None,student_ids=None):
        al=self.db.one('SELECT * FROM allocations WHERE id=?',(aid,))
        if not al: raise ValidationError('考場分配不存在。')
        room=self.db.one('SELECT * FROM rooms WHERE id=?',(al['room_id'],))
        if not room['enabled']: raise ValidationError('此考場已停用。')
        self.check_room_conflict(al['session_id'],al['room_id'])
        pending=self.pending(al['session_id'],class_id)
        if student_ids is not None:
            wanted=set(student_ids)
            pending=[s for s in pending if s['student_id'] in wanted]
            if len(pending)!=len(wanted): raise ValidationError('選取學生已被分配或不在此場次。')
        if not pending: raise ValidationError('沒有待分配學生。')
        remain,seats=self.remaining(aid)
        if len(pending)>remain: raise CapacityError(remain,len(pending))
        for st in pending: self.check_student_conflict(al['session_id'],st['student_id'])
        with self.mutation(al['session_id']):
            offset=len(self.assigned(aid=aid))
            for i,st in enumerate(pending):
                self.db.conn.execute('INSERT INTO assignments(id,allocation_id,student_id,enrollment_id,position,seat) VALUES(?,?,?,?,?,?)',
                    (uid(),aid,st['student_id'],st['enrollment_id'],offset+i,seats[i]))

    def renumber(self,aid,order=None):
        rows=self.assigned(aid=aid)
        if order is not None:
            byid={r['id']:r for r in rows}
            if len(order)!=len(rows) or set(order)!=set(byid): raise ValidationError('排序資料不完整。')
            rows=[byid[i] for i in order]
        al=next(a for a in self.allocations() if a['id']==aid)
        _,available=self.remaining(aid)
        # All unlocked current seats and unused seats, except locked and merged-room occupants.
        fixed={r['seat'] for r in rows if r['locked']}
        pool=sorted(set(available+[r['seat'] for r in rows if not r['locked']])-fixed)
        if len(pool)<sum(not r['locked'] for r in rows): raise ValidationError('可用座位不足。')
        # Temporary unique strings prevent unique-constraint collisions while swapping.
        for r in rows:
            self.db.conn.execute('UPDATE assignments SET seat=? WHERE id=?',('tmp-'+r['id'],r['id']))
        for i,r in enumerate(rows):
            seat=r['seat'] if r['locked'] else pool.pop(0)
            self.db.conn.execute('UPDATE assignments SET position=?,seat=? WHERE id=?',(i,seat,r['id']))

    def reorder(self,aid,order):
        al=next(a for a in self.allocations() if a['id']==aid)
        with self.mutation(al['session_id']): self.renumber(aid,order)

    def shuffle_seats(self,aid):
        """Shuffle unlocked students among occupied slots in just this room."""
        from random import SystemRandom
        allocation=self.db.one('SELECT * FROM allocations WHERE id=?',(aid,))
        if not allocation:raise ValidationError('請先選擇考場。')
        slots=[r for r in self.assigned(aid=aid) if not r['locked']]
        if len(slots)<2:raise ValidationError('至少需要兩位未鎖定座號的學生，才可隨機打散。')
        original=[r['id'] for r in slots];order=list(original)
        rng=SystemRandom()
        while order==original:rng.shuffle(order)
        with self.mutation(allocation['session_id']):
            for identifier in order:
                self.db.conn.execute('UPDATE assignments SET seat=? WHERE id=?',('tmp-'+identifier,identifier))
            for slot,identifier in zip(slots,order):
                self.db.conn.execute('UPDATE assignments SET seat=?,position=? WHERE id=?',(slot['seat'],slot['position'],identifier))

    def unassign(self,assignment_ids):
        rows=[r for r in self.assigned() if r['id'] in set(assignment_ids)]
        if not rows: return
        if len({r['session_id'] for r in rows})!=1: raise ValidationError('請逐一場次調整。')
        if any(r['locked'] for r in rows): raise ValidationError('請先解除座號鎖定。')
        with self.mutation(rows[0]['session_id']):
            self.db.conn.executemany('DELETE FROM assignments WHERE id=?',[(r['id'],) for r in rows])
            for aid in {r['allocation_id'] for r in rows}: self.renumber(aid)

    def move_students(self,assignment_ids,target_aid):
        rows=[r for r in self.assigned() if r['id'] in set(assignment_ids)]
        target=next(a for a in self.allocations() if a['id']==target_aid)
        if not rows or any(r['session_id']!=target['session_id'] for r in rows): raise ValidationError('請選取同場次學生。')
        if any(r['locked'] for r in rows): raise ValidationError('請先解除座號鎖定。')
        if not target['enabled']:raise ValidationError('目標考場已停用。')
        self.check_room_conflict(target['session_id'],target['room_id'])
        rows=[r for r in rows if r['allocation_id']!=target_aid]
        remain,seats=self.remaining(target_aid)
        if len(rows)>remain: raise CapacityError(remain,len(rows))
        with self.mutation(target['session_id']):
            offset=len(self.assigned(aid=target_aid))
            for i,r in enumerate(rows):
                self.db.conn.execute('UPDATE assignments SET allocation_id=?,position=?,seat=? WHERE id=?',(target_aid,offset+i,seats[i],r['id']))
            for aid in {r['allocation_id'] for r in rows}: self.renumber(aid)

    def special(self,assignment_id,seat,locked,special,note):
        r=next(r for r in self.assigned() if r['id']==assignment_id)
        al=next(a for a in self.allocations() if a['id']==r['allocation_id'])
        seat=f'{int(seat):03d}'
        if r['locked'] and seat!=r['seat']: raise ValidationError('請先解除鎖定，再修改座號。')
        if seat not in self.seat_pool(al): raise ValidationError('座號不在可用座位中。')
        if any(x['seat']==seat and x['id']!=r['id'] for x in self.assigned(aid=al['id'])):
            raise ValidationError('此座位已有學生，請先調整或交換。')
        for other in self.overlap_sessions(r['session_id']):
            if any(x['room_id']==r['room_id'] and x['seat']==seat for x in self.assigned(other['id'])):
                raise ValidationError('合場考試已佔用此座位。')
        with self.mutation(r['session_id']):
            self.db.conn.execute('UPDATE assignments SET seat=?,locked=?,special=?,note=? WHERE id=?',
                                 (seat,int(locked),special,note,r['id']))

    def undo(self,sid,redo=False):
        row=self.db.one('SELECT * FROM history WHERE session_id=? AND applied=? ORDER BY id '+('ASC' if redo else 'DESC')+' LIMIT 1',
                        (sid,0 if redo else 1))
        if not row: raise ValidationError('沒有可重做的操作。' if redo else '沒有可復原的操作。')
        target=json.loads(row['after_json'] if redo else row['before_json'])
        with self.db.conn:
            self.db.conn.execute('DELETE FROM assignments WHERE allocation_id IN (SELECT id FROM allocations WHERE session_id=?)',(sid,))
            for r in target:
                self.db.conn.execute('INSERT INTO assignments('+','.join(r)+') VALUES('+','.join('?' for _ in r)+')',tuple(r.values()))
            # Changes in other sessions must not let undo bypass conflicts or capacity.
            for al in self.allocations(sid):
                remain,_=self.remaining(al['id'])
                if al['count']>min(al['capacity'],len(self.seat_pool(al))): raise ValidationError('復原後超出考場容量。')
                self.check_room_conflict(sid,al['room_id'])
            for r in self.assigned(sid): self.check_student_conflict(sid,r['student_id'])
            errors=[e for e in self.validate(sid,False) if e in ['合場考試總人數超出容量。','合場考試座號重複。','座號不在可用座位內。']]
            if errors:raise ValidationError('復原操作會產生座位衝突：\n'+'\n'.join(errors))
            self.db.conn.execute('UPDATE history SET applied=? WHERE id=?',(int(redo),row['id']))
            self.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id=?",(now(),sid))

    def validate(self,sid,require_complete=True):
        errors=[]
        participants=self.participants(sid); assigned=self.assigned(sid)
        if not participants: errors.append('此場次沒有學生。')
        if len({r['student_id'] for r in participants})!=len(participants): errors.append('同場次學生出現在多個班級。')
        if len({r['student_id'] for r in assigned})!=len(assigned):errors.append('同場次重複分配學生。')
        if any(r['class_id'] not in {p['class_id'] for p in participants} for r in assigned):errors.append('已分配學生的班級不在此場次。')
        if require_complete and self.pending(sid): errors.append(f'尚有 {len(self.pending(sid))} 名學生未分配。')
        for r in assigned:
            if not r['active']: errors.append('已移除修讀記錄仍有座位，請人工移回待分配／移除。')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',r['student_no']): errors.append('存在錯誤學號。')
            try:self.check_student_conflict(sid,r['student_id'])
            except ValidationError as e:errors.append(str(e))
        for al in self.allocations(sid):
            rows=self.assigned(aid=al['id'])
            if not al['enabled']: errors.append('所用考場已停用。')
            if len(rows)>min(al['capacity'],len(self.seat_pool(al))):errors.append('考場超出容量。')
            if any(r['seat'] not in self.seat_pool(al) for r in rows):errors.append('座號不在可用座位內。')
            others=[]
            for other in self.overlap_sessions(sid):
                others += [r for r in self.assigned(other['id']) if r['room_id']==al['room_id']]
            if len(rows)+len(others)>al['capacity']:errors.append('合場考試總人數超出容量。')
            if {r['seat'] for r in rows}&{r['seat'] for r in others}:errors.append('合場考試座號重複。')
            try:self.check_room_conflict(sid,al['room_id'])
            except ValidationError as e:errors.append(str(e))
        return list(dict.fromkeys(errors))

    def complete(self,sid):
        errors=self.validate(sid)
        with self.db.conn:
            self.db.conn.execute('UPDATE sessions SET status=?,modified=? WHERE id=?',('待處理錯誤' if errors else '已完成編排',now(),sid))
        if errors: raise ValidationError('\n'.join(errors))

    def export_data(self,aid):
        al=next(a for a in self.allocations() if a['id']==aid)
        errors=self.validate(al['session_id'])
        if errors: raise ValidationError('\n'.join(errors))
        students=self.assigned(aid=aid)
        if not students: raise ValidationError('此考場沒有學生。')
        info=self.db.one('''SELECT s.*,co.code,co.name_cn,co.name_en,co.programme,co.programme_en,co.language,
              b.academic_year,b.semester,b.exam_type,b.name batch_name FROM sessions s
              JOIN exams e ON e.id=s.exam_id JOIN courses co ON co.id=e.course_id JOIN batches b ON b.id=e.batch_id WHERE s.id=?''',(al['session_id'],))
        missing=[label for key,label in [('teachers','任課教師'),('intake','入讀時間'),('name_en','科目英文名稱'),('programme','學位課程中文名稱'),('programme_en','學位課程英文名稱')] if not info.get(key,'').strip()]
        if missing:raise ValidationError('輸出表頭資料不完整：'+ '、'.join(missing)+'。請在科目或場次資料補齊。')
        return dict(info,room_name=al['room_name']),students

    def dashboard(self):
        result={}
        for table in ['students','courses','batches','sessions','allocations']:
            result[table]=self.db.one(f'SELECT COUNT(*) n FROM {table}')['n']
        result['complete']=sum(s['status'] in ('已完成編排','已生成文件') and not self.validate(s['id']) for s in self.sessions())
        result['pending']=result['sessions']-result['complete']
        return result

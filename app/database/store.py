import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from app.models.records import ValidationError


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now().isoformat(timespec='microseconds')


def default_data_dir():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'FOFExamManager'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'FOFExamManager'


SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS students(id TEXT PRIMARY KEY,student_no TEXT NOT NULL UNIQUE,
 chinese_name TEXT NOT NULL,english_name TEXT NOT NULL,raw_name TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY,code TEXT NOT NULL UNIQUE,name_cn TEXT NOT NULL,
 name_en TEXT NOT NULL DEFAULT '',teachers TEXT NOT NULL DEFAULT '',programme TEXT NOT NULL DEFAULT '',
 programme_en TEXT NOT NULL DEFAULT '',language TEXT NOT NULL DEFAULT '中文',notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id),
 name TEXT NOT NULL,expected INTEGER,UNIQUE(course_id,name));
CREATE TABLE IF NOT EXISTS enrollments(id TEXT PRIMARY KEY,student_id TEXT NOT NULL REFERENCES students(id),
 class_id TEXT NOT NULL REFERENCES classes(id),source TEXT NOT NULL DEFAULT '',position INTEGER NOT NULL,
 active INTEGER NOT NULL DEFAULT 1,UNIQUE(student_id,class_id));
CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,capacity INTEGER NOT NULL CHECK(capacity>0),
 usable_seats TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,name TEXT NOT NULL,academic_year TEXT NOT NULL,
 semester TEXT NOT NULL,exam_type TEXT NOT NULL,programme TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES batches(id),
 course_id TEXT NOT NULL REFERENCES courses(id),notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
 date TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,teachers TEXT NOT NULL,intake TEXT NOT NULL DEFAULT '',
 allow_merge INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT '草稿',modified TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session_classes(session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 class_id TEXT REFERENCES classes(id),PRIMARY KEY(session_id,class_id));
CREATE TABLE IF NOT EXISTS allocations(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 room_id TEXT NOT NULL REFERENCES rooms(id),UNIQUE(session_id,room_id));
CREATE TABLE IF NOT EXISTS assignments(id TEXT PRIMARY KEY,allocation_id TEXT NOT NULL REFERENCES allocations(id) ON DELETE CASCADE,
 student_id TEXT NOT NULL REFERENCES students(id),enrollment_id TEXT NOT NULL REFERENCES enrollments(id),
 position INTEGER NOT NULL,seat TEXT NOT NULL,locked INTEGER NOT NULL DEFAULT 0,
 special TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',UNIQUE(allocation_id,seat),UNIQUE(allocation_id,student_id));
CREATE TRIGGER IF NOT EXISTS session_unique_student BEFORE INSERT ON assignments
 WHEN EXISTS(SELECT 1 FROM assignments a JOIN allocations old ON old.id=a.allocation_id
 JOIN allocations target_alloc ON target_alloc.id=NEW.allocation_id WHERE old.session_id=target_alloc.session_id AND a.student_id=NEW.student_id)
 BEGIN SELECT RAISE(ABORT,'duplicate student in session'); END;
CREATE TRIGGER IF NOT EXISTS session_unique_student_update BEFORE UPDATE OF allocation_id,student_id ON assignments
 WHEN EXISTS(SELECT 1 FROM assignments a JOIN allocations old ON old.id=a.allocation_id
 JOIN allocations target_alloc ON target_alloc.id=NEW.allocation_id WHERE old.session_id=target_alloc.session_id AND a.student_id=NEW.student_id AND a.id<>NEW.id)
 BEGIN SELECT RAISE(ABORT,'duplicate student in session'); END;
CREATE TABLE IF NOT EXISTS import_logs(id TEXT PRIMARY KEY,source TEXT NOT NULL,created TEXT NOT NULL,summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS generation_logs(id TEXT PRIMARY KEY,allocation_id TEXT REFERENCES allocations(id) ON DELETE SET NULL,
 created TEXT NOT NULL,path TEXT NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 before_json TEXT NOT NULL,after_json TEXT NOT NULL,applied INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL);
'''


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_data_dir() / 'fof_exam.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        existing={r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if existing and ('schema_version' not in existing or self.conn.execute('SELECT version FROM schema_version').fetchone()[0]!=1):
            self.conn.close()
            raise ValidationError('此資料庫不是相容的 FOF 考試系統資料庫，未改動其內容。')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA busy_timeout=5000')
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        if self.conn.execute('SELECT version FROM schema_version').fetchone()[0] != 1:
            self.conn.close()
            raise ValidationError('資料庫版本不相容；請使用相應版本程式或還原相容備份。')

    def rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def backup(self, target):
        target = Path(target)
        if target.resolve() == self.path.resolve():
            raise ValidationError('備份路徑不可與現有資料庫相同。')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents silent replacement, including races.
        with target.open('xb'):
            pass
        try:
            with sqlite3.connect(target) as dst:
                self.conn.backup(dst)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target

    def restore(self, source):
        source = Path(source).resolve()
        if source == self.path.resolve():
            raise ValidationError('請選擇另一份備份檔案。')
        with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValidationError('備份檔案完整性檢查失敗。')
            required = {'students','courses','classes','enrollments','rooms','batches','exams',
                        'sessions','session_classes','allocations','assignments','history','schema_version',
                        'import_logs','generation_logs'}
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables or src.execute('SELECT version FROM schema_version').fetchone()[0] != 1:
                raise ValidationError('這不是相容的 FOF 考試系統備份。')
            for table in required:
                expected=[tuple(r)[1:6] for r in self.conn.execute(f'PRAGMA table_info({table})')]
                actual=[tuple(r)[1:6] for r in src.execute(f'PRAGMA table_info({table})')]
                if actual!=expected:raise ValidationError('備份資料欄位不相容，現有資料沒有改動。')
            if src.execute('PRAGMA foreign_key_check').fetchone():
                raise ValidationError('備份的資料關聯已損壞。')
            backup = self.path.with_name('before_restore_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uid()[:6] + '.sqlite3')
            self.backup(backup)
            src.backup(self.conn)
        self.conn.execute('PRAGMA foreign_keys=ON')
        return backup

    def close(self):
        self.conn.close()

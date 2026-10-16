
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

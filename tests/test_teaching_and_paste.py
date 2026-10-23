import json
import os
import sqlite3
from pathlib import Path
import pytest
from openpyxl import Workbook,load_workbook
from PySide6.QtCore import Qt,QMimeData
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog
from app.database.store import Store
from app.services.manager import Manager
from app.importers.roster import inspect_roster
from app.importers.courses import parse_courses
from app.models.records import ValidationError
from app.models.programmes import parse_teaching_code,PROGRAMMES
from app.ui.course_paste import CoursePasteDialog
from app.ui.batch_dialog import BatchDialog
from app.ui.import_dialog import ImportDialog
from app.ui.window import MainWindow,ROOM_FIELDS,SessionDialog
from conftest import setup_exam


def workbook(path,code='261BAECF3DBAE30500',summary=True):
    w=Workbook();w.remove(w.active)
    for name,ids in ([('匯總',[1,2]),('D',[1]),('A',[2])] if summary else [('D',[1]),('A',[2])]):
        s=w.create_sheet(name)
        s.append(['科目名稱','公司金融 - BAE305-D'])
        s.append(['科目代碼',code,'教務科目代碼','BAE305'])
        s.append(['帳號','姓名','英文姓名','班級'])
        for i in ids:s.append([f'ST{i:03d}',f'學生{i}',f'STUDENT {i}','D' if i==1 else 'A'])
    w.save(path);return path


def test_decode_course_offering():
    c=parse_teaching_code('261BAECF3DBAE30500','BAE305')
    assert (c.academic_year,c.semester,c.programme_code,c.grade,c.class_name,c.course_code)==('2026–2027','第一學期','BAECF',3,'3D','BAE305')
    assert parse_teaching_code('262BAECF3DBAE30500').semester=='第二學期'
    assert parse_teaching_code('bad') is None


@pytest.mark.parametrize('summary',[True,False])
def test_roster_counts_administrative_classes_together(tmp_path,summary):
    if not summary:
        with pytest.raises(ValidationError,match='找不到匯總'):
            inspect_roster(workbook(tmp_path/'3D.xlsx',summary=False))
        return
    candidates=inspect_roster(workbook(tmp_path/'3D.xlsx',summary=summary))
    assert len(candidates)==1 and candidates[0].recommended
    rows=candidates[0].records
    assert len(rows)==2 and {r.class_name for r in rows}=={'3D'}
    assert {r.administrative_class for r in rows}=={''}
    assert all(r.teaching_code=='261BAECF3DBAE30500' for r in rows)


def test_repeated_summary_not_duplicated_and_idempotent(manager,tmp_path):
    records=inspect_roster(workbook(tmp_path/'3D.xlsx'))[0].records
    manager.import_records(records);manager.import_records(records)
    assert len(manager.students())==2 and manager.classes()[0]['count']==2
    assert {s['administrative_class'] for s in manager.students()}=={''}
    assert manager.courses()[0]['programme_en']==PROGRAMMES['BAECF'][1]


def test_same_course_same_class_different_years_separate(manager,tmp_path):
    a=inspect_roster(workbook(tmp_path/'2026.xlsx'))[0].records
    b=inspect_roster(workbook(tmp_path/'2027.xlsx','271BAECF3DBAE30500'))[0].records
    manager.import_records(a+b)
    assert len(manager.classes())==2
    assert len(manager.students())==4
    assert manager.db.one('SELECT COUNT(*) n FROM students')['n']==2
    assert {c['academic_year'] for c in manager.classes()}=={'2026–2027','2027–2028'}


def v1_database(path):
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent/'fixtures/v1_schema.sql').read_text(encoding='utf8'))
        db.execute("INSERT INTO courses(id,code,name_cn) VALUES('course','BAE305','公司金融')")
        db.execute("INSERT INTO classes(id,course_id,name) VALUES('class','course','D')")
        db.execute("INSERT INTO students VALUES('student','ST001','學生1','STUDENT 1','學生1')")
        db.execute("INSERT INTO enrollments(id,student_id,class_id,source,position) VALUES('enrollment','student','class','3D.xlsx',0)")
        db.execute("INSERT INTO rooms(id,name,capacity) VALUES('room','G2209',80)")
        db.execute("INSERT INTO batches(id,name,academic_year,semester,exam_type,created) VALUES('batch','Old','2026–2027','第一學期','期中','2026-10-14')")
        db.execute("INSERT INTO exams(id,batch_id,course_id) VALUES('exam','batch','course')")
        db.execute("INSERT INTO sessions(id,exam_id,date,start,end,teachers,modified) VALUES('session','exam','2026-10-14','19:00','21:00','Teacher','2026-10-14')")
        db.execute("INSERT INTO session_classes VALUES('session','class')")
        db.execute("INSERT INTO allocations VALUES('allocation','session','room')")
        db.execute("INSERT INTO assignments(id,allocation_id,student_id,enrollment_id,position,seat,locked,note) VALUES('assignment','allocation','student','enrollment',0,'007',1,'PRIVATE')")


def test_v1_upgrade_and_reimport_preserve_locked_seat(tmp_path):
    path=tmp_path/'old.sqlite3';v1_database(path)
    store=Store(path)
    try:
        assert store.upgrade_backup.exists()
        with sqlite3.connect(store.upgrade_backup) as old:assert old.execute('SELECT version FROM schema_version').fetchone()[0]==1
        m=Manager(store);records=inspect_roster(workbook(tmp_path/'3D.xlsx'))[0].records
        assert len(m.import_diff(records)['unchanged'])==1
        m.import_records(records)
        assert m.classes()[0]['id']=='class' and m.classes()[0]['name']=='3D' and m.classes()[0]['count']==2
        seat=m.assigned('session')[0]
        assert (seat['id'],seat['enrollment_id'],seat['seat'],seat['locked'],seat['note'])==('assignment','enrollment','007',1,'PRIVATE')
        assert len(m.pending('session'))==1
        assert store.conn.execute('PRAGMA foreign_key_check').fetchone() is None
    finally:store.close()


def test_restore_v1_backup_without_altering_backup(manager,tmp_path):
    path=tmp_path/'v1.sqlite3';v1_database(path);before=path.read_bytes()
    backup=manager.db.restore(path)
    assert backup.exists() and path.read_bytes()==before
    assert manager.assigned('session')[0]['seat']=='007'
    assert manager.db.one('SELECT version FROM schema_version')['version']==2


def test_old_administrative_membership_moves_without_losing_id(tmp_path):
    path=tmp_path/'old.sqlite3';v1_database(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO classes(id,course_id,name) VALUES('adminA','course','A')")
        db.execute("UPDATE enrollments SET class_id='adminA'")
        db.execute("INSERT INTO session_classes VALUES('session','adminA')")
    store=Store(path)
    try:
        m=Manager(store);m.import_records(inspect_roster(workbook(tmp_path/'3D.xlsx'))[0].records)
        assert m.assigned('session')[0]['enrollment_id']=='enrollment'
        assert m.assigned('session')[0]['class_name']=='3D'
        assert not any('班級不在' in x for x in m.validate('session',False))
    finally:store.close()


def test_old_mixed_administrative_class_reclassified_in_import_order(tmp_path):
    path=tmp_path/'old.sqlite3';v1_database(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO classes(id,course_id,name) VALUES('adminE','course','E')")
        db.execute("INSERT INTO classes(id,course_id,name) VALUES('classF','course','F')")
        db.execute("UPDATE enrollments SET class_id='adminE',source='3F.xlsx'")
        db.execute("INSERT INTO session_classes VALUES('session','adminE')")
    store=Store(path)
    try:
        m=Manager(store)
        e=inspect_roster(workbook(tmp_path/'3E.xlsx','261BAECF3EBAE30500'))[0].records[1:]
        f=inspect_roster(workbook(tmp_path/'3F.xlsx','261BAECF3FBAE30500'))[0].records[:1]
        m.import_records(e);m.import_records(f)
        assert m.assigned('session')[0]['class_name']=='3F'
        assert m.assigned('session')[0]['seat']=='007'
    finally:store.close()


def test_upgrade_does_not_move_old_year_seats_into_new_year(tmp_path):
    path=tmp_path/'old.sqlite3';v1_database(path)
    with sqlite3.connect(path) as db:db.execute("UPDATE batches SET academic_year='2025–2026'")
    store=Store(path)
    try:
        m=Manager(store);records=inspect_roster(workbook(tmp_path/'3D.xlsx'))[0].records
        m.import_records(records,remove_missing=True)
        assert m.assigned('session')[0]['class_name']=='D'
        assert m.assigned('session')[0]['seat']=='007'
        assert {c['name'] for c in m.classes()}=={'D','3D'}
        assert len(m.participants('session'))==1
    finally:store.close()


COPIED='BAECF\tBAE101\t"微積分導論\nIntroductory Calculus"\t教師甲、Teacher B\nBAECF\tBAE305\t"公司金融\nCorporate Finance"\tArman Eshraghi、王璐、江宇\nBAECF\t"BAE406 &\nBAE411"\t"金融與經濟研究方法\nResearch Methods in Finance & Economics"\t教師乙'


def test_copied_multiline_table_and_combined_codes(manager):
    preview=parse_courses(COPIED)
    assert [r.values['code'] for r in preview]==['BAE101','BAE305','BAE406','BAE411']
    assert preview[1].values['name_cn']=='公司金融'
    assert preview[1].values['name_en']=='Corporate Finance'
    assert preview[1].values['teachers']=='Arman Eshraghi、王璐、江宇'
    assert not preview[0].issues and preview[2].issues
    manager.save_courses([r.values for r in preview])
    assert len(manager.courses())==4


def test_html_table_and_separate_columns():
    html='<table><tr><td>BAECF</td><td>BAE305</td><td>公司金融<br>Corporate Finance</td><td>教師甲 · Teacher B</td></tr></table>'
    preview=parse_courses('',html)
    assert preview[0].values['name_en']=='Corporate Finance'
    assert not preview[0].issues
    separate=parse_courses('BAECF\tBAE305\t公司金融\tCorporate Finance\t教師甲')[0]
    assert separate.values['name_cn']=='公司金融' and separate.values['teachers']=='教師甲'


def test_invalid_or_duplicate_paste_not_silently_saved(manager):
    with pytest.raises(ValidationError):parse_courses('no course numbers')
    preview=parse_courses(COPIED+'\nBAECF\tBAE305\t公司金融\tCorporate Finance\tTeacher')
    assert '重複' in ' '.join(preview[1].issues)
    with pytest.raises(ValidationError):manager.save_courses([r.values for r in preview])
    assert not manager.courses()


def test_clipboard_preview_edit_confirm(qtbot,manager,monkeypatch):
    d=CoursePasteDialog(manager);qtbot.addWidget(d)
    QApplication.clipboard().setText(COPIED)
    d.from_clipboard();assert d.table.rowCount()==4 and not manager.courses()
    d.table.item(1,3).setText('教師修正、Teacher C')
    for i in range(4):d.table.item(i,5).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    d.commit();assert d.result()==QDialog.DialogCode.Accepted
    assert next(c for c in manager.courses() if c['code']=='BAE305')['teachers']=='教師修正、Teacher C'


def test_native_paste_preserves_html_and_analyzes(qtbot,manager):
    d=CoursePasteDialog(manager);qtbot.addWidget(d)
    mime=QMimeData();mime.setText('plain text without table boundaries')
    mime.setHtml('<table><tr><td>BAECF</td><td>BAE305</td><td>公司金融<br>Corporate Finance</td><td>教師甲</td></tr></table>')
    d.text.insertFromMimeData(mime)
    assert d.table.rowCount()==1 and d.table.item(0,2).text()=='Corporate Finance'


def test_batch_generated_name_and_fixed_programme(manager,qtbot):
    d=BatchDialog();qtbot.addWidget(d)
    assert 'name' not in d.editors and 'programme' not in d.editors
    d.editors['academic_year'].setCurrentIndex(d.editors['academic_year'].findData('2026–2027'))
    d.editors['semester'].setCurrentIndex(1);d.editors['exam_type'].setCurrentIndex(1)
    assert d.preview.text()=='2026–2027學年第二學期期末考試'
    identifier=manager.save_batch(d.values());batch=manager.batches()[0]
    assert batch['name']==d.preview.text() and '金融學院' in batch['programme']
    assert PROGRAMMES['BAECF'][0] in batch['programme']
    assert 'usable_seats' not in {f[0] for f in ROOM_FIELDS}


def test_coded_roster_preview_shows_actual_teaching_class(qtbot,manager,tmp_path):
    d=ImportDialog(manager,[workbook(tmp_path/'3D.xlsx')]);qtbot.addWidget(d)
    assert d.preview.rowCount()==2
    assert d.preview.item(1,3).text()=='3D'
    assert d.preview.item(0,7).text()=='261BAECF3DBAE30500'
    assert '完整匯總名單' in d.summary.text()
    assert not any('行政班' in d.preview.horizontalHeaderItem(i).text() for i in range(d.preview.columnCount()))


def test_session_excludes_other_academic_terms(manager,tmp_path,qtbot):
    for prefix in ['261','271']:
        records=inspect_roster(workbook(tmp_path/(prefix+'.xlsx'),prefix+'BAECF3DBAE30500'))[0].records
        manager.import_records(records)
    b=manager.save_batch({'academic_year':'2026–2027','semester':'第一學期','exam_type':'期中'})
    room=manager.save_room({'name':'G2209','capacity':80,'enabled':1})
    d=SessionDialog(manager);qtbot.addWidget(d)
    assert d.classes.count()==1
    wrong=next(c for c in manager.classes() if c['academic_year']=='2027–2028')
    with pytest.raises(ValidationError,match='學年學期'):
        manager.create_session(b,manager.courses()[0]['id'],{'date':'2026-10-15','start':'19:00','end':'21:00'},[wrong['id']],[room])

import sqlite3
from zipfile import ZipFile
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QFileDialog,QMessageBox
from openpyxl import load_workbook
from app.database.store import Store
from app.services.manager import Manager
from app.models.records import StudentRecord,ValidationError
from app.exporters.excel import ExcelExporter
from app.ui.window import MainWindow
from app.ui.widgets import FormDialog
from app.ui.student_flags import StudentFlagReminder,StudentFlagsDialog
from conftest import setup_exam


def one_room(manager):
    sid,classes,rooms=setup_exam(manager,(2,),room_names=('G2207',))
    aid=rooms['G2207'];manager.assign(aid,classes['D'])
    student=manager.assigned(aid=aid)[0]
    return sid,aid,student


def legacy_v2(manager,path):
    manager.db.backup(path)
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE student_flags')
        db.execute('UPDATE schema_version SET version=2')
    return path


def test_flag_is_global_survives_reimport_and_identity_edits(manager):
    sid,aid,student=one_room(manager)
    before=manager.snapshot(sid)
    manager.set_student_flag(student['student_id'],'作弊：需核對座位')
    records=[StudentRecord(student['student_no'],student['chinese_name'],student['english_name'],'D',code) for code in ('BAE305','C202')]
    manager.import_records(records)
    manager.edit_student(student['student_id'],'RENAMED001','修訂姓名','UPDATED NAME')
    assert len(manager.flagged_students())==1
    assert all(r['flag_reason']=='作弊：需核對座位' for r in manager.students() if r['id']==student['student_id'])
    alert=manager.flagged_in_allocations([aid])[0]
    assert (alert['student_no'],alert['seat'],alert['room_name'])==('RENAMED001',student['seat'],'G2207')
    assert manager.snapshot(sid)==before
    manager.set_student_flag(student['student_id'],'已更新原因')
    assert manager.flagged_in_allocations([aid])[0]['flag_reason']=='已更新原因'
    manager.set_student_flag(student['student_id'],enabled=False)
    assert not manager.flagged_in_allocations([aid])


def test_flag_applies_to_new_exam_and_only_selected_rooms(manager):
    sid,aid,student=one_room(manager);manager.set_student_flag(student['student_id'],'PRIVATE')
    sid2,classes,rooms=setup_exam(manager,(1,),code='C202',dt='2026-10-15',room_names=('G2209',))
    manager.import_records([StudentRecord(student['student_no'],student['chinese_name'],student['english_name'],'D','C202')])
    second=rooms['G2209'];manager.assign(second,classes['D'])
    assert len(manager.flagged_in_allocations([second]))==1
    assert manager.flagged_in_allocations([second])[0]['code']=='C202'
    assert {r['allocation_id'] for r in manager.flagged_in_allocations([aid,second,aid])}=={aid,second}
    assert not manager.flagged_in_allocations([])


def test_flag_requires_reason_and_real_student(manager):
    _,_,student=one_room(manager)
    with pytest.raises(ValidationError,match='原因'):manager.set_student_flag(student['student_id'],'  ')
    with pytest.raises(ValidationError,match='不存在'):manager.set_student_flag('missing','作弊')
    assert not manager.flagged_students()


def test_flag_survives_deleting_last_roster_and_returning_student(manager):
    _,_,student=one_room(manager);identifier=student['student_id']
    manager.set_student_flag(identifier,'需安排座位')
    manager.delete_enrollments([student['enrollment_id']])
    assert not any(r['id']==identifier for r in manager.students())
    assert manager.flagged_students()[0]['id']==identifier
    manager.import_records([StudentRecord(student['student_no'],student['chinese_name'],student['english_name'],'A','NEW101')])
    returned=next(r for r in manager.students() if r['course_code']=='NEW101')
    assert returned['id']==identifier and returned['flag_reason']=='需安排座位'
    assert not manager.db.conn.execute('PRAGMA foreign_key_check').fetchall()


def test_v2_upgrade_backs_up_and_preserves_locked_seats_and_history(manager,tmp_path):
    sid,aid,student=one_room(manager)
    manager.special(student['id'],student['seat'],True,'前排','內部')
    snapshot=manager.snapshot(sid);history=manager.db.rows('SELECT * FROM history')
    path=legacy_v2(manager,tmp_path/'legacy.sqlite3');store=Store(path)
    try:
        assert store.upgrade_backup.exists()
        with sqlite3.connect(store.upgrade_backup) as backup:assert backup.execute('SELECT version FROM schema_version').fetchone()[0]==2
        upgraded=Manager(store)
        assert upgraded.snapshot(sid)==snapshot
        assert store.rows('SELECT * FROM history')==history
        assert store.one('SELECT version FROM schema_version')['version']==3
        upgraded.set_student_flag(student['student_id'],'持久標記')
    finally:store.close()
    reopened=Store(path)
    try:assert Manager(reopened).flagged_students()[0]['flag_reason']=='持久標記'
    finally:reopened.close()


def test_flag_backup_restore_and_legacy_restore(manager,tmp_path):
    _,_,student=one_room(manager)
    old=legacy_v2(manager,tmp_path/'old.sqlite3');old_bytes=old.read_bytes()
    manager.set_student_flag(student['student_id'],'備份標記')
    backup=manager.db.backup(tmp_path/'with_flags.sqlite3')
    manager.set_student_flag(student['student_id'],enabled=False)
    manager.db.restore(backup)
    assert manager.flagged_students()[0]['flag_reason']=='備份標記'
    safety=manager.db.restore(old)
    assert old.read_bytes()==old_bytes and not manager.flagged_students()
    with sqlite3.connect(safety) as db:assert db.execute('SELECT reason FROM student_flags').fetchone()[0]=='備份標記'


def test_flag_reason_never_exported_even_with_class_index(manager,tmp_path):
    _,aid,student=one_room(manager)
    reason='PRIVATE_FLAG_DO_NOT_PRINT_951'
    manager.set_student_flag(student['student_id'],reason)
    path=ExcelExporter(manager).generate(aid,tmp_path,include_class_index=True)
    with ZipFile(path) as archive:
        assert not any(reason.encode() in archive.read(name) for name in archive.namelist())
    wb=load_workbook(path)
    assert wb['Attendance']['C18'].value==student['student_no'];wb.close()
    assert all(reason not in r['message'] for r in manager.db.rows('SELECT * FROM generation_logs'))


def test_flag_form_and_independent_flags_list(qtbot,manager,monkeypatch):
    _,_,student=one_room(manager)
    win=MainWindow(manager);qtbot.addWidget(win)
    def edit(dialog):
        assert dialog.editors['enabled'].isChecked()
        dialog.editors['reason'].setPlainText('作弊：待安排位置')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(FormDialog,'exec',edit)
    win.student_flag_form(manager.students()[0])
    assert manager.flagged_students()[0]['flag_reason']=='作弊：待安排位置'
    win.flagged_only.setChecked(True);assert win.students_table.rowCount()==1
    assert win.seat_tree.topLevelItem(0).text(7)=='作弊：待安排位置'
    assert '特殊學生' in win.generation_table.item(0,7).text()
    flags=StudentFlagsDialog(manager,lambda r:manager.set_student_flag(r['id'],enabled=False));qtbot.addWidget(flags)
    flags.search.setText('作弊');assert flags.table.rowCount()==1
    flags.table.selectRow(0);flags.edit()
    assert not manager.flagged_students() and flags.table.rowCount()==0


def test_every_generation_reminds_even_after_previous_generation(qtbot,manager,tmp_path,monkeypatch):
    _,aid,student=one_room(manager);manager.set_student_flag(student['student_id'],'重複提醒原因')
    win=MainWindow(manager);qtbot.addWidget(win);win.check_generation(True)
    reminders=[]
    def confirm(dialog):
        reminders.append((dialog.table.item(0,1).text(),dialog.table.item(0,2).text(),dialog.table.item(0,6).text()))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(StudentFlagReminder,'exec',confirm)
    folders=iter([tmp_path/'first',tmp_path/'again'])
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(next(folders)))
    monkeypatch.setattr(QMessageBox,'information',lambda *a,**k:None)
    win.generate_selected();win.generate_selected()
    assert reminders==[('G2207',student['student_no'],'重複提醒原因')]*2
    assert len(list(tmp_path.rglob('*.xlsx')))==2


def test_reminder_can_return_to_seat_adjustment_without_export(qtbot,manager,tmp_path,monkeypatch):
    sid,aid,student=one_room(manager);manager.set_student_flag(student['student_id'],'安排前排')
    win=MainWindow(manager);qtbot.addWidget(win);win.nav.setCurrentRow(7);win.check_generation(True)
    def adjust(dialog):
        dialog.table.selectRow(0);dialog.adjust()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(StudentFlagReminder,'exec',adjust)
    def no_folder(*a,**k):raise AssertionError('Should return before choosing export folder')
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',no_folder)
    win.generate_selected()
    assert win.nav.currentRow()==6 and win.seat_room.currentData()==aid
    assert win.seat_tree.currentItem().data(0,Qt.ItemDataRole.UserRole)==student['id']
    assert not manager.db.rows('SELECT * FROM generation_logs')

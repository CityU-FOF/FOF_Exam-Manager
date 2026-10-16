import sqlite3
import pytest
from openpyxl import load_workbook
from app.services.manager import Manager
from app.models.records import StudentRecord
from app.exporters.excel import ExcelExporter
from conftest import setup_exam


def test_saved_combined_names_repaired_with_backup_and_seats_preserved(manager,tmp_path):
    sid,classes,rooms=setup_exam(manager,(1,))
    aid=rooms['G2207'];manager.assign(aid,classes['D'])
    assignment=manager.assigned(aid=aid)[0]
    manager.special(assignment['id'],assignment['seat'],True,'特殊安排','內部備註')
    old_cn='陳大文 CHAN TAI MAN';old_en='David'
    with manager.db.conn:
        manager.db.conn.execute('UPDATE students SET chinese_name=?,english_name=?,raw_name=?',
                                (old_cn,old_en,old_cn+'\n'+old_en))
    manager.complete(sid)
    seats=manager.db.rows('SELECT * FROM assignments')
    history=manager.db.rows('SELECT * FROM history')
    upgraded=Manager(manager.db)
    assert upgraded.name_repair_count==1
    with sqlite3.connect(upgraded.name_repair_backup) as backup:
        assert backup.execute('SELECT chinese_name,english_name FROM students').fetchone()==(old_cn,old_en)
    student=upgraded.students()[0]
    assert (student['chinese_name'],student['english_name'])==('陳大文','CHAN TAI MAN')
    assert student['raw_name']==old_cn+'\n'+old_en
    assert upgraded.db.rows('SELECT * FROM assignments')==seats
    assert upgraded.db.rows('SELECT * FROM history')==history
    assert upgraded.sessions()[0]['status']=='草稿'
    wb=load_workbook(ExcelExporter(upgraded).generate(aid,tmp_path/'output'))
    for sheet in wb:
        assert sheet['D18'].value=='陳大文'
        assert sheet.cell(18,5 if sheet.title=='Attendance' else 6).value=='CHAN TAI MAN'
    assert wb['Attendance']['G17'].value=='Remark'
    wb.close()
    again=Manager(manager.db)
    assert again.name_repair_count==0 and again.name_repair_backup is None
    assert len(list(manager.db.path.parent.glob('before_name_split_*.sqlite3')))==1


def test_name_repair_preserves_manual_names_and_ambiguous_input(manager):
    records=[StudentRecord(str(i),cn,en,'D','BAE305') for i,(cn,en) in enumerate([
        ('陳大文','CUSTOM ENGLISH NAME'),
        ('陳（大文） / CHAN 123','David'),
        ('','ANA MARIA SILVA'),
        ('ANA MARIA SILVA','Ana'),
    ])]
    manager.import_records(records)
    upgraded=Manager(manager.db)
    assert upgraded.name_repair_count==1
    by_id={s['student_no']:s for s in upgraded.students()}
    for i in range(3):
        assert (by_id[str(i)]['chinese_name'],by_id[str(i)]['english_name'])==(records[i].chinese_name,records[i].english_name)
    assert (by_id['3']['chinese_name'],by_id['3']['english_name'])==('','ANA MARIA SILVA')
    assert by_id['3']['raw_name']=='ANA MARIA SILVA\nAna'


def test_name_repair_backup_failure_keeps_names_unchanged(manager,monkeypatch):
    manager.import_records([StudentRecord('001','陳大文 CHAN TAI MAN','David','D','BAE305')])
    before=manager.db.rows('SELECT * FROM students')
    def fail_backup(path):
        raise PermissionError('backup unavailable')
    monkeypatch.setattr(manager.db,'backup',fail_backup)
    with pytest.raises(PermissionError):Manager(manager.db)
    assert manager.db.rows('SELECT * FROM students')==before

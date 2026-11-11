from pathlib import Path
import sqlite3
import pytest
from openpyxl import load_workbook
from app.models.records import StudentRecord,ValidationError
from app.exporters.excel import ExcelExporter
from conftest import setup_exam
from app.database.store import Store


def test_failed_export_keeps_original_and_removes_temp(manager,tmp_path,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(3,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    exp=ExcelExporter(manager);path=exp.generate(aid,tmp_path);before=path.read_bytes()
    def invalid(*args):raise ValidationError('verification deliberately failed')
    monkeypatch.setattr(exp,'verify',invalid)
    with pytest.raises(ValidationError):exp.generate(aid,tmp_path,'overwrite')
    assert path.read_bytes()==before
    assert not list(tmp_path.glob('.fof-*'))


def test_import_transaction_rolls_back_prior_valid_row(manager):
    manager.import_records([StudentRecord('EXIST','原名','ORIGINAL','E','C101')])
    with pytest.raises(ValidationError):
        manager.import_records([StudentRecord('NEW','新增','NEW','D','C101'),StudentRecord('EXIST','變更','CHANGED','D','C101')])
    assert len(manager.students())==1
    assert manager.students()[0]['chinese_name']=='原名'
    assert not any(c['name']=='D' for c in manager.classes())


def test_header_changes_sync_both_sheets_and_draft(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(3,));aid=rooms['G2207'];manager.assign(aid,cl['D']);manager.complete(sid)
    s=manager.sessions()[0]
    manager.update_session(sid,dict(date='2027-01-05',start='09:00',end='11:00',teachers='甲老師、乙老師',intake='2025-08'))
    c=manager.courses()[0]
    manager.save_course(dict(code=c['code'],name_cn='修訂公司金融',name_en='Updated Corporate Finance'),c['id'])
    assert manager.sessions()[0]['status']=='草稿'
    path=ExcelExporter(manager).generate(aid,tmp_path);wb=load_workbook(path,data_only=True)
    for sheet in wb:
        assert sheet['G12'].value.date().isoformat()=='2027-01-05'
        assert sheet['G14'].value=='09:00-11:00'
        assert sheet['E10'].value=='甲老師、乙老師'
        assert sheet['D10'].value=='2025-08'
        assert '修訂公司金融' in sheet['A8'].value
        assert not sheet.protection.sheet
        assert sheet.freeze_panes is None
        assert sheet.sheet_view.topLeftCell == 'A1'
        assert sheet.sheet_view.selection[0].activeCell == 'A1'
        assert sheet.sheet_view.selection[0].pane is None
        assert sheet['A1'].value == '澳門城市大學'
        assert sheet['A2'].value == 'CITY UNIVERSITY OF MACAU'
        assert sheet['A3'].value == '應用經濟學學士學位課程（中文學制）'
        assert not any(sheet.row_dimensions[i].hidden for i in range(1,18))
        assert sheet['E10'].alignment.horizontal == 'right'
        assert sheet.row_dimensions[10].height == 16.5
        assert not sheet['C18'].protection.locked
    assert wb['Attendance']['G16'].value=='備注'
    assert wb['Attendance']['G17'].value=='Remark'
    assert wb['Seat Plan']['G16'].value is None
    wb.close()


def test_teacher_or_english_header_required(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(1,));manager.assign(rooms['G2207'],cl['D'])
    c=manager.courses()[0];manager.save_course(dict(code=c['code'],name_cn=c['name_cn'],name_en=''),c['id'])
    with pytest.raises(ValidationError,match='科目英文名稱'):ExcelExporter(manager).generate(rooms['G2207'],tmp_path)


def test_undo_cannot_steal_merged_seat(manager):
    sid,cl,rooms=setup_exam(manager,(1,),capacity=2,merge=True,room_names=('G2207',));aid=rooms['G2207']
    manager.assign(aid,cl['D']);manager.unassign([manager.assigned(sid)[0]['id']])
    sid2,cl2,rooms2=setup_exam(manager,(1,),capacity=2,code='C202',merge=True,room_names=('G2207',))
    manager.assign(rooms2['G2207'],cl2['D'])
    with pytest.raises(ValidationError,match='座位衝突'):manager.undo(sid)
    assert not manager.assigned(sid) and len(manager.pending(sid))==1


def test_merged_room_capacity_edit_rejected(manager):
    sid,cl,rooms=setup_exam(manager,(3,),capacity=5,merge=True,room_names=('G2207',));manager.assign(rooms['G2207'],cl['D'])
    s2,c2,r2=setup_exam(manager,(2,),capacity=5,code='C202',merge=True,room_names=('G2207',));manager.assign(r2['G2207'],c2['D'])
    room=manager.rooms()[0]
    with pytest.raises(ValidationError,match='合場'):manager.save_room(dict(name=room['name'],capacity=4,enabled=1),room['id'])
    assert manager.rooms()[0]['capacity']==5


def test_copy_setting_has_no_assignments_and_shared_exam(manager):
    sid,cl,rooms=setup_exam(manager,(3,));manager.assign(rooms['G2207'],cl['D'])
    new=manager.copy_session(sid)
    assert len(manager.pending(new))==3 and not manager.assigned(new)
    assert len(manager.allocations(new))==2
    assert manager.db.one('SELECT COUNT(*) n FROM exams')['n']==1


def test_batch_continues_after_export_failure(manager,tmp_path,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(2,2));manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    exp=ExcelExporter(manager);real=exp.generate
    def generate(aid,*args,**kwargs):
        if aid==rooms['G2207']:raise PermissionError('cannot write first file')
        return real(aid,*args,**kwargs)
    monkeypatch.setattr(exp,'generate',generate)
    result=exp.batch(list(rooms.values()),tmp_path)
    assert [r[1] for r in result]==['失敗','成功']
    assert len(list(tmp_path.glob('*.xlsx')))==1


def test_unrelated_database_not_modified(tmp_path):
    path=tmp_path/'other.sqlite3'
    with sqlite3.connect(path) as conn:conn.execute('CREATE TABLE original(x)')
    with pytest.raises(ValidationError):Store(path)
    with sqlite3.connect(path) as conn:
        assert [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]==['original']


def test_restore_wrong_columns_keeps_current_database(manager,tmp_path):
    manager.import_records([StudentRecord('001','測試','TEST','D','C101')])
    target=tmp_path/'badshape.sqlite3';manager.db.backup(target)
    with sqlite3.connect(target) as conn:
        conn.execute('ALTER TABLE courses RENAME COLUMN name_en TO missing')
    with pytest.raises(ValidationError,match='欄位'):manager.db.restore(target)
    assert len(manager.students())==1


def test_deployment_selfcheck(qapp,tmp_path):
    from app.utils.selfcheck import selfcheck
    report=selfcheck(qapp,tmp_path/'check')
    assert report['status']=='passed' and report['ui_pages']==10
    assert Path(report['output']).exists()


def test_completed_status_and_generation_version(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(1,1));manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    assert manager.dashboard()['complete']==0
    manager.complete(sid);assert manager.dashboard()['complete']==1
    exp=ExcelExporter(manager);exp.generate(rooms['G2207'],tmp_path)
    assert manager.sessions()[0]['status']=='已完成編排'
    exp.generate(rooms['G2209'],tmp_path);assert manager.sessions()[0]['status']=='已生成文件'
    manager.update_session(sid,dict(date='2026-10-15',start='19:00',end='21:00',teachers='江宇',intake='2026-08'))
    assert manager.dashboard()['complete']==0
    exp.generate(rooms['G2207'],tmp_path);assert manager.sessions()[0]['status']=='已完成編排'

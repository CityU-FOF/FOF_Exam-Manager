from pathlib import Path
import sqlite3
import socket
import pytest
from openpyxl import load_workbook
from app.models.records import ValidationError,CapacityError,StudentRecord
from app.database.store import Store
from app.services.manager import Manager
from app.exporters.excel import ExcelExporter
from conftest import setup_exam,assign_four


def test_four_class_acceptance(manager,tmp_path):
    sid,classes,rooms=setup_exam(manager);assign_four(manager,sid,classes,rooms)
    assert [(a['room_name'],a['count']) for a in manager.allocations(sid)]==[('G2207',63),('G2209',64)]
    assert len(manager.assigned(sid))==127 and not manager.pending(sid)
    manager.complete(sid)
    result=ExcelExporter(manager).batch(list(rooms.values()),tmp_path/'output')
    assert [r[1] for r in result]==['成功','成功']
    for aid,_,path in result:
        wb=load_workbook(path,data_only=True)
        rows=manager.assigned(aid=aid)
        for s in wb:
            assert s['D14'].value==len(rows)
            assert [s.cell(i,3).value for i in range(18,18+len(rows))]==[r['student_no'] for r in rows]
            assert [s.cell(i,2).value for i in range(18,18+len(rows))]==[r['seat'] for r in rows]
            assert s.print_title_rows is None
            assert s.print_title_cols is None
            assert not s.row_breaks.brk
            assert s.sheet_properties.pageSetUpPr.autoPageBreaks
            assert s.page_setup.fitToWidth==1
            assert s.page_setup.fitToHeight==0
            assert s.page_setup.scale is None
            assert s.page_margins.left==pytest.approx(1.8/2.54)
            assert s.page_margins.right==pytest.approx(1.8/2.54)
            assert s.page_margins.top==pytest.approx(1.9/2.54)
            assert s.page_margins.bottom==pytest.approx(1.9/2.54)
            for row in range(18,18+len(rows)):
                for col in [4,5 if s.title=='Attendance' else 6]:
                    assert s.cell(row,col).alignment.horizontal=='center'
                    assert s.cell(row,col).alignment.vertical=='center'
            assert s['D18'].font.name=='標楷體'
            assert s['D18'].font.sz==12
        assert wb['Seat Plan']['C15'].value is None
        assert wb['Seat Plan']['F16'].value is None
        wb.close()


def test_capacity_explicit_split_and_cancel(manager):
    sid,classes,rooms=setup_exam(manager,(70,25),room_names=('G2207',))
    aid=rooms['G2207'];manager.assign(aid,classes['D'])
    with pytest.raises(CapacityError) as e:manager.assign(aid,classes['E'])
    assert e.value.remaining==10 and e.value.requested==25
    assert len(manager.pending(sid,classes['E']))==25
    first=manager.pending(sid,classes['E'])[:10]
    manager.assign(aid,classes['E'],[s['student_id'] for s in first])
    assert len(manager.pending(sid,classes['E']))==15
    assert len(manager.assigned(sid))==80


def test_order_restart_undo_redo(manager):
    sid,classes,rooms=setup_exam(manager,(5,));aid=rooms['G2207'];manager.assign(aid,classes['D'])
    initial=manager.assigned(aid=aid);order=[r['id'] for r in initial]
    order.insert(1,order.pop());manager.reorder(aid,order)
    assert [r['id'] for r in manager.assigned(aid=aid)]==order
    assert [r['seat'] for r in manager.assigned(aid=aid)]==['001','002','003','004','005']
    second=Store(manager.db.path);m=Manager(second)
    assert [r['id'] for r in m.assigned(aid=aid)]==order
    m.undo(sid);assert [r['id'] for r in m.assigned(aid=aid)]==[r['id'] for r in initial]
    m.undo(sid,True);assert [r['id'] for r in m.assigned(aid=aid)]==order
    second.close()


@pytest.mark.parametrize('count',[1,30,63,64,65,80,120])
def test_dynamic_rows(manager,tmp_path,count):
    sid,classes,rooms=setup_exam(manager,(count,),capacity=max(count,80));aid=rooms['G2207'];manager.assign(aid,classes['D'])
    path=ExcelExporter(manager).generate(aid,tmp_path)
    wb=load_workbook(path,data_only=False)
    assert 17+count <= wb['Attendance'].max_row <= 17+count+6
    assert wb['Seat Plan'].max_row==17+count
    for s in wb:
        assert len([s.cell(i,3).value for i in range(18,s.max_row+1) if s.cell(i,3).value])==count
        assert not any(c.data_type=='f' for row in s for c in row)
    wb.close()


def test_add_remove_64_65_63(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(64,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    exporter=ExcelExporter(manager);exporter.generate(aid,tmp_path)
    record=StudentRecord('NEW0001','新增學生','NEW STUDENT','D','BAE305',source='manual')
    manager.import_records([record]);assert len(manager.pending(sid))==1
    manager.assign(aid,cl['D']);assert len(manager.assigned(sid))==65
    exporter.generate(aid,tmp_path,'overwrite')
    removed=manager.assigned(aid=aid)[-2:];manager.unassign([r['id'] for r in removed])
    for r in removed:manager.deactivate_enrollment(r['enrollment_id'])
    assert not manager.validate(sid)
    path=exporter.generate(aid,tmp_path,'overwrite');assert load_workbook(path,data_only=True)['Attendance']['D14'].value==63


def test_split_cross_rooms_and_move(manager):
    sid,classes,rooms=setup_exam(manager,(35,));pending=manager.pending(sid)
    manager.assign(rooms['G2207'],classes['D'],[s['student_id'] for s in pending[:20]])
    manager.assign(rooms['G2209'],classes['D'])
    assert len(manager.assigned(sid))==35 and not manager.pending(sid)
    assert len({r['student_id'] for r in manager.assigned(sid)})==35
    first=manager.assigned(aid=rooms['G2207'])[0]
    manager.move_students([first['id']],rooms['G2209'])
    assert [a['count'] for a in manager.allocations(sid)]==[19,16]
    assert {r['class_name'] for r in manager.assigned(sid)}=={'D'}
    manager.undo(sid);assert [a['count'] for a in manager.allocations(sid)]==[20,15]


def test_batch_ten_output_and_conflict_policies(manager,tmp_path):
    aids=[]
    for i in range(5):
        sid,cl,rooms=setup_exam(manager,(2,2),code=f'BAE{i:03d}',dt=f'2026-10-{14+i:02d}')
        manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E']);aids+=list(rooms.values())
    exp=ExcelExporter(manager);results=exp.batch(aids,tmp_path)
    assert len(results)==10 and all(r[1]=='成功' for r in results)
    assert len(list(tmp_path.glob('*.xlsx')))==10
    with pytest.raises(FileExistsError):exp.generate(aids[0],tmp_path)
    assert exp.generate(aids[0],tmp_path,'skip') is None
    renamed=exp.generate(aids[0],tmp_path,'rename');assert renamed.stem.endswith('_2')


def test_reimport_diff_preserves_seats(manager):
    sid,cl,rooms=setup_exam(manager,(5,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    before=manager.assigned(aid=aid)
    updated=[StudentRecord(r['student_no'],r['chinese_name'],r['english_name'],'D','BAE305') for r in before[:-1]]
    updated[0].chinese_name='姓名已修正'
    updated.append(StudentRecord('ADDED123','新增','ADDED','D','BAE305'))
    diff=manager.import_diff(updated);assert {k:len(v) for k,v in diff.items()}=={'added':1,'removed':1,'changed':1,'unchanged':3}
    manager.import_records(updated,True)
    assert [(r['id'],r['seat']) for r in manager.assigned(aid=aid)]==[(r['id'],r['seat']) for r in before]
    assert any('已移除' in e for e in manager.validate(sid))
    manager.unassign([before[-1]['id']]);manager.assign(aid,cl['D']);assert not manager.validate(sid)


def test_multi_course_identity_and_same_name(manager):
    records=[StudentRecord('00001','同名','SAME','D','C101'),StudentRecord('00002','同名','SAME','D','C101'),
             StudentRecord('00001','同名','SAME','F','C102')]
    manager.import_records(records)
    assert manager.db.one('SELECT COUNT(*) n FROM students')['n']==2
    assert len(manager.students())==3
    assert {r['student_no'] for r in manager.students()}=={'00001','00002'}


def test_room_and_student_overlap(manager):
    sid,cl,rooms=setup_exam(manager,(2,));manager.assign(rooms['G2207'],cl['D'])
    s=manager.sessions()[0];cids=[cl['D']]
    with pytest.raises(ValidationError,match='考場已被'):manager.create_session(s['batch_id'],s['course_id'],dict(date=s['date'],start='20:00',end='22:00',teachers='T'),cids,[manager.rooms()[0]['id']])
    assert len(manager.sessions())==1
    new_room=manager.save_room(dict(name='OTHER',capacity=80,enabled=1))
    sid2=manager.create_session(s['batch_id'],s['course_id'],dict(date=s['date'],start='20:00',end='22:00',teachers='T'),cids,[new_room])
    with pytest.raises(ValidationError,match='學生同一時段'):manager.assign(manager.allocations(sid2)[0]['id'],cl['D'])
    assert not manager.assigned(sid2)
    manager.update_session(sid2,dict(date=s['date'],start='21:00',end='22:00',teachers='T'))
    manager.assign(manager.allocations(sid2)[0]['id'],cl['D'])


def test_merged_capacity_and_seat_uniqueness(manager):
    sid,cl,rooms=setup_exam(manager,(3,),capacity=5,merge=True,room_names=('G2207',));manager.assign(rooms['G2207'],cl['D'])
    other,c2,r2=setup_exam(manager,(3,),capacity=5,code='C201',merge=True,room_names=('G2207',))
    with pytest.raises(CapacityError):manager.assign(r2['G2207'],c2['D'])
    manager.assign(r2['G2207'],c2['D'],[s['student_id'] for s in manager.pending(other)[:2]])
    assert [s['seat'] for s in manager.assigned(other)]==['004','005']
    assert not manager.validate(sid)


def test_lock_preserved_and_internal_notes_private(manager,tmp_path,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(5,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    rows=manager.assigned(aid=aid);last=rows[-1]
    manager.special(last['id'],'005',True,'需要前排','PRIVATE_INTERNAL_REASON')
    order=[r['id'] for r in rows];order.insert(1,order.pop());manager.reorder(aid,order)
    assert next(r for r in manager.assigned(aid=aid) if r['id']==last['id'])['seat']=='005'
    with pytest.raises(ValidationError,match='解除'):manager.unassign([last['id']])
    def deny(*args,**kwargs):raise AssertionError('Network attempted')
    monkeypatch.setattr(socket,'socket',deny)
    path=ExcelExporter(manager).generate(aid,tmp_path)
    wb=load_workbook(path)
    assert not any('PRIVATE_INTERNAL_REASON' in str(c.value) or '需要前排' in str(c.value) for s in wb for row in s for c in row)
    wb.close()


def test_reserved_seats_and_duplicates(manager):
    sid,cl,rooms=setup_exam(manager,(3,));aid=rooms['G2207']
    al=next(a for a in manager.allocations(sid) if a['id']==aid)
    room=next(r for r in manager.rooms() if r['id']==al['room_id'])
    values={k:room[k] for k in ['name','capacity','enabled','notes']};values['usable_seats']='001,003,008'
    manager.save_room(values,room['id']);manager.assign(aid,cl['D'])
    assert [r['seat'] for r in manager.assigned(aid=aid)]==['001','003','008']
    rows=manager.assigned(aid=aid)
    with pytest.raises(ValidationError,match='已有學生'):manager.special(rows[0]['id'],'003',False,'','')
    with pytest.raises(ValidationError):manager.save_room(dict(values,usable_seats='001,001'),room['id'])


def test_backup_restore_protects_current_data(manager,tmp_path):
    manager.import_records([StudentRecord('001','甲','A','D','C101')])
    target=tmp_path/'backup.sqlite3';manager.db.backup(target)
    with pytest.raises(FileExistsError):manager.db.backup(target)
    manager.import_records([StudentRecord('002','乙','B','D','C101')])
    safety=manager.db.restore(target)
    assert safety.exists() and len(manager.students())==1
    with sqlite3.connect(safety) as c:assert c.execute('SELECT COUNT(*) FROM students').fetchone()[0]==2
    bad=tmp_path/'bad.sqlite3'
    with sqlite3.connect(bad) as c:c.execute('CREATE TABLE bad(x)')
    with pytest.raises(ValidationError):manager.db.restore(bad)
    assert len(manager.students())==1


def test_bad_import_transaction_and_unassigned_export(manager,tmp_path):
    record=StudentRecord('001','甲','A','D','C101')
    with pytest.raises(ValidationError):manager.import_records([record,record])
    assert not manager.students()
    sid,cl,rooms=setup_exam(manager,(3,))
    with pytest.raises(ValidationError,match='未分配'):ExcelExporter(manager).generate(rooms['G2207'],tmp_path)


def test_formula_injection_stays_text(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(1,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    st=manager.assigned(sid)[0];manager.edit_student(st['student_id'],st['student_no'],'=HYPERLINK("x")','+COMMAND')
    path=ExcelExporter(manager).generate(aid,tmp_path);wb=load_workbook(path)
    assert wb['Attendance']['D18'].value=='=HYPERLINK("x")' and wb['Attendance']['D18'].data_type=='s'
    assert wb['Seat Plan']['D18'].data_type=='s'
    wb.close()

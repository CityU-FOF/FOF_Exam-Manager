import json
import sqlite3
import pytest
from PySide6.QtCore import Qt,QMimeData,QPointF
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QMessageBox,QInputDialog
from app.importers.rooms import parse_rooms
from app.models.records import StudentRecord,ValidationError
from app.ui.room_paste import RoomPasteDialog
from app.ui.window import MainWindow
from app.ui.widgets import ClassCards,AssignedClassCards
from app.exporters.excel import ExcelExporter
from conftest import setup_exam


ROOMS='''| 展覽廳 | 216 |
| ------ | --- |
| L105 | 75 |
| T103 | 89 |
| N204 | 61 |
| 展覽廳 | 216 |
| L105 | 75 |
| N202 | 84 |
| 展覽廳 | 216 |
| T103 | 89 |
| T106 | 89 |
| N203 | 66 |
| L105 | 75 |
| N202 | 84 |
| N204 | 61 |
| NLG102 | 66 |
| NLG103 | 34 |
| NLG104 | 60 |
| L107 | 59 |'''


@pytest.mark.parametrize('text,html',[
    (ROOMS,''),('考場\t最多人數\n展覽廳\t216\nL105\t75',''),
    ('展覽廳 216\nL105 75',''),('展覽廳,216\nL105,75',''),
    ('','<table><tr><th>考場</th><th>容量</th></tr><tr><td>展覽廳</td><td>216</td></tr><tr><td>L105</td><td>75</td></tr></table>'),
])
def test_room_paste_formats_and_deduplication(text,html):
    rows=parse_rooms(text,html)
    assert len(rows)==(11 if text==ROOMS else 2)
    assert (rows[0].name,rows[0].capacity)==('展覽廳','216')
    assert (rows[1].name,rows[1].capacity)==('L105','75')
    assert not any(r.issues for r in rows)


def test_room_paste_conflicting_capacity_not_guessed():
    rows=parse_rooms('L105\t75\nL105\t80\nN204\twrong')
    assert len(rows)==3 and all(r.issues for r in rows)
    with pytest.raises(ValidationError):parse_rooms('')


def test_room_batch_validation_is_atomic_and_preserves_existing(manager):
    sid,cl,rooms=setup_exam(manager,(3,));manager.assign(rooms['G2207'],cl['D'])
    existing=next(r for r in manager.rooms() if r['name']=='G2207')
    manager.save_room(dict(name='G2207',capacity=80,enabled=0,notes='保留備註'),existing['id'])
    before=manager.rooms()
    with pytest.raises(ValidationError):
        manager.save_rooms([dict(name='NEW',capacity=20),dict(name='G2207',capacity=2)])
    assert manager.rooms()==before
    with pytest.raises(ValidationError):manager.save_rooms([dict(name='l105',capacity=75),dict(name='L105',capacity=80)])
    assert manager.rooms()==before
    manager.save_rooms([dict(name='G2207',capacity=100),dict(name='l105',capacity=75)])
    updated=next(r for r in manager.rooms() if r['id']==existing['id'])
    assert (updated['capacity'],updated['enabled'],updated['notes'])==(100,0,'保留備註')
    manager.save_rooms([dict(name='L105',capacity=75)])
    assert len([r for r in manager.rooms() if r['name']=='L105'])==1


def test_room_paste_preview_save(qtbot,manager,monkeypatch):
    dialog=RoomPasteDialog(manager);qtbot.addWidget(dialog)
    dialog.text.setPlainText(ROOMS);dialog.analyze()
    assert dialog.table.rowCount()==11
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    dialog.commit()
    assert len(manager.rooms())==11
    assert len(manager.seat_pool(next(r for r in manager.rooms() if r['name']=='展覽廳')))==216


def test_delete_roster_keeps_other_course_identity_and_other_room(manager):
    sid,cl,rooms=setup_exam(manager,(3,2))
    manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    member=manager.assigned(aid=rooms['G2207'])[0]
    manager.import_records([StudentRecord(member['student_no'],member['chinese_name'],member['english_name'],'A','C202')])
    manager.special(member['id'],member['seat'],True,'','')
    untouched=manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))
    ids=[r['id'] for r in manager.db.rows('SELECT id FROM enrollments WHERE class_id=?',(cl['D'],))]
    manager.delete_enrollments(ids)
    assert manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))==untouched
    assert not manager.db.one('SELECT id FROM classes WHERE id=?',(cl['D'],))
    assert not manager.db.rows('SELECT * FROM history WHERE session_id=?',(sid,))
    assert len(manager.students())==3
    assert [r['course_code'] for r in manager.students() if r['student_no']==member['student_no']]==['C202']
    assert not manager.validate(sid)
    backup=next(manager.db.path.parent.glob('before_roster_delete_*.sqlite3'))
    with sqlite3.connect(backup) as db:assert db.execute('SELECT COUNT(*) FROM assignments').fetchone()[0]==5
    assert not manager.db.conn.execute('PRAGMA foreign_key_check').fetchall()


def test_delete_generation_allocation_keeps_other_room_and_existing_excel(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(2,2))
    for name,cid in zip(rooms,cl.values()):manager.assign(rooms[name],cid)
    file=ExcelExporter(manager).generate(rooms['G2207'],tmp_path/'export')
    untouched=manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))
    manager.delete_allocations([rooms['G2207']])
    assert file.exists() and len(manager.pending(sid))==2
    assert manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))==untouched
    assert len(manager.rooms())==2 and len(manager.allocations(sid))==1
    assert manager.db.one('SELECT allocation_id FROM generation_logs')['allocation_id'] is None
    assert not manager.db.rows('SELECT * FROM history WHERE session_id=?',(sid,))
    assert list(manager.db.path.parent.glob('before_allocation_delete_*.sqlite3'))
    assert not manager.db.conn.execute('PRAGMA foreign_key_check').fetchall()


def test_return_class_native_drop_only_affects_source_room(qtbot,manager,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(4,2))
    pending=manager.pending(sid,cl['D'])
    manager.assign(rooms['G2207'],cl['D'],[r['student_id'] for r in pending[:2]])
    manager.assign(rooms['G2209'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    untouched=manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))
    win=MainWindow(manager);qtbot.addWidget(win);win.select_session(sid,5)
    assert win.room_cards.findChildren(AssignedClassCards)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    mime=QMimeData();mime.setData(ClassCards.RETURN_MIME,json.dumps(dict(allocation_id=rooms['G2207'],class_id=cl['D'],session_id=sid)).encode())
    event=QDropEvent(QPointF(10,10),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    win.class_cards.dropEvent(event)
    assert event.isAccepted() and len(manager.pending(sid,cl['D']))==2
    assert manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(rooms['G2209'],))==untouched


def test_return_class_button_and_locked_seat_protection(qtbot,manager,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(2,));manager.assign(rooms['G2207'],cl['D'])
    row=manager.assigned(sid)[0];manager.special(row['id'],row['seat'],True,'','')
    before=manager.snapshot(sid)
    win=MainWindow(manager);qtbot.addWidget(win)
    for i in range(win.room_cards.count()):
        if win.room_cards.item(i).data(Qt.ItemDataRole.UserRole)==rooms['G2207']:win.room_cards.setCurrentRow(i)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:('D 班',True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    with pytest.raises(ValidationError,match='鎖定'):win.return_room_class()
    assert manager.snapshot(sid)==before
    manager.special(row['id'],row['seat'],False,'','')
    win.return_room_class()
    assert len(manager.pending(sid))==2


def test_student_filters_and_delete_cancel(qtbot,manager,monkeypatch):
    setup_exam(manager,(2,))
    manager.import_records([StudentRecord('NEW','測試','TEST','4B','C202',source='other.xlsx',academic_year='2027–2028',semester='第二學期')])
    win=MainWindow(manager);qtbot.addWidget(win)
    assert win.students_table.rowCount()==3
    win.student_year.setCurrentIndex(win.student_year.findData('2027–2028'))
    assert win.students_table.rowCount()==1 and '1 筆' in win.class_counts.text()
    win.student_term.setCurrentIndex(win.student_term.findData('第二學期'))
    win.student_source.setCurrentIndex(win.student_source.findData('other.xlsx'))
    assert win.students_table.rowCount()==1
    win.students_table.selectRow(0)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.No)
    win.delete_students();assert len(manager.students())==3
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    win.delete_students();assert len(manager.students())==2
    win.clear_student_filters();assert win.students_table.rowCount()==2


def test_generation_grouping_sort_filter_and_delete(qtbot,manager,monkeypatch):
    first,cl,rooms=setup_exam(manager,(1,),code='BAE409')
    second,_,_=setup_exam(manager,(1,),code='BAE305',dt='2026-10-15')
    with manager.db.conn:
        for aid,created in [(rooms['G2207'],'2026-10-16T10:00:00'),(rooms['G2209'],'2026-10-16T12:00:00')]:
            manager.db.conn.execute('INSERT INTO generation_logs VALUES(?,?,?,?,?,?)',(aid,aid,created,'unused.xlsx','成功',''))
        manager.db.conn.execute("UPDATE sessions SET modified='2026-10-16T11:00:00' WHERE id=?",(second,))
        manager.db.conn.execute("UPDATE sessions SET modified='2026-10-16T13:00:00' WHERE id=?",(first,))
    win=MainWindow(manager);qtbot.addWidget(win)
    def displayed():return [win.generation_table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(win.generation_table.rowCount())]
    for sort in ['batch','modified','generated']:
        win.gen_sort.setCurrentIndex(win.gen_sort.findData(sort))
        rows=displayed()
        assert rows[0]['session_id']==rows[1]['session_id']
        assert rows[2]['session_id']==rows[3]['session_id']
        if sort!='batch':assert rows[0]['session_id']==first
    win.gen_filters[0].setText('BAE305');assert len(displayed())==2
    target=displayed()[0]['id'];win.generation_table.item(0,0).setCheckState(Qt.CheckState.Checked)
    win.gen_sort.setCurrentIndex(0)
    assert any(win.generation_table.item(i,0).checkState()==Qt.CheckState.Checked for i in range(2))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    win.delete_generation()
    assert target not in {a['id'] for a in manager.allocations()}
    assert len(displayed())==1


def test_old_expected_counts_no_longer_block_generation(manager):
    sid,cl,rooms=setup_exam(manager,(1,));manager.assign(rooms['G2207'],cl['D'])
    with manager.db.conn:manager.db.conn.execute('UPDATE classes SET expected=999')
    assert not manager.validate(sid)

import pytest
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QDialog
from app.models.records import ValidationError
from app.ui.window import MainWindow,SessionDialog
from app.ui.widgets import AssignedClassCards
from app.exporters.excel import ExcelExporter
from openpyxl import load_workbook
from conftest import setup_exam


def values(manager,sid):return next(s for s in manager.sessions() if s['id']==sid)


def test_room_replacement_preserves_assignments_locks_and_exports(manager,tmp_path):
    sid,cl,rooms=setup_exam(manager,(3,2))
    manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    student=manager.assigned(aid=rooms['G2207'])[0]
    manager.special(student['id'],'070',True,'前排','私有備註')
    before=manager.snapshot(sid)
    target=manager.save_room(dict(name='T106',capacity=80,enabled=1))
    manager.update_session(sid,values(manager,sid),{rooms['G2207']:target})
    assert manager.snapshot(sid)==before
    assert next(a for a in manager.allocations(sid) if a['id']==rooms['G2207'])['room_name']=='T106'
    wb=load_workbook(ExcelExporter(manager).generate(rooms['G2207'],tmp_path))
    assert all(s['D12'].value=='T106' for s in wb);wb.close()
    assert not manager.db.conn.execute('PRAGMA foreign_key_check').fetchall()


def test_swap_add_and_remove_rooms_atomically(manager):
    sid,cl,rooms=setup_exam(manager,(2,2))
    for name,cid in zip(rooms,cl.values()):manager.assign(rooms[name],cid)
    original=manager.snapshot(sid)
    a,b=manager.allocations(sid)
    master=manager.rooms()
    manager.update_session(sid,values(manager,sid),{a['id']:b['room_id'],b['id']:a['room_id']})
    assert manager.snapshot(sid)==original and manager.rooms()==master
    new=manager.save_room(dict(name='NEW',capacity=80,enabled=1))
    untouched=manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(b['id'],))
    manager.update_session(sid,values(manager,sid),{a['id']:None},[new])
    assert len(manager.pending(sid))==2
    assert manager.db.rows('SELECT * FROM assignments WHERE allocation_id=?',(b['id'],))==untouched
    assert len(manager.allocations(sid))==2
    assert not manager.db.rows('SELECT * FROM history WHERE session_id=?',(sid,))
    assert list(manager.db.path.parent.glob('before_session_rooms_*.sqlite3'))


@pytest.mark.parametrize('mode',['capacity','locked_seat','disabled','duplicate','empty','conflict'])
def test_invalid_room_change_rolls_back_date_and_all_rooms(manager,mode):
    sid,cl,rooms=setup_exam(manager,(3,1))
    manager.assign(rooms['G2207'],cl['D']);manager.assign(rooms['G2209'],cl['E'])
    target=manager.save_room(dict(name='NEW',capacity=2 if mode=='capacity' else 80,enabled=mode!='disabled'))
    if mode=='locked_seat':
        r=manager.assigned(sid)[0];manager.special(r['id'],'079',True,'','')
        manager.save_room(dict(name='NEW',capacity=40,enabled=1),target)
    if mode=='conflict':setup_exam(manager,(1,),code='C202',dt='2026-11-10',room_names=('NEW',))
    before=manager.snapshot(sid);allocations=manager.allocations(sid);session=values(manager,sid)
    masters=manager.rooms();history=manager.db.rows('SELECT * FROM history')
    changes={rooms['G2207']:target}
    if mode=='duplicate':changes={rooms['G2207']:allocations[1]['room_id']}
    if mode=='empty':changes={aid:None for aid in rooms.values()}
    with pytest.raises(ValidationError):manager.update_session(sid,dict(session,date='2026-11-10'),changes)
    assert manager.snapshot(sid)==before and manager.allocations(sid)==allocations
    assert values(manager,sid)==session and manager.rooms()==masters
    assert manager.db.rows('SELECT * FROM history')==history


def test_session_editor_keeps_current_rooms_and_adds_replacement(qtbot,manager,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(2,));manager.assign(rooms['G2207'],cl['D'])
    target=manager.save_room(dict(name='T106',capacity=80,enabled=1))
    win=MainWindow(manager);qtbot.addWidget(win)
    def edit(dialog):
        assert dialog.room_replacements[rooms['G2207']].currentData()==manager.db.one('SELECT room_id FROM allocations WHERE id=?',(rooms['G2207'],))['room_id']
        assert dialog.checked(dialog.rooms)==[]
        choice=dialog.room_replacements[rooms['G2207']]
        choice.setCurrentIndex(choice.findData(target))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(SessionDialog,'exec',edit)
    win.edit_session(sid)
    assert next(a for a in manager.allocations(sid) if a['id']==rooms['G2207'])['room_name']=='T106'
    assert len(manager.assigned(sid))==2


def test_room_class_rows_fully_visible_and_wheel_scrolls_outer_list(qtbot,manager):
    sid,cl,rooms=setup_exam(manager,(2,2,2,2))
    for cid in cl.values():manager.assign(rooms['G2207'],cid)
    win=MainWindow(manager);qtbot.addWidget(win);win.resize(1250,700);win.show();win.select_session(sid,5)
    win.room_cards.setFixedHeight(250)
    qtbot.wait(50)
    lists=win.room_cards.findChildren(AssignedClassCards)
    listing=next(w for w in lists if w.allocation_id==rooms['G2207'])
    assert listing.count()==4
    assert listing.verticalScrollBarPolicy()==Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert listing.viewport().height()>=sum(listing.sizeHintForRow(i) for i in range(4))
    assert listing.visualItemRect(listing.item(3)).bottom()<listing.viewport().height()
    scrollbar=win.room_cards.verticalScrollBar()
    assert scrollbar.maximum()>0
    previous=scrollbar.value()
    event=QWheelEvent(QPointF(10,10),QPointF(10,10),QPoint(0,0),QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    listing.wheelEvent(event)
    assert scrollbar.value()>previous

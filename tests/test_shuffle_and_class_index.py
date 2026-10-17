import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QMessageBox,QPushButton
from app.database.store import Store
from app.services.manager import Manager
from app.models.records import ValidationError
from app.templates.engine import class_seat_index
from app.exporters.excel import ExcelExporter
from app.ui.window import MainWindow
from conftest import setup_exam


def test_shuffle_preserves_locked_slots_gaps_other_room_and_undo(manager):
    sid,classes,rooms=setup_exam(manager,(4,2))
    aid=rooms['G2207'];manager.assign(aid,classes['D']);manager.assign(rooms['G2209'],classes['E'])
    rows=manager.assigned(aid=aid)
    manager.special(rows[0]['id'],'020',True,'前排','保留安排')
    manager.special(rows[1]['id'],'010',False,'其他','保留備註')
    manager.complete(sid)
    before=manager.snapshot(sid)
    fixed=next(r for r in before if r['id']==rows[0]['id'])
    others=[r for r in before if r['allocation_id']!=aid]
    manager.shuffle_seats(aid)
    after=manager.snapshot(sid)
    assert before!=after
    assert {r['id'] for r in before}=={r['id'] for r in after}
    assert next(r for r in after if r['id']==fixed['id'])==fixed
    assert [r for r in after if r['allocation_id']!=aid]==others
    assert {r['seat'] for r in before if r['allocation_id']==aid}=={r['seat'] for r in after if r['allocation_id']==aid}
    for old in before:
        new=next(r for r in after if r['id']==old['id'])
        assert {k:v for k,v in old.items() if k not in ('seat','position')}=={k:v for k,v in new.items() if k not in ('seat','position')}
    assert manager.sessions()[0]['status']=='草稿' and not manager.validate(sid)
    reopened=Store(manager.db.path)
    try:
        other=Manager(reopened)
        assert other.snapshot(sid)==after
        other.undo(sid);assert other.snapshot(sid)==before
        other.undo(sid,True);assert other.snapshot(sid)==after
    finally:reopened.close()


@pytest.mark.parametrize('locked',[False,True])
def test_shuffle_requires_two_unlocked_students(manager,locked):
    sid,classes,rooms=setup_exam(manager,((2 if locked else 1),))
    aid=rooms['G2207'];manager.assign(aid,classes['D'])
    if locked:
        for r in manager.assigned(aid=aid):manager.special(r['id'],r['seat'],True,'','')
    before=manager.snapshot(sid);history=manager.db.rows('SELECT * FROM history')
    with pytest.raises(ValidationError,match='至少需要兩位'):manager.shuffle_seats(aid)
    assert manager.snapshot(sid)==before and manager.db.rows('SELECT * FROM history')==history


def test_shuffle_keeps_merged_exam_seats_reserved(manager):
    first,classes,rooms=setup_exam(manager,(3,),merge=True,room_names=('G2207',))
    manager.assign(rooms['G2207'],classes['D'])
    second,cl2,rooms2=setup_exam(manager,(2,),code='C202',merge=True,room_names=('G2207',))
    manager.assign(rooms2['G2207'],cl2['D'])
    untouched=manager.snapshot(second)
    manager.shuffle_seats(rooms['G2207'])
    assert manager.snapshot(second)==untouched
    assert not manager.validate(first) and not manager.validate(second)


def test_shuffle_ui_cancel_search_and_confirm(qtbot,manager,monkeypatch):
    sid,classes,rooms=setup_exam(manager,(4,))
    aid=rooms['G2207'];manager.assign(aid,classes['D'])
    win=MainWindow(manager);qtbot.addWidget(win);win.select_session(sid,6)
    win.seat_room.setCurrentIndex(win.seat_room.findData(aid))
    assert any(b.text()=='隨機打散座位' for b in win.findChildren(QPushButton))
    assert not win.include_class_index.isChecked()
    before=manager.snapshot(sid)
    win.seat_search.setText('測試')
    with pytest.raises(ValidationError,match='清除搜尋'):win.shuffle_seats()
    win.seat_search.clear()
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.No)
    win.shuffle_seats();assert manager.snapshot(sid)==before
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    win.shuffle_seats();assert manager.snapshot(sid)!=before
    win.history(False);assert manager.snapshot(sid)==before


def test_index_ranges_never_bridge_missing_seats():
    students=[dict(class_name='3D',seat=s) for s in ['010','003','001','004']]
    students += [dict(class_name='3F',seat=s) for s in ['002','007','008']]
    assert class_seat_index(students)==['3D：001、003–004、010','3F：002、007–008']


def test_optional_index_export_uses_actual_mixed_seats_only_on_attendance(manager,tmp_path):
    sid,classes,rooms=setup_exam(manager,(4,2))
    aid=rooms['G2207']
    manager.assign(aid,classes['D']);manager.assign(aid,classes['E'])
    d=[r['id'] for r in manager.assigned(aid=aid) if r['class_id']==classes['D']]
    e=[r['id'] for r in manager.assigned(aid=aid) if r['class_id']==classes['E']]
    manager.reorder(aid,[d[0],e[0],d[1],e[1],d[2],d[3]])
    manager.special(d[0],'001',False,'內部安排不可輸出','PRIVATE NOTE MUST STAY LOCAL')
    exporter=ExcelExporter(manager)
    plain=exporter.generate(aid,tmp_path/'plain')
    result=exporter.batch([aid],tmp_path/'index',include_class_index=True)
    assert result[0][1]=='成功'
    with open(plain,'rb') as stream:
        wb=load_workbook(stream)
        assert not any('班級座號索引' in str(c.value) for s in wb for row in s for c in row)
        wb.close()
    wb=load_workbook(result[0][2])
    attendance=wb['Attendance'];seats=wb['Seat Plan']
    index_cells=[c for row in attendance for c in row if '班級座號索引' in str(c.value)]
    assert [c.value for c in index_cells]==['班級座號索引 · D：001、003、005–006','班級座號索引 · E：002、004']
    assert all(c.font.sz==9 and c.font.color.rgb=='00777777' for c in index_cells)
    assert not any('班級座號索引' in str(c.value) for row in seats for c in row)
    for sheet in wb:
        assert not any('PRIVATE NOTE' in str(c.value) or '內部安排不可輸出' in str(c.value) for row in sheet for c in row)
        assert not sheet.print_title_rows and not sheet.row_breaks.brk
        assert [sheet.cell(i,2).value for i in range(18,24)]==['001','002','003','004','005','006']
    assert int(str(attendance.print_area).split('$')[-1])>=index_cells[-1].row
    wb.close()

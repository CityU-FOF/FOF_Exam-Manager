import json
from PySide6.QtCore import Qt,QMimeData,QPointF
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QDialog,QMessageBox
from app.ui.window import MainWindow
from app.ui.widgets import ClassCards,SelectionDialog
from app.ui.import_dialog import ImportDialog
from openpyxl import Workbook
from conftest import setup_exam


def test_navigation_and_native_room_drop(qtbot,manager):
    sid,classes,rooms=setup_exam(manager,(5,))
    win=MainWindow(manager);qtbot.addWidget(win);win.show();win.select_session(sid,5)
    assert win.pages.count()==9
    for i in range(9):win.nav.setCurrentRow(i);assert win.pages.currentIndex()==i
    win.nav.setCurrentRow(5)
    qtbot.wait(50)
    item=win.room_cards.item(0);aid=item.data(Qt.ItemDataRole.UserRole)
    mime=QMimeData();mime.setData(ClassCards.MIME,json.dumps({'class_id':classes['D'],'session_id':sid}).encode())
    pos=win.room_cards.visualItemRect(item).center()
    event=QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    win.room_cards.dropEvent(event)
    assert event.isAccepted()
    assert len(manager.assigned(aid=aid))==5 and not manager.pending(sid)
    assert '已分配：5' in win.allocation_stats.text()


def test_seat_editor_controls_and_persistence(qtbot,manager):
    sid,cl,rooms=setup_exam(manager,(5,));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    win=MainWindow(manager);qtbot.addWidget(win);win.select_session(sid,6);win.seat_room.setCurrentIndex(win.seat_room.findData(aid))
    original=win.seat_tree.order();last=win.seat_tree.topLevelItem(4);last.setSelected(True)
    win.move_position(1)
    assert win.seat_tree.order()==[original[0],original[4],*original[1:4]]
    win.history(False);assert win.seat_tree.order()==original
    win.history(True);assert win.seat_tree.order()[1]==original[4]
    win.seat_search.setText('NONEXISTENT');assert all(win.seat_tree.topLevelItem(i).isHidden() for i in range(5))
    win.seat_search.clear();assert not win.seat_tree.isFiltered()
    # The native drop handler's persisted order signal is wired to the service.
    order=win.seat_tree.order();order.reverse();win.seat_tree.orderChanged.emit(order)
    assert [r['id'] for r in manager.assigned(aid=aid)]==order


def test_ui_capacity_split_manual_selection(qtbot,manager,monkeypatch):
    sid,cl,rooms=setup_exam(manager,(70,25),room_names=('G2207',));aid=rooms['G2207'];manager.assign(aid,cl['D'])
    win=MainWindow(manager);qtbot.addWidget(win)
    def fake_box_exec(box):
        box._selected=next(b for b in box.buttons() if b.text()=='拆分班級');return 0
    monkeypatch.setattr(QMessageBox,'exec',fake_box_exec)
    monkeypatch.setattr(QMessageBox,'clickedButton',lambda box:box._selected)
    def accept_selection(dialog):
        # Explicitly choose the last 10 students, not the automatic first ten.
        for i in range(dialog.list.count()):dialog.list.item(i).setCheckState(Qt.CheckState.Checked if i>=15 else Qt.CheckState.Unchecked)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(SelectionDialog,'exec',accept_selection)
    before=manager.pending(sid,cl['E']);win.assign_class(aid,cl['E'])
    assert {r['student_id'] for r in manager.pending(sid,cl['E'])}=={r['student_id'] for r in before[:15]}


def test_import_preview_confirm_and_class_search(qtbot,manager,tmp_path,monkeypatch):
    wb=Workbook();s=wb.active;s.title='D';s.append(['學號','姓名','英文姓名','授課班','科目代碼'])
    s.append(['00001','甲','A','D','C101']);p=tmp_path/'roster.xlsx';wb.save(p)
    dialog=ImportDialog(manager,[p]);qtbot.addWidget(dialog)
    assert dialog.preview.rowCount()==1 and not manager.students()
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    dialog.commit();assert len(manager.students())==1
    win=MainWindow(manager);qtbot.addWidget(win)
    win.student_search.setText('00001');assert win.students_table.rowCount()==1
    win.student_search.setText('missing');assert win.students_table.rowCount()==0


def test_open_output_uses_local_file_url(qtbot,manager,tmp_path,monkeypatch):
    from app.ui.window import QDesktopServices
    win=MainWindow(manager);qtbot.addWidget(win);win.last_output=tmp_path
    calls=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:calls.append(url) or True)
    win.open_output();assert len(calls)==1 and calls[0].isLocalFile()


def test_combined_names_preview_and_save(qtbot,manager,tmp_path,monkeypatch):
    wb=Workbook();s=wb.active
    s.append(['帳號','姓名','英文姓名','授課班','科目代碼'])
    s.append(['F20990100001','陳大文 CHAN TAI MAN','David','4B','BAE409'])
    path=tmp_path/'original.xlsx';wb.save(path)
    dialog=ImportDialog(manager,[path]);qtbot.addWidget(dialog)
    assert dialog.preview.item(0,1).text()=='陳大文'
    assert dialog.preview.item(0,2).text()=='CHAN TAI MAN'
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    dialog.commit()
    win=MainWindow(manager);qtbot.addWidget(win)
    assert 'v1.3.1' in win.windowTitle()
    assert win.students_table.item(0,1).text()=='陳大文'
    assert win.students_table.item(0,2).text()=='CHAN TAI MAN'

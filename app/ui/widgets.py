import json
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTextEdit,
 QSpinBox, QCheckBox, QComboBox, QListWidget, QListWidgetItem, QTreeWidget, QAbstractItemView,
 QVBoxLayout, QLabel)


class FormDialog(QDialog):
    def __init__(self,title,fields,values=None,parent=None):
        super().__init__(parent)
        self.setWindowTitle(title);self.setMinimumWidth(520)
        self.editors={};values=values or {}
        layout=QFormLayout(self)
        for key,label,kind in fields:
            value=values.get(key,'')
            if kind=='int':
                editor=QSpinBox();editor.setRange(1,999);editor.setValue(int(value or 80))
            elif kind=='bool':
                editor=QCheckBox();editor.setChecked(bool(value))
            elif kind=='text':
                editor=QTextEdit();editor.setMaximumHeight(90);editor.setPlainText(str(value))
            elif isinstance(kind,list):
                editor=QComboBox()
                for text,data in kind:editor.addItem(text,data)
                ix=editor.findData(value)
                if ix>=0:editor.setCurrentIndex(ix)
            else:
                editor=QLineEdit(str(value))
            self.editors[key]=editor;layout.addRow(label,editor)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        result={}
        for key,e in self.editors.items():
            if isinstance(e,QSpinBox):v=e.value()
            elif isinstance(e,QCheckBox):v=int(e.isChecked())
            elif isinstance(e,QTextEdit):v=e.toPlainText().strip()
            elif isinstance(e,QComboBox):v=e.currentData()
            else:v=e.text().strip()
            result[key]=v
        return result


class ClassCards(QListWidget):
    MIME='application/x-fof-class'
    RETURN_MIME='application/x-fof-assigned-class'
    assignedDropped=Signal(str,str,str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setDragEnabled(True);self.setAcceptDrops(True);self.session_id=None

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(self.RETURN_MIME):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        self.dragEnterEvent(event)

    def dropEvent(self,event):
        if not event.mimeData().hasFormat(self.RETURN_MIME):event.ignore();return
        try:data=json.loads(bytes(event.mimeData().data(self.RETURN_MIME)))
        except (ValueError,TypeError):event.ignore();return
        if not isinstance(data,dict) or not all(isinstance(data.get(k),str) for k in ('allocation_id','class_id','session_id')):event.ignore();return
        self.assignedDropped.emit(data['allocation_id'],data['class_id'],data['session_id']);event.acceptProposedAction()

    def startDrag(self,supportedActions):
        item=self.currentItem()
        if not item:return
        mime=QMimeData();mime.setData(self.MIME,json.dumps({'class_id':item.data(Qt.ItemDataRole.UserRole),'session_id':self.session_id}).encode())
        drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction)


class AssignedClassCards(QListWidget):
    def __init__(self,allocation_id,session_id,parent=None):
        super().__init__(parent);self.allocation_id=allocation_id;self.session_id=session_id
        self.setDragEnabled(True)

    def startDrag(self,supportedActions):
        item=self.currentItem()
        if not item:return
        mime=QMimeData();mime.setData(ClassCards.RETURN_MIME,json.dumps(dict(
            allocation_id=self.allocation_id,session_id=self.session_id,class_id=item.data(Qt.ItemDataRole.UserRole))).encode())
        # Returning a class rebuilds the room cards, so keep the drag owned by
        # the surviving window rather than this temporary class list.
        drag=QDrag(self.window());drag.setMimeData(mime);drag.exec(Qt.DropAction.MoveAction)


class RoomCards(QListWidget):
    classDropped=Signal(str,str,str)
    def __init__(self,parent=None):
        super().__init__(parent);self.setAcceptDrops(True);self.setSpacing(12)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(ClassCards.MIME):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        if event.mimeData().hasFormat(ClassCards.MIME) and self.itemAt(event.position().toPoint()):event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if not item or not event.mimeData().hasFormat(ClassCards.MIME):event.ignore();return
        try:data=json.loads(bytes(event.mimeData().data(ClassCards.MIME)))
        except (ValueError,TypeError):event.ignore();return
        if not isinstance(data,dict) or not isinstance(data.get('class_id'),str) or not isinstance(data.get('session_id'),str):event.ignore();return
        self.classDropped.emit(item.data(Qt.ItemDataRole.UserRole),data['class_id'],data['session_id'])
        event.acceptProposedAction()


class SeatTree(QTreeWidget):
    orderChanged=Signal(list)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setHeaderLabels(['序號','座號','學號','中文姓名','英文姓名','班級','特殊安排','特殊學生原因（內部）'])
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSortingEnabled(False)

    def dropEvent(self,event):
        if self.isFiltered():event.ignore();return
        super().dropEvent(event)
        self.orderChanged.emit(self.order())

    def order(self):
        return [self.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole) for i in range(self.topLevelItemCount())]

    def isFiltered(self):
        return any(self.topLevelItem(i).isHidden() for i in range(self.topLevelItemCount()))


class SelectionDialog(QDialog):
    def __init__(self,title,rows,max_count,parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(600,550)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel(f'請勾選要安排的學生（最多 {max_count} 人）；其餘保留待分配。'))
        self.count=QSpinBox();self.count.setRange(1,max_count);self.count.setValue(max_count)
        layout.addWidget(self.count)
        self.list=QListWidget();layout.addWidget(self.list)
        for i,r in enumerate(rows):
            item=QListWidgetItem(f'{r["student_no"]}　{r["chinese_name"]}　{r["english_name"]}')
            item.setData(Qt.ItemDataRole.UserRole,r['student_id'])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i<max_count else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.count.valueChanged.connect(self.select_count)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def select_count(self,n):
        for i in range(self.list.count()):self.list.item(i).setCheckState(Qt.CheckState.Checked if i<n else Qt.CheckState.Unchecked)

    def selected(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]

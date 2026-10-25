from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QTableWidget,
 QTableWidgetItem,QPushButton,QHeaderView,QAbstractItemView,QMessageBox)


class StudentFlagsDialog(QDialog):
    def __init__(self,manager,edit_callback,parent=None):
        super().__init__(parent);self.manager=manager;self.edit_callback=edit_callback
        self.setWindowTitle('特殊學生名單（內部）');self.resize(900,580)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('標記跨科目保存；即使暫時沒有修讀記錄，仍可在此管理。'))
        self.search=QLineEdit();self.search.setPlaceholderText('搜尋學號、姓名或原因');layout.addWidget(self.search)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['學號','中文姓名','英文姓名','標記原因（內部）'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table)
        self.search.textChanged.connect(self.refresh)
        bar=QHBoxLayout();layout.addLayout(bar)
        edit=QPushButton('編輯／解除選中標記');edit.clicked.connect(self.edit);bar.addWidget(edit)
        close=QPushButton('關閉');close.clicked.connect(self.accept);bar.addWidget(close)
        self.refresh()

    def refresh(self):
        text=self.search.text().strip().lower()
        rows=[r for r in self.manager.flagged_students() if text in ' '.join(str(r[k]) for k in
              ('student_no','chinese_name','english_name','flag_reason')).lower()]
        self.table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,key in enumerate(['student_no','chinese_name','english_name','flag_reason']):
                item=QTableWidgetItem(r[key]);item.setData(Qt.ItemDataRole.UserRole,r);self.table.setItem(i,j,item)
        self.table.resizeRowsToContents()

    def edit(self):
        row=self.table.currentRow()
        if row<0:
            QMessageBox.information(self,'選擇學生','請先選取一位學生。');return
        self.edit_callback(self.table.item(row,0).data(Qt.ItemDataRole.UserRole));self.refresh()


class StudentFlagReminder(QDialog):
    """The normal generation confirmation, with actionable room/student alerts."""
    def __init__(self,alerts,room_count,parent=None):
        super().__init__(parent);self.allocation_id=None;self.assignment_id=None
        self.setWindowTitle('生成前提醒：考場內有特殊學生');self.resize(1100,600)
        layout=QVBoxLayout(self)
        label=QLabel(f'本次選中 {room_count} 個考場，發現 {len(alerts)} 筆特殊學生編排。可返回考場指定並鎖定座號，再重新生成；標記及原因不會印入 Excel。')
        label.setWordWrap(True);layout.addWidget(label)
        self.table=QTableWidget(len(alerts),7)
        self.table.setHorizontalHeaderLabels(['科目','考場','學號','中文姓名','英文姓名','目前座號','原因（內部）'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,r in enumerate(alerts):
            for j,key in enumerate(['code','room_name','student_no','chinese_name','english_name','seat','flag_reason']):
                item=QTableWidgetItem(r[key]);item.setData(Qt.ItemDataRole.UserRole,r);self.table.setItem(i,j,item)
        self.table.resizeRowsToContents();self.table.selectRow(0);layout.addWidget(self.table)
        bar=QHBoxLayout();layout.addLayout(bar)
        edit=QPushButton('前往所選考場調整座位');edit.clicked.connect(self.adjust);edit.setDefault(True);bar.addWidget(edit)
        generate=QPushButton('已核對安排，繼續生成');generate.clicked.connect(self.accept);bar.addWidget(generate)
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);bar.addWidget(cancel)

    def adjust(self):
        row=self.table.currentRow()
        if row<0:return
        record=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
        self.allocation_id=record['allocation_id'];self.assignment_id=record['assignment_id']
        self.reject()

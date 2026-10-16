from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
 QTableWidget,QTableWidgetItem,QPushButton,QMessageBox,QHeaderView)
from app.ui.course_paste import PasteEdit
from app.importers.rooms import parse_rooms


class RoomPasteDialog(QDialog):
    def __init__(self,manager,parent=None):
        super().__init__(parent);self.manager=manager;self.html='';self.loading=False
        self.setWindowTitle('智能貼上考場');self.resize(850,680)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('貼上「考場名稱、最多人數」兩欄；相同考場及容量自動去重，不同容量需人工核對。'))
        self.text=PasteEdit();self.text.setAcceptRichText(False)
        self.text.pasted.connect(self.pasted);self.text.textChanged.connect(self.changed);layout.addWidget(self.text)
        bar=QHBoxLayout();layout.addLayout(bar)
        for label,callback in [('從剪貼簿貼上並分析',self.from_clipboard),('分析文字',self.analyze),('刪除選中預覽列',self.remove_rows)]:
            b=QPushButton(label);b.clicked.connect(callback);bar.addWidget(b)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['考場名稱','最多人數','提示','已核對'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table)
        bar=QHBoxLayout();layout.addLayout(bar)
        b=QPushButton('確認批量儲存');b.clicked.connect(self.commit);bar.addWidget(b)
        b=QPushButton('取消');b.clicked.connect(self.reject);bar.addWidget(b)

    def changed(self):
        if not self.loading:self.html=''
        self.table.setRowCount(0)

    def pasted(self,html):
        self.html=html;self.analyze()

    def from_clipboard(self):
        mime=QApplication.clipboard().mimeData();self.loading=True
        self.text.setPlainText(mime.text());self.loading=False
        self.html=mime.html() if mime.hasHtml() else '';self.analyze()

    def analyze(self):
        try:
            rows=parse_rooms(self.text.toPlainText(),self.html);self.table.setRowCount(len(rows))
            for i,r in enumerate(rows):
                for j,value in enumerate([r.name,r.capacity,'；'.join(r.issues) or '已去重；相同名稱會更新容量']):
                    item=QTableWidgetItem(value)
                    if j==2:item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.table.setItem(i,j,item)
                item=QTableWidgetItem();item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked if r.issues else Qt.CheckState.Checked);self.table.setItem(i,3,item)
        except Exception as exc:QMessageBox.warning(self,'不能分析',str(exc))

    def remove_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):self.table.removeRow(row)

    def commit(self):
        try:
            if not self.table.rowCount():raise ValueError('請先分析考場表格。')
            rows=[]
            for i in range(self.table.rowCount()):
                if self.table.item(i,3).checkState()!=Qt.CheckState.Checked:raise ValueError('請先修正及核對有提示的列。')
                rows.append(dict(name=self.table.item(i,0).text(),capacity=self.table.item(i,1).text()))
            if QMessageBox.question(self,'確認考場',f'儲存 {len(rows)} 個考場？已有考場會更新容量，保留啟用狀態及備註；座號自動由 001 起。')!=QMessageBox.StandardButton.Yes:return
            self.manager.save_rooms(rows);self.accept()
        except Exception as exc:QMessageBox.warning(self,'不能儲存',str(exc))

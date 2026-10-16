from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTextEdit,
 QTableWidget,QTableWidgetItem,QPushButton,QMessageBox,QHeaderView)
from app.importers.courses import parse_courses
from app.models.programmes import PROGRAMMES,programme_values


class PasteEdit(QTextEdit):
    pasted=Signal(str)

    def insertFromMimeData(self,source):
        super().insertFromMimeData(source)
        self.pasted.emit(source.html() if source.hasHtml() else '')


class CoursePasteDialog(QDialog):
    def __init__(self,manager,parent=None):
        super().__init__(parent);self.manager=manager;self.html='';self.loading=False;self.previews=[]
        self.setWindowTitle('智能貼上科目表格');self.resize(1150,760)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('選擇課程 → 從 Excel／Word 複製表格 → 貼上分析 → 核對後批量儲存。'))
        self.programme=QComboBox()
        for code,(cn,en) in PROGRAMMES.items():self.programme.addItem(f'{code} · {cn} / {en}',code)
        layout.addWidget(self.programme)
        self.text=PasteEdit();self.text.setAcceptRichText(False);self.text.setPlaceholderText('貼上：課程代碼｜科目編號｜中文科名＋英文科名｜任課教師')
        self.text.pasted.connect(self.pasted)
        self.text.textChanged.connect(self.text_changed);layout.addWidget(self.text,1)
        bar=QHBoxLayout();layout.addLayout(bar)
        for label,callback in [('從剪貼簿貼上並分析',self.from_clipboard),('分析文字',self.analyze),('刪除選中預覽列',self.remove_rows)]:
            b=QPushButton(label);b.clicked.connect(callback);bar.addWidget(b)
        self.status=QLabel();layout.addWidget(self.status)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['科目編號','中文名稱','英文名稱','任課教師','分析提示','已人工核對'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,2)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        save=QPushButton('確認批量儲存');save.clicked.connect(self.commit);buttons.addWidget(save)
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);buttons.addWidget(cancel)

    def text_changed(self):
        if not self.loading:self.html=''
        self.previews=[];self.table.setRowCount(0);self.status.setText('文字已變更，請重新分析。')

    def pasted(self,html):
        self.html=html;self.analyze()

    def from_clipboard(self):
        mime=QApplication.clipboard().mimeData()
        self.loading=True
        self.text.setPlainText(mime.text());self.loading=False
        self.html=mime.html() if mime.hasHtml() else ''
        self.analyze()

    def analyze(self):
        try:
            self.previews=parse_courses(self.text.toPlainText(),self.html,self.programme.currentData())
            self.table.setRowCount(len(self.previews))
            for i,r in enumerate(self.previews):
                for j,key in enumerate(['code','name_cn','name_en','teachers']):
                    item=QTableWidgetItem(r.values[key]);item.setToolTip(r.values[key]);self.table.setItem(i,j,item)
                note=QTableWidgetItem('；'.join(r.issues) or '已識別，可核對後儲存');note.setToolTip(note.text());note.setFlags(Qt.ItemFlag.ItemIsEnabled);self.table.setItem(i,4,note)
                check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Unchecked if r.issues else Qt.CheckState.Checked);self.table.setItem(i,5,check)
            self.table.resizeRowsToContents()
            self.status.setText(f'識別 {len(self.previews)} 筆科目；合併編號會分開列出。有提示的列必須修正並核對。')
        except Exception as exc:QMessageBox.warning(self,'不能分析',str(exc))

    def remove_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):self.table.removeRow(row)

    def commit(self):
        try:
            if not self.table.rowCount():raise ValueError('請先貼上並分析科目表格。')
            records=[]
            for i in range(self.table.rowCount()):
                if self.table.item(i,5).checkState()!=Qt.CheckState.Checked:raise ValueError(f'第 {i+1} 列仍需人工核對。')
                values={key:self.table.item(i,j).text().strip() for j,key in enumerate(['code','name_cn','name_en','teachers'])}
                records.append(dict(programme_values(self.programme.currentData()),**values))
            if QMessageBox.question(self,'確認儲存',f'儲存 {len(records)} 筆科目？相同科目編號會更新科名、教師與課程；已有名單及座位會保留。')!=QMessageBox.StandardButton.Yes:return
            self.manager.save_courses(records);self.accept()
        except Exception as exc:QMessageBox.warning(self,'不能儲存',str(exc))

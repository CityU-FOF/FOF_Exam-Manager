from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QTableWidget,
 QTableWidgetItem,QCheckBox,QMessageBox,QHeaderView)
from app.importers.roster import inspect_roster


class ImportDialog(QDialog):
    def __init__(self,manager,paths,parent=None):
        super().__init__(parent);self.manager=manager;self.candidates=[];self.records=[]
        self.setWindowTitle('名單匯入 · 科目授課班、預覽、差異合併');self.resize(1250,800)
        layout=QVBoxLayout(self)
        self.summary=QLabel('每份檔案只使用完整匯總名單，按科目代碼識別授課班。');layout.addWidget(self.summary)
        self.sheets=QTableWidget(0,7);self.sheets.setHorizontalHeaderLabels(['選取','檔案','名單來源','授課班','完整科目代碼','學年／學期','人數'])
        self.sheets.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.sheets)
        for path in paths:
            for c in inspect_roster(path):
                row=self.sheets.rowCount();self.sheets.insertRow(row);self.candidates.append(c)
                item=QTableWidgetItem();item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if c.recommended else Qt.CheckState.Unchecked)
                self.sheets.setItem(row,0,item)
                first=c.records[0]
                for col,value in enumerate([first.source,c.sheet,c.class_name,first.teaching_code,first.academic_year+' '+first.semester,str(len(c.records))],1):
                    item=QTableWidgetItem(value);item.setFlags(Qt.ItemFlag.ItemIsEnabled);self.sheets.setItem(row,col,item)
        preview=QPushButton('載入所選班級預覽');preview.clicked.connect(self.load_preview);layout.addWidget(preview)
        self.preview=QTableWidget(0,10)
        self.preview.setHorizontalHeaderLabels(['學號','中文姓名','英文姓名','授課班','科目編號','科目名稱','學年／學期','完整科目代碼','問題／原始姓名','已人工核對'])
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.preview,2)
        self.remove=QCheckBox('差異合併：停用所選班級已移除的修讀記錄（保留現有座位並要求人工處理）')
        layout.addWidget(self.remove)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.diff_button=QPushButton('查看差異');self.diff_button.clicked.connect(self.show_diff);buttons.addWidget(self.diff_button)
        review=QPushButton('定位待核對資料');review.clicked.connect(self.focus_issue);buttons.addWidget(review)
        confirm=QPushButton('確認匯入');confirm.clicked.connect(self.commit);buttons.addWidget(confirm)
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);buttons.addWidget(cancel)
        self.load_preview()

    def load_preview(self):
        self.records=[]
        for i,c in enumerate(self.candidates):
            if self.sheets.item(i,0).checkState()==Qt.CheckState.Checked:self.records+=c.records
        self.preview.setRowCount(len(self.records))
        for i,r in enumerate(self.records):
            for col,value in enumerate([r.student_no,r.chinese_name,r.english_name,r.class_name,r.course_code,r.course_name,
                                        r.academic_year+' '+r.semester,r.teaching_code,
                                        '；'.join(r.issues)+'\n原文：'+r.raw_name]):
                item=QTableWidgetItem(value)
                if col>=6 or (r.teaching_code and col in (3,4)):item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.preview.setItem(i,col,item)
            reviewed=QTableWidgetItem();reviewed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            reviewed.setCheckState(Qt.CheckState.Unchecked if r.issues else Qt.CheckState.Checked)
            self.preview.setItem(i,9,reviewed)
        details=['%s：%d 人'%(c.class_name,len(c.records)) for i,c in enumerate(self.candidates) if self.sheets.item(i,0).checkState()==Qt.CheckState.Checked]
        problems=sum(bool(r.issues) for r in self.records)
        self.summary.setText(f'預覽 {len(self.records)} 人，{len(details)} 份完整匯總名單，{problems} 筆資料需核對。\n'+'；'.join(details))
        self.summary.setWordWrap(True)

    def focus_issue(self):
        for i in range(self.preview.rowCount()):
            if self.preview.item(i,9).checkState()!=Qt.CheckState.Checked:
                self.preview.setCurrentCell(i,9)
                self.preview.scrollToItem(self.preview.item(i,9))
                return

    def edited_records(self):
        if not self.records:raise ValueError('請先選取班級。')
        rows=[]
        for i,r in enumerate(self.records):
            if self.preview.item(i,9).checkState()!=Qt.CheckState.Checked:
                self.focus_issue()
                raise ValueError(f'第 {i+1} 列有待核對資料，已定位至「已人工核對」欄。請查看該列問題，修正後勾選核對。')
            values=[self.preview.item(i,j).text().strip() for j in range(6)]
            rows.append(replace(r,student_no=values[0],chinese_name=values[1],english_name=values[2],
                                class_name=values[3],course_code=values[4],course_name=values[5],administrative_class='',issues=[]))
        return rows

    def show_diff(self):
        try:
            diff=self.manager.import_diff(self.edited_records())
            labels={'added':'新增','removed':'已移除','changed':'姓名更改','unchanged':'無變化'}
            text='\n'.join(f'{labels[k]}：{len(v)} 人' for k,v in diff.items())
            for key in ['added','removed','changed']:
                text+='\n\n'+labels[key]+'：\n'
                text+='\n'.join((r['student_no']+' '+r['chinese_name']) if isinstance(r,dict) else (r.student_no+' '+r.chinese_name) for r in diff[key])
            box=QMessageBox(self);box.setWindowTitle('重新匯入差異');box.setText('\n'.join(f'{labels[k]}：{len(v)} 人' for k,v in diff.items()))
            box.setDetailedText(text);box.exec()
        except Exception as e:QMessageBox.warning(self,'不能比較',str(e))

    def commit(self):
        try:
            records=self.edited_records();diff=self.manager.import_diff(records)
            text=f'新增 {len(diff["added"])}、姓名更改 {len(diff["changed"])}、已移除 {len(diff["removed"])}、無變化 {len(diff["unchanged"])}。\n'
            text+='已移除記錄將停用，現有座位保留待確認。' if self.remove.isChecked() else '已移除記錄將保留；此操作不刪除現有修讀關係。'
            if QMessageBox.question(self,'確認合併',text)!=QMessageBox.StandardButton.Yes:return
            self.manager.import_records(records,self.remove.isChecked());self.accept()
        except Exception as e:QMessageBox.warning(self,'匯入失敗',str(e))

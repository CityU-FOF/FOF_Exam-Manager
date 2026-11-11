from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,
 QSpinBox,QPushButton,QCheckBox,QTabWidget,QScrollArea,QFileDialog,QMessageBox,QDialog,QListWidget,QListWidgetItem)
from app.services.papers import PaperManager,LANGUAGES,print_quantities
from app.exporters.papers import PaperExporter
from app.utils.output import default_output_directory


class PaperPage(QWidget):
    def __init__(self,manager,parent=None):
        super().__init__(parent);self.manager=manager;self.papers=PaperManager(manager)
        self.sid=None;self.loading=False;self.last_output=None;self.editors={};self.language_editors={};self.cover_labels={}
        self.output_folder=default_output_directory(manager)
        layout=QVBoxLayout(self)
        title=QLabel('試卷文件及印刷統計');title.setObjectName('pageTitle');layout.addWidget(title)
        self.context_label=QLabel('請先在右上方選擇考試場次。');self.context_label.setTextFormat(Qt.TextFormat.PlainText);self.context_label.setWordWrap(True);layout.addWidget(self.context_label)
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);layout.addWidget(scroll,1)
        content=QVBoxLayout(body);form=QFormLayout();content.addLayout(form)
        self.add_combo(form,self.editors,'approval','是否需要試題審批',[
            ('待確認','pending'),('需要審批：保留已審批PDF及原QR','required'),('不需審批：由本系統填寫官方封面','not_required')])
        self.add_combo(form,self.editors,'book','開／閉卷（自行生成封面時必填）',[
            ('待選擇','pending'),('閉卷','closed'),('開卷','open')])
        for key,label in [('sender','送審人'),('submission_date','送審日期（YYYY-MM-DD）')]:
            e=QLineEdit();self.editors[key]=e;form.addRow(label,e);e.textChanged.connect(self.changed)
        self.add_spin(form,self.editors,'sheets_per_ream','每令A4張數',100000)
        self.add_spin(form,self.editors,'reams_per_box','每箱令數',1000)
        tabs=QTabWidget();content.addWidget(tabs)
        for language,label in LANGUAGES.items():
            page=QWidget();lf=QFormLayout(page);tabs.addTab(page,label);editors={};self.language_editors[language]=editors
            self.add_spin(lf,editors,'pages','試卷內容頁數（不含封面）',10000)
            self.add_combo(lf,editors,'formula','公式表處理',[
                ('待確認','pending'),('沒有公式表','none'),('已計入上述試卷內容頁數','included'),('獨立印刷：請補齊下方資料','separate')])
            self.add_spin(lf,editors,'formula_pages','獨立公式表頁數',10000)
            self.add_combo(lf,editors,'formula_sides','獨立公式表單／雙面',[
                ('待選擇','pending'),('單面','single'),('雙面','double')])
            self.add_spin(lf,editors,'formula_copies','獨立公式表實際份數（含所需後備）',100000)
            self.add_combo(lf,editors,'formula_cover','獨立公式表封面',[
                ('待確認','pending'),('沒有獨立封面','none'),('另加一張單面封面','single')])
            coverbar=QHBoxLayout();self.cover_labels[language]=QLabel('未匯入已審批封面')
            self.cover_labels[language].setWordWrap(True);coverbar.addWidget(self.cover_labels[language],1)
            b=QPushButton('匯入已審批PDF');b.clicked.connect(lambda _,l=language:self.import_cover(l));coverbar.addWidget(b)
            lf.addRow('已審批原封面',coverbar)
        note=QLabel('A班為英文卷，其餘授課班為中文卷。每班多1份後備；內容雙面、封面另印1張單面。\n附件一每科一份；試卷袋每個考場一頁，可重複列印多份。評審結論、現場情況與簽署留白。')
        note.setWordWrap(True);content.addWidget(note)
        self.total=QLabel();self.total.setWordWrap(True);self.total.setTextFormat(Qt.TextFormat.PlainText);content.addWidget(self.total)
        choices=QHBoxLayout();layout.addLayout(choices);self.kinds={}
        for key,label,checked in [('review','附件一評審表',True),('cover','附件二封面',False),('bag','附件三試卷袋',True),('statistics','印刷統計',False)]:
            b=QCheckBox(label);b.setChecked(checked);self.kinds[key]=b;choices.addWidget(b)
        bar=QHBoxLayout();layout.addLayout(bar)
        b=QPushButton('生成選中的考務文件');b.clicked.connect(self.generate);bar.addWidget(b)
        b=QPushButton('印刷總表（多科）');b.clicked.connect(self.batch_statistics);bar.addWidget(b)
        b=QPushButton('打開輸出資料夾');b.clicked.connect(self.open_output);bar.addWidget(b)

    def add_spin(self,form,editors,key,label,maximum):
        e=QSpinBox();e.setRange(0,maximum);e.setSpecialValueText('待填');form.addRow(label,e);editors[key]=e;e.valueChanged.connect(self.changed)

    def add_combo(self,form,editors,key,label,choices):
        e=QComboBox()
        for text,value in choices:e.addItem(text,value)
        form.addRow(label,e);editors[key]=e;e.currentIndexChanged.connect(self.changed)

    def load_session(self,sid):
        self.sid=sid;self.loading=True
        settings=self.papers.settings(sid)
        for key,e in self.editors.items():self.set_value(e,settings[key])
        for language,editors in self.language_editors.items():
            for key,e in editors.items():self.set_value(e,settings[language][key])
        self.loading=False;self.refresh_summary()

    @staticmethod
    def set_value(editor,value):
        if isinstance(editor,QSpinBox):editor.setValue(int(value))
        elif isinstance(editor,QComboBox):editor.setCurrentIndex(max(0,editor.findData(value)))
        else:editor.setText(str(value))

    def collect(self):
        def value(e):
            if isinstance(e,QSpinBox):return e.value()
            if isinstance(e,QComboBox):return e.currentData()
            return e.text().strip()
        result={k:value(e) for k,e in self.editors.items()}
        for language,editors in self.language_editors.items():result[language]={k:value(e) for k,e in editors.items()}
        return result

    def changed(self):
        if self.loading or not self.sid:return
        self.papers.save(self.sid,self.collect());self.refresh_summary()

    def refresh_summary(self):
        if not self.sid:
            self.context_label.setText('請先在右上方選擇考試場次。');self.total.clear();return
        context=self.papers.context(self.sid);info=context['info']
        self.context_label.setText(f'{info["code"]} {info["name_cn"]} · {info["date"]} {info["start"]}–{info["end"]}\n'+
            '；'.join(f'{g["name"]}：{g["students"]}人（{LANGUAGES[g["language"]]}）' for g in context['groups']))
        covers=self.papers.covers(self.sid)
        for language,label in self.cover_labels.items():
            label.setText(covers[language]['original_name'] if language in covers else '未匯入已審批封面')
            label.setTextFormat(Qt.TextFormat.PlainText)
            independent=self.language_editors[language]['formula'].currentData()=='separate'
            for key,e in self.language_editors[language].items():
                if key.startswith('formula_'):e.setEnabled(independent)
        try:
            result=print_quantities(context['groups'],self.collect())
            text='\n'.join(f'{r["label"]}：({r["students"]}人＋{r["classes"]}班後備) × {r["sheets_per_copy"]}張／份；獨立公式表 {r["formula_sheets"]}張' for r in result['rows'])
            self.total.setText(text+f'\n合共 {result["total_sheets"]} 張＝{result["full_reams"]}令 {result["loose_sheets"]}張；約需 {result["boxes"]} 箱。設定已自動保存。')
        except Exception as exc:self.total.setText('用紙統計待補齊：'+str(exc))

    def import_cover(self,language):
        if not self.sid:return
        path,_=QFileDialog.getOpenFileName(self,'選擇已審批原封面（保留原QR）','','PDF (*.pdf)')
        if not path:return
        try:self.papers.put_cover(self.sid,language,path);self.refresh_summary()
        except Exception as exc:QMessageBox.warning(self,'無法匯入',str(exc))

    def generate(self):
        try:
            if not self.sid:raise ValueError('請先選擇考試場次。')
            self.papers.save(self.sid,self.collect())
            host=self.window()
            if self.kinds['bag'].isChecked() and hasattr(host,'confirm_flagged_students'):
                aids=[r['id'] for r in self.manager.allocations(self.sid)]
                if not host.confirm_flagged_students(aids):return
            folder=QFileDialog.getExistingDirectory(self,'選擇考務文件輸出資料夾',str(self.output_folder))
            if not folder:return
            self.output_folder=Path(folder);self.last_output=None
            self.last_output=PaperExporter(self.manager).generate(self.sid,folder,[k for k,b in self.kinds.items() if b.isChecked()])
            QMessageBox.information(self,'考務文件已生成','已輸出至：\n'+str(self.last_output)+'\nExcel請修改「資料」頁B欄；只列印官方表格頁。')
        except Exception as exc:QMessageBox.warning(self,'未能生成',str(exc))

    def open_output(self):
        try:
            folder=self.last_output or self.output_folder
            folder.mkdir(parents=True,exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve()))):
                raise OSError('無法開啟資料夾，請用檔案總管開啟：\n'+str(folder))
        except Exception as exc:QMessageBox.warning(self,'無法打開輸出資料夾',str(exc))

    def batch_statistics(self):
        try:
            if not self.sid:raise ValueError('請先選擇考試場次。')
            context=self.papers.context(self.sid)
            dialog=QDialog(self);dialog.setWindowTitle('選擇同批次要統計的科目場次');dialog.resize(650,500)
            layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
            for session in self.manager.sessions():
                if session['batch_id']!=context['info']['batch_id']:continue
                item=QListWidgetItem(f'{session["code"]} {session["name_cn"]} · {session["date"]} {session["start"]}')
                item.setData(Qt.ItemDataRole.UserRole,session['id']);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if session['id']==self.sid else Qt.CheckState.Unchecked);listing.addItem(item)
            b=QPushButton('確認統計');b.clicked.connect(dialog.accept);layout.addWidget(b)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            chosen=[listing.item(i).data(Qt.ItemDataRole.UserRole) for i in range(listing.count()) if listing.item(i).checkState()==Qt.CheckState.Checked]
            folder=QFileDialog.getExistingDirectory(self,'選擇印刷總表輸出資料夾',str(self.output_folder))
            if not folder:return
            self.output_folder=Path(folder);self.last_output=None
            path=PaperExporter(self.manager).batch_statistics(chosen,folder);self.last_output=path.parent
            QMessageBox.information(self,'印刷總表已輸出',str(path))
        except Exception as exc:QMessageBox.warning(self,'未能統計',str(exc))

from datetime import date
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QListWidget,QListWidgetItem,QStackedWidget,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,
 QHeaderView,QAbstractItemView,QFileDialog,QMessageBox,QDialog,QCheckBox,QTreeWidgetItem,
 QSplitter,QProgressDialog,QInputDialog,QProgressBar,QFrame,QTabWidget)
from app.ui.widgets import FormDialog,ClassCards,RoomCards,AssignedClassCards,SeatTree,SelectionDialog
from app.ui.import_dialog import ImportDialog
from app.ui.course_paste import CoursePasteDialog
from app.ui.room_paste import RoomPasteDialog
from app.ui.student_flags import StudentFlagsDialog,StudentFlagReminder
from app.ui.papers import PaperPage
from app.ui.batch_dialog import BatchDialog
from app.models.programmes import programme_values,PROGRAMMES,FACULTY
from app.models.records import StudentRecord,CapacityError,ValidationError
from app.database.store import uid,now
from app.exporters.excel import ExcelExporter,safe_filename
from app.utils.output import default_output_directory


COURSE_FIELDS=[('code','科目編號','line'),('name_cn','中文名稱','line'),('name_en','英文名稱','line'),
 ('teachers','任課教師（多人以 、 分隔）','line'),('notes','備註','text')]
ROOM_FIELDS=[('name','考場名稱','line'),('capacity','最多考生人數（座號自動 001 起）','int'),
 ('enabled','啟用','bool'),('notes','備註','text')]


def button(text,callback,layout):
    widget=QPushButton(text);widget.clicked.connect(callback);layout.addWidget(widget);return widget


def table(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setAlternatingRowColors(True);return t


def fill_table(t,rows,keys):
    t.setRowCount(len(rows))
    for i,r in enumerate(rows):
        for j,key in enumerate(keys):
            item=QTableWidgetItem(str(r.get(key,'') if r.get(key) is not None else ''))
            item.setData(Qt.ItemDataRole.UserRole,r);t.setItem(i,j,item)


def selected_row(t):
    row=t.currentRow()
    if row<0 or not t.item(row,0):raise ValidationError('請先選取一列。')
    return t.item(row,0).data(Qt.ItemDataRole.UserRole)


def populate(combo,choices,empty=None):
    old=combo.currentData();combo.blockSignals(True);combo.clear()
    if empty:combo.addItem(empty,None)
    for label,data in choices:combo.addItem(label,data)
    index=combo.findData(old)
    if index>=0:combo.setCurrentIndex(index)
    combo.blockSignals(False)


class SessionDialog(FormDialog):
    def __init__(self,manager,parent=None,existing=None):
        self.manager=manager
        courses=[(c['code']+' '+c['name_cn'],c['id']) for c in manager.courses()]
        batches=[(b['name'],b['id']) for b in manager.batches()]
        fields=[] if existing else [('batch_id','學年／學期／考試',batches),('course_id','科目',courses)]
        fields += [('date','考試日期 YYYY-MM-DD','line'),('start','開始時間 HH:MM','line'),
          ('end','結束時間 HH:MM','line'),('teachers','本場教師（可覆寫預設）','line'),('intake','入讀時間 Intake','line'),
          ('allow_merge','允許合場（雙方場次均須啟用）','bool')]
        defaults=existing or {'date':date.today().isoformat(),'start':'19:00','end':'21:00','intake':'2026-08'}
        super().__init__('編輯場次' if existing else '建立考試場次',fields,defaults,parent)
        self.classes=QListWidget();self.rooms=QListWidget()
        if not existing:
            self.layout().insertRow(self.layout().rowCount()-1,'參加班級（勾選）',self.classes)
            self.layout().insertRow(self.layout().rowCount()-1,'使用考場（勾選）',self.rooms)
            self.editors['course_id'].currentIndexChanged.connect(self.course_changed)
            self.editors['batch_id'].currentIndexChanged.connect(self.course_changed)
            self.course_changed()
            for r in manager.rooms():
                if r['enabled']:self.add_check(self.rooms,f'{r["name"]} · {r["capacity"]} 人',r['id'],checked=False)
        else:
            self.room_replacements={}
            allocations=manager.allocations(existing['id'])
            table_widget=QTableWidget(len(allocations),2)
            table_widget.setHorizontalHeaderLabels(['目前考場／人數','更換為（或移除）'])
            table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table_widget.setMinimumHeight(170)
            for i,a in enumerate(allocations):
                item=QTableWidgetItem(f'{a["room_name"]} · {a["count"]} 人');item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                table_widget.setItem(i,0,item)
                choice=QComboBox();choice.addItem('移除：學生回待分配',None)
                for room in manager.rooms():
                    if room['enabled'] or room['id']==a['room_id']:
                        choice.addItem(f'{room["name"]} · {room["capacity"]} 人',room['id'])
                choice.setCurrentIndex(choice.findData(a['room_id']))
                table_widget.setCellWidget(i,1,choice);self.room_replacements[a['id']]=choice
            self.layout().insertRow(self.layout().rowCount()-1,'現有考場',table_widget)
            for room in manager.rooms():
                if room['enabled'] and room['id'] not in {a['room_id'] for a in allocations}:
                    self.add_check(self.rooms,f'{room["name"]} · {room["capacity"]} 人',room['id'],checked=False)
            self.rooms.setMaximumHeight(150)
            self.layout().insertRow(self.layout().rowCount()-1,'新增考場（勾選）',self.rooms)
            notice=QLabel('更換保留學生、次序及鎖定座號。移除會將學生回待分配（包括鎖定者），並清除此場次復原歷史；已有 Excel 保留。')
            notice.setWordWrap(True);self.layout().insertRow(self.layout().rowCount()-1,notice)
            self.resize(760,700)

    @staticmethod
    def add_check(widget,label,identifier,checked=True):
        item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,identifier)
        item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked);widget.addItem(item)

    def course_changed(self):
        cid=self.editors['course_id'].currentData();self.classes.clear()
        batch=next((b for b in self.manager.batches() if b['id']==self.editors['batch_id'].currentData()),None)
        for c in self.manager.classes(cid):
            normalized=lambda v:v.replace('-','').replace('–','').replace('/','')
            if batch and c['academic_year'] and (normalized(c['academic_year'])!=normalized(batch['academic_year']) or c['semester']!=batch['semester']):continue
            if c['course_id']==cid:self.add_check(self.classes,f'{c["name"]} 班 · {c["count"]} 人 · {c["academic_year"]} {c["semester"]}',c['id'])
        course=next((c for c in self.manager.courses() if c['id']==cid),None)
        if course:self.editors['teachers'].setText(course['teachers'])

    @staticmethod
    def checked(widget):
        return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count()) if widget.item(i).checkState()==Qt.CheckState.Checked]


class MainWindow(QMainWindow):
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.exporter=ExcelExporter(manager);self.last_output=None
        self.setWindowTitle('FOF Exam Seating & Attendance Manager v1.7.2');self.resize(1440,920);self.setMinimumSize(1000,650)
        self.setAcceptDrops(True)
        root=QWidget();self.setCentralWidget(root);outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0)
        self.nav=QListWidget();self.nav.setFixedWidth(210)
        self.nav.addItems(['Dashboard','學生名單','科目管理','考場管理','學年與考試','考場編排','座位調整','文件生成中心','試卷文件及印刷','設定與資料備份'])
        outer.addWidget(self.nav)
        right=QVBoxLayout();right.setContentsMargins(24,20,24,20);outer.addLayout(right,1)
        head=QHBoxLayout();right.addLayout(head)
        title=QLabel('FOF  /  考試座位與簽到管理');title.setObjectName('brand');head.addWidget(title)
        head.addStretch();self.session_combo=QComboBox();self.session_combo.setMinimumWidth(440);head.addWidget(self.session_combo)
        self.pages=QStackedWidget();right.addWidget(self.pages,1)
        self.statusBar().showMessage('離線本地處理 · 資料自動保存 · 不傳送學生資料')
        self.build_dashboard();self.build_students();self.build_courses();self.build_rooms();self.build_batches()
        self.build_allocation();self.build_seats();self.build_generation()
        self.paper_page=PaperPage(self.manager,self);self.pages.addWidget(self.paper_page)
        self.build_settings()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.session_combo.currentIndexChanged.connect(self.refresh_workflow)
        self.nav.setCurrentRow(0);self.refresh_all()
        if manager.name_repair_count:
            self.statusBar().showMessage(f'已拆分 {manager.name_repair_count} 個舊姓名；修正前備份：{manager.name_repair_backup}')

    def guard(self,callback):
        try:return callback()
        except Exception as e:
            self.refresh_all()
            QMessageBox.warning(self,'操作未完成',str(e));return None

    def page(self,title,subtitle):
        w=QWidget();layout=QVBoxLayout(w);layout.setContentsMargins(0,12,0,0);layout.setSpacing(16)
        h=QLabel(title);h.setObjectName('pageTitle');layout.addWidget(h)
        sub=QLabel(subtitle);sub.setWordWrap(True);sub.setObjectName('subtitle');layout.addWidget(sub)
        self.pages.addWidget(w);return layout

    def build_dashboard(self):
        layout=self.page('Dashboard','所有統計來自本地資料庫。選擇上方場次可繼續編排。')
        self.stats=QLabel();self.stats.setObjectName('stats');layout.addWidget(self.stats)
        self.dashboard_table=table(['批次','科目','日期','時間','狀態']);layout.addWidget(self.dashboard_table)
        self.dashboard_table.cellDoubleClicked.connect(lambda *_:self.select_session(selected_row(self.dashboard_table)['id'],5))

    def build_students(self):
        layout=self.page('學生名單','拖放 .xlsx 到視窗或選取檔案匯入。每份檔案只讀完整匯總名單，按科目代碼識別授課班，再確認預覽與差異。')
        filters=QHBoxLayout();layout.addLayout(filters)
        self.student_search=QLineEdit();self.student_search.setPlaceholderText('搜尋學號、中文姓名、英文姓名');filters.addWidget(self.student_search)
        self.student_course=QComboBox();self.student_class=QComboBox();filters.addWidget(self.student_course);filters.addWidget(self.student_class)
        self.student_search.textChanged.connect(self.refresh_students);self.student_course.currentIndexChanged.connect(self.refresh_student_classes)
        self.student_class.currentIndexChanged.connect(self.refresh_students)
        more=QHBoxLayout();layout.addLayout(more)
        self.student_year=QComboBox();self.student_term=QComboBox();self.student_source=QComboBox()
        for f in [self.student_year,self.student_term,self.student_source]:
            more.addWidget(f);f.currentIndexChanged.connect(self.refresh_students)
        self.flagged_only=QCheckBox('只顯示特殊學生');self.flagged_only.toggled.connect(self.refresh_students);more.addWidget(self.flagged_only)
        button('清除篩選',self.clear_student_filters,more)
        self.class_counts=QLabel();layout.addWidget(self.class_counts)
        bar=QHBoxLayout();layout.addLayout(bar)
        button('匯入 Excel（可多選）',self.pick_import,bar)
        button('新增學生',lambda:self.guard(self.add_student),bar)
        button('編輯姓名／學號',lambda:self.guard(self.edit_student),bar)
        button('特殊學生標記',lambda:self.guard(lambda:self.student_flag_form(selected_row(self.students_table))),bar)
        button('特殊學生名單',lambda:self.guard(lambda:StudentFlagsDialog(self.manager,self.student_flag_form,self).exec()),bar)
        button('停用修讀記錄',lambda:self.guard(self.remove_student),bar)
        button('刪除選中修讀記錄',lambda:self.guard(self.delete_students),bar)
        button('刪除所選班級名單',lambda:self.guard(lambda:self.delete_students(True)),bar)
        self.students_table=table(['學號','中文姓名','英文姓名','科目','授課班','學年','學期','匯入來源','特殊學生原因（內部）']);layout.addWidget(self.students_table)
        self.students_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def build_courses(self):
        layout=self.page('科目管理','預設本科學士課程。複製整張科目表格，貼上分析後一次儲存；多人教師可由場次覆寫。')
        bar=QHBoxLayout();layout.addLayout(bar)
        self.course_search=QLineEdit();self.course_search.setPlaceholderText('搜尋科目');self.course_search.textChanged.connect(self.refresh_courses);bar.addWidget(self.course_search)
        button('新增',lambda:self.guard(lambda:self.course_form()),bar)
        button('編輯',lambda:self.guard(lambda:self.course_form(selected_row(self.courses_table))),bar)
        button('刪除未使用科目',lambda:self.guard(self.delete_course),bar)
        button('貼上表格・智能分析',lambda:self.guard(self.paste_courses),bar)
        self.courses_table=table(['代碼','中文名稱','英文名稱','教師','課程','學制']);layout.addWidget(self.courses_table)

    def build_rooms(self):
        layout=self.page('考場管理','只需輸入最多考生人數，例如 80 人，系統自動使用 001–080 座號。')
        bar=QHBoxLayout();layout.addLayout(bar)
        button('新增考場',lambda:self.guard(lambda:self.room_form()),bar)
        button('修改／停用',lambda:self.guard(lambda:self.room_form(selected_row(self.rooms_table))),bar)
        button('貼上表格・智能分析',lambda:self.guard(self.paste_rooms),bar)
        self.rooms_table=table(['名稱','最多人數','自動座號','啟用','備註']);layout.addWidget(self.rooms_table)

    def build_batches(self):
        layout=self.page('學年與考試','先選學年 → 學期 → 期中／期末，再建立科目場次。學院固定金融學院，課程預設本科；考試名稱自動產生。')
        bar=QHBoxLayout();layout.addLayout(bar)
        button('新增學年考試',lambda:self.guard(lambda:self.batch_form()),bar)
        button('編輯學年考試',lambda:self.guard(lambda:self.batch_form(selected_row(self.batches_table))),bar)
        button('刪除空設定',lambda:self.guard(self.delete_batch),bar)
        self.batches_table=table(['考試名稱（自動）','學年','學期','類型','學院／課程']);layout.addWidget(self.batches_table,1)
        bar2=QHBoxLayout();layout.addLayout(bar2)
        self.session_search=QLineEdit();self.session_search.setPlaceholderText('搜尋學年／學期／科目／日期');bar2.addWidget(self.session_search)
        self.session_search.textChanged.connect(self.refresh_sessions_table)
        button('建立場次',lambda:self.guard(self.new_session),bar2)
        button('修改場次／考場',lambda:self.guard(self.edit_session),bar2)
        button('複製設定',lambda:self.guard(self.copy_session),bar2)
        button('刪除場次',lambda:self.guard(self.delete_session),bar2)
        self.sessions_table=table(['批次','科目','日期','開始','結束','狀態']);layout.addWidget(self.sessions_table,2)
        self.sessions_table.cellDoubleClicked.connect(lambda *_:self.select_session(selected_row(self.sessions_table)['id'],5))

    def build_allocation(self):
        layout=self.page('考場編排','將左側班級拖入考場；將考場內班級拖回左側即可移出。移出只調整該考場，鎖定座位須先解除。')
        bar=QHBoxLayout();layout.addLayout(bar)
        button('復原',lambda:self.guard(lambda:self.history(False)),bar)
        button('重做',lambda:self.guard(lambda:self.history(True)),bar)
        button('加／減／更換考場',lambda:self.guard(lambda:self.edit_session(self.current_session())),bar)
        button('調整參加班級',lambda:self.guard(self.edit_session_classes),bar)
        button('驗證並完成編排',lambda:self.guard(self.complete_session),bar)
        button('編輯選中考場座位',self.open_seat_editor,bar)
        button('移出選中考場班級',lambda:self.guard(self.return_room_class),bar)
        split=QSplitter();layout.addWidget(split,1)
        self.class_cards=ClassCards();self.class_cards.setSpacing(10);split.addWidget(self.class_cards)
        self.room_cards=RoomCards();split.addWidget(self.room_cards)
        detail_widget=QWidget();d=QVBoxLayout(detail_widget);self.allocation_stats=QLabel();self.allocation_stats.setWordWrap(True);d.addWidget(self.allocation_stats)
        self.warnings=QLabel();self.warnings.setWordWrap(True);self.warnings.setObjectName('warnings');d.addWidget(self.warnings)
        self.pending_list=QListWidget();d.addWidget(self.pending_list);split.addWidget(detail_widget);split.setSizes([260,460,350])
        self.room_cards.classDropped.connect(self.class_dropped)
        self.room_cards.itemDoubleClicked.connect(lambda _:self.open_seat_editor())
        self.class_cards.itemDoubleClicked.connect(lambda _:self.guard(self.assign_selected))
        self.class_cards.assignedDropped.connect(lambda aid,cid,sid:self.guard(lambda:self.return_assigned_class(aid,cid,sid)))

    def build_seats(self):
        layout=self.page('座位調整','上下拖放學生重新排序。鎖定者保留實際座號；名單次序和座號分開保存。')
        top=QHBoxLayout();layout.addLayout(top)
        self.seat_room=QComboBox();self.seat_room.setMinimumWidth(220);self.seat_room.currentIndexChanged.connect(self.refresh_seats);top.addWidget(self.seat_room)
        self.seat_search=QLineEdit();self.seat_search.setPlaceholderText('搜尋學生（搜尋期間停用拖放排序）');self.seat_search.textChanged.connect(self.filter_seats);top.addWidget(self.seat_search)
        bar=QHBoxLayout();layout.addLayout(bar)
        button('移至首位',lambda:self.guard(lambda:self.move_position(0)),bar)
        button('指定序號',lambda:self.guard(self.position_dialog),bar)
        button('交換兩人',lambda:self.guard(self.swap_students),bar)
        button('座號／鎖定／特殊安排',lambda:self.guard(self.special_dialog),bar)
        button('調至其他考場',lambda:self.guard(self.move_room),bar)
        button('移回待分配',lambda:self.guard(self.unassign_selected),bar)
        bar2=QHBoxLayout();layout.addLayout(bar2)
        button('復原',lambda:self.guard(lambda:self.history(False)),bar2)
        button('重做',lambda:self.guard(lambda:self.history(True)),bar2)
        button('隨機打散座位',lambda:self.guard(self.shuffle_seats),bar2)
        button('特殊學生標記',lambda:self.guard(self.seat_student_flag),bar2)
        button('保存草稿',lambda:QMessageBox.information(self,'已保存','每次操作均已在資料庫交易中自動保存。'),bar2)
        button('返回考場編排',lambda:self.nav.setCurrentRow(5),bar2)
        self.seat_available=QLabel();self.seat_available.setWordWrap(True);layout.addWidget(self.seat_available)
        self.seat_tree=SeatTree();self.seat_tree.orderChanged.connect(lambda order:self.guard(lambda:self.reorder(order)))
        layout.addWidget(self.seat_tree,1)

    def build_generation(self):
        layout=self.page('文件生成中心','每個考場生成一份可編輯 Excel，包含一致的 Attendance 與 Seat Plan。內部特殊安排不會輸出。')
        filters=QHBoxLayout();layout.addLayout(filters)
        self.gen_filters=[]
        for placeholder in ['科目篩選','日期 YYYY-MM-DD','考場篩選']:
            f=QLineEdit();f.setPlaceholderText(placeholder);f.textChanged.connect(self.refresh_generation);filters.addWidget(f);self.gen_filters.append(f)
        self.only_complete=QCheckBox('只顯示已完成項目');self.only_complete.toggled.connect(self.refresh_generation);filters.addWidget(self.only_complete)
        ordering=QHBoxLayout();layout.addLayout(ordering)
        self.gen_batch=QComboBox();self.gen_batch.currentIndexChanged.connect(self.refresh_generation);ordering.addWidget(self.gen_batch)
        self.gen_sort=QComboBox()
        for label,value in [('按批次／科目排列','batch'),('按最後修改：新到舊','modified'),('按最後生成：新到舊','generated')]:self.gen_sort.addItem(label,value)
        self.gen_sort.currentIndexChanged.connect(self.refresh_generation);ordering.addWidget(self.gen_sort)
        ordering.addWidget(QLabel('同一場次的考場保持相鄰'))
        self.include_class_index=QCheckBox('簽到表末尾附班級座號索引（細字）')
        self.include_class_index.setToolTip('按實際座號列出各授課班的連續範圍及零散座號；座位表不加標記。')
        layout.addWidget(self.include_class_index)
        bar=QHBoxLayout();layout.addLayout(bar)
        button('全選',lambda:self.check_generation(True),bar);button('取消全選',lambda:self.check_generation(False),bar)
        button('生成選中項目',lambda:self.guard(self.generate_selected),bar)
        button('打開輸出資料夾',lambda:self.guard(self.open_output),bar)
        button('打開已生成文件',lambda:self.guard(self.open_generated),bar)
        button('刪除勾選考場項目',lambda:self.guard(self.delete_generation),bar)
        self.generation_table=table(['選取','批次','科目','日期','時間','考場','人數','狀態','最後修改','最後生成'])
        self.generation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.generation_table)
        self.generation_results=QListWidget();layout.addWidget(self.generation_results,1)

    def build_settings(self):
        layout=self.page('設定與資料備份','備份使用獨立檔案；還原前自動另存現有資料庫，不會無提示覆蓋。')
        self.db_location=QLabel(str(self.manager.db.path));self.db_location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.db_location)
        bar=QHBoxLayout();layout.addLayout(bar)
        button('備份資料庫',lambda:self.guard(self.backup),bar)
        button('還原資料庫',lambda:self.guard(self.restore),bar)
        button('打開資料目錄',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.manager.db.path.parent))),bar)
        self.log_table=table(['來源／文件','時間','結果']);layout.addWidget(self.log_table)
        layout.addWidget(QLabel('本工具無登入、網絡 API、CDN 或遠端字型。Excel 匯入不執行巨集、公式或外部連結。'))

    def current_session(self):
        sid=self.session_combo.currentData()
        if not sid:raise ValidationError('請先建立並選取考試場次。')
        return sid

    def select_session(self,sid,page=None):
        ix=self.session_combo.findData(sid)
        if ix>=0:self.session_combo.setCurrentIndex(ix)
        if page is not None:self.nav.setCurrentRow(page)

    def refresh_all(self):
        populate(self.session_combo,[(f'{s["code"]} · {s["date"]} {s["start"]} · {s["batch_name"]}',s['id']) for s in self.manager.sessions()])
        populate(self.student_course,[(c['code']+' '+c['name_cn'],c['id']) for c in self.manager.courses()],'全部科目')
        rows=self.manager.students()
        for combo,key,label in [(self.student_year,'academic_year','全部學年'),(self.student_term,'semester','全部學期'),(self.student_source,'source','全部匯入來源')]:
            populate(combo,[(v,v) for v in sorted({r[key] for r in rows if r[key]})],label)
        populate(self.gen_batch,[(b['name'],b['id']) for b in self.manager.batches()],'全部批次')
        self.refresh_student_classes();self.refresh_courses();self.refresh_rooms();self.refresh_batches();self.refresh_workflow()
        stats=self.manager.dashboard()
        self.stats.setText(f'學生 {stats["students"]}    科目 {stats["courses"]}    批次 {stats["batches"]}    場次 {stats["sessions"]}\n'
                           f'考場分配 {stats["allocations"]}    完成場次 {stats["complete"]}    未完成 {stats["pending"]}')
        fill_table(self.dashboard_table,self.manager.sessions(),['batch_name','code','date','start','status'])
        logs=[{'source':r['source'],'created':r['created'],'status':r['summary']} for r in self.manager.db.rows('SELECT * FROM import_logs ORDER BY created DESC LIMIT 100')]
        logs += [{'source':r['path'],'created':r['created'],'status':r['status']} for r in self.manager.db.rows('SELECT * FROM generation_logs ORDER BY created DESC LIMIT 100')]
        fill_table(self.log_table,logs,['source','created','status'])

    def refresh_student_classes(self):
        populate(self.student_class,[(c['code']+' '+c['name']+' 班 · '+c['academic_year']+' '+c['semester'],c['id']) for c in self.manager.classes(self.student_course.currentData())],'全部班級')
        self.refresh_students()

    def refresh_students(self):
        rows=self.manager.students(self.student_search.text(),self.student_course.currentData(),self.student_class.currentData())
        rows=[r for r in rows if all(not combo.currentData() or r[key]==combo.currentData() for combo,key in
              [(self.student_year,'academic_year'),(self.student_term,'semester'),(self.student_source,'source')])]
        if self.flagged_only.isChecked():rows=[r for r in rows if r['flag_reason']]
        fill_table(self.students_table,rows,
                   ['student_no','chinese_name','english_name','course_code','class_name','academic_year','semester','source','flag_reason'])
        self.class_counts.setText(f'目前篩選：{len(rows)} 筆修讀記錄 · {len({r["student_no"] for r in rows})} 位學生 · {len({r["class_id"] for r in rows})} 個授課班（可 Ctrl／Shift 多選刪除）')

    def clear_student_filters(self):
        self.student_search.clear()
        self.flagged_only.setChecked(False)
        for combo in [self.student_course,self.student_class,self.student_year,self.student_term,self.student_source]:combo.setCurrentIndex(0)

    def refresh_courses(self):
        search=self.course_search.text().lower()
        fill_table(self.courses_table,[c for c in self.manager.courses() if search in ' '.join(str(v) for v in c.values()).lower()],
                   ['code','name_cn','name_en','teachers','programme','language'])

    def refresh_rooms(self):
        rows=[dict(r,seat_range=f'001–{r["capacity"]:03d}') for r in self.manager.rooms()]
        fill_table(self.rooms_table,rows,['name','capacity','seat_range','enabled','notes'])

    def refresh_batches(self):
        fill_table(self.batches_table,self.manager.batches(),['name','academic_year','semester','exam_type','programme']);self.refresh_sessions_table()

    def refresh_sessions_table(self):
        search=self.session_search.text().lower()
        fill_table(self.sessions_table,[s for s in self.manager.sessions() if search in ' '.join(str(v) for v in s.values()).lower()],
                   ['batch_name','code','date','start','end','status'])

    def refresh_workflow(self):
        sid=self.session_combo.currentData();self.class_cards.clear();self.room_cards.clear();self.pending_list.clear()
        self.paper_page.load_session(sid)
        self.class_cards.session_id=sid
        if not sid:
            self.allocation_stats.setText('請先建立考試場次。');self.warnings.clear();populate(self.seat_room,[]);self.refresh_seats();self.refresh_generation();return
        pending=self.manager.pending(sid);assigned=self.manager.assigned(sid)
        ids=[r['class_id'] for r in self.manager.db.rows('SELECT class_id FROM session_classes WHERE session_id=?',(sid,))]
        for c in self.manager.classes():
            if c['id'] not in ids:continue
            unassigned=sum(p['class_id']==c['id'] for p in pending)
            item=QListWidgetItem(f'{c["code"]} · {c["name"]} 班\n{c["count"]} 人  /  待分配 {unassigned} 人')
            item.setData(Qt.ItemDataRole.UserRole,c['id']);item.setSizeHint(QSize(200,82))
            if not unassigned:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.class_cards.addItem(item)
        allocations=self.manager.allocations(sid)
        for al in allocations:
            remain,_=self.manager.remaining(al['id'])
            class_ids=list(dict.fromkeys(r['class_id'] for r in assigned if r['allocation_id']==al['id']))
            item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,al['id']);self.room_cards.addItem(item)
            card=QFrame();card.setObjectName('roomCard');v=QVBoxLayout(card)
            flagged=sum(bool(r['flag_reason']) for r in assigned if r['allocation_id']==al['id'])
            v.addWidget(QLabel(f'{al["room_name"]}     {al["count"]} / {al["capacity"]} 人'+(f'  ⚑ 特殊學生 {flagged} 人' if flagged else '')))
            bar=QProgressBar();bar.setRange(0,al['capacity']);bar.setValue(al['count']);v.addWidget(bar)
            v.addWidget(QLabel(f'剩餘可用 {remain} 座位 · 拖入班級或雙擊編輯座位'))
            if class_ids:
                class_list=AssignedClassCards(al['id'],sid)
                for cid in class_ids:
                    rr=[r for r in assigned if r['allocation_id']==al['id'] and r['class_id']==cid]
                    entry=QListWidgetItem(f'{rr[0]["class_name"]} 班 · {len(rr)} 人（拖回左側移出）')
                    entry.setData(Qt.ItemDataRole.UserRole,cid);class_list.addItem(entry)
                class_list.ensurePolished()
                class_list.setFixedHeight(sum(max(44,class_list.sizeHintForRow(i)) for i in range(class_list.count()))+24)
                class_list.itemPressed.connect(lambda _,current=item:self.room_cards.setCurrentItem(current))
                v.addWidget(class_list)
            self.room_cards.setItemWidget(item,card)
            item.setSizeHint(QSize(350,card.sizeHint().height()+16))
        self.allocation_stats.setText(f'已分配：{len(assigned)} 人\n未分配：{len(pending)} 人\n'
                                     +'\n'.join(f'{a["room_name"]} 使用率：{a["count"]/a["capacity"]:.0%}' for a in allocations))
        errors=self.manager.validate(sid,False);self.warnings.setText('\n'.join(errors) or '資料檢查：目前沒有衝突')
        for s in pending:self.pending_list.addItem(('⚑ ' if s['flag_reason'] else '')+f'{s["class_name"]} · {s["student_no"]} · {s["chinese_name"]}')
        populate(self.seat_room,[(f'{a["room_name"]} · {a["count"]} 人',a['id']) for a in allocations])
        self.refresh_seats();self.refresh_generation()

    def refresh_seats(self):
        self.seat_tree.clear();aid=self.seat_room.currentData()
        if not aid:self.seat_available.setText('請先選擇考場。');return
        for i,r in enumerate(self.manager.assigned(aid=aid)):
            item=QTreeWidgetItem([str(i+1),r['seat']+(' 🔒' if r['locked'] else ''),r['student_no'],r['chinese_name'],r['english_name'],r['class_name'],r['special'],r['flag_reason']])
            item.setData(0,Qt.ItemDataRole.UserRole,r['id']);item.setFlags((item.flags()|Qt.ItemFlag.ItemIsDragEnabled)&~Qt.ItemFlag.ItemIsDropEnabled)
            self.seat_tree.addTopLevelItem(item)
        remaining,seats=self.manager.remaining(aid)
        self.seat_available.setText(f'剩餘 {remaining} 個座位；可用座號：'+', '.join(seats))
        for i in range(8):self.seat_tree.resizeColumnToContents(i)
        self.filter_seats()

    def filter_seats(self):
        search=self.seat_search.text().lower()
        for i in range(self.seat_tree.topLevelItemCount()):
            item=self.seat_tree.topLevelItem(i);item.setHidden(search not in ' '.join(item.text(c) for c in range(8)).lower())

    def refresh_generation(self):
        checked=set()
        for i in range(self.generation_table.rowCount()):
            item=self.generation_table.item(i,0)
            if item and item.checkState()==Qt.CheckState.Checked:checked.add(item.data(Qt.ItemDataRole.UserRole)['id'])
        sessions={s['id']:s for s in self.manager.sessions()};rows=[]
        allocations=self.manager.allocations();flag_counts={}
        for flagged in self.manager.flagged_in_allocations([a['id'] for a in allocations]):
            key=flagged['allocation_id'];flag_counts[key]=flag_counts.get(key,0)+1
        course,dt,room=[f.text().lower() for f in self.gen_filters]
        for al in allocations:
            s=sessions[al['session_id']]
            if self.gen_batch.currentData() and s['batch_id']!=self.gen_batch.currentData():continue
            valid=not self.manager.validate(s['id'])
            if course not in (s['code']+' '+s['name_cn']).lower() or dt not in s['date'] or room not in al['room_name'].lower():continue
            if self.only_complete.isChecked() and (not valid or s['status'] not in ('已完成編排','已生成文件')):continue
            generated=self.manager.db.one("SELECT * FROM generation_logs WHERE allocation_id=? AND status='成功' ORDER BY created DESC,rowid DESC LIMIT 1",(al['id'],))
            rows.append(dict(al,batch_id=s['batch_id'],batch_name=s['batch_name'],course=s['code']+' '+s['name_cn'],date=s['date'],time=s['start']+'–'+s['end'],status=s['status'] if valid else '待處理錯誤',modified=s['modified'],generated=generated['created'] if generated else '',path=generated['path'] if generated else ''))
            if flag_counts.get(al['id']):rows[-1]['status']+=f' · ⚑ {flag_counts[al["id"]]} 位特殊學生'
        rows.sort(key=lambda r:(r['batch_name'],r['batch_id'],r['course'],r['date'],r['time'],r['session_id'],r['room_name']))
        sort=self.gen_sort.currentData()
        if sort in ('modified','generated'):
            latest={}
            for r in rows:latest[r['session_id']]=max(latest.get(r['session_id'],''),r[sort])
            rows.sort(key=lambda r:latest[r['session_id']],reverse=True)
        for r in rows:
            r['modified_display']=r['modified'].replace('T',' ')[:19]
            r['generated_display']=r['generated'].replace('T',' ')[:19] or '—'
        fill_table(self.generation_table,rows,['id','batch_name','course','date','time','room_name','count','status','modified_display','generated_display'])
        for i,r in enumerate(rows):
            item=self.generation_table.item(i,0);item.setText('');item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked if r['id'] in checked else Qt.CheckState.Unchecked)

    def pick_import(self):
        paths,_=QFileDialog.getOpenFileNames(self,'選擇學生名單','','Excel (*.xlsx)')
        if paths:self.guard(lambda:self.import_paths(paths))

    def import_paths(self,paths):
        d=ImportDialog(self.manager,paths,self)
        if d.exec()==QDialog.DialogCode.Accepted:self.refresh_all();self.nav.setCurrentRow(1)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower()=='.xlsx' for u in event.mimeData().urls()):event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:self.guard(lambda:self.import_paths(paths));event.acceptProposedAction()

    def course_form(self,old=None):
        d=FormDialog('科目資料',COURSE_FIELDS,old,self)
        programme=QComboBox()
        for code,(cn,en) in PROGRAMMES.items():programme.addItem(f'{code} · {cn}',code)
        d.layout().insertRow(0,'課程',programme)
        if d.exec()==QDialog.DialogCode.Accepted:self.manager.save_course(dict(programme_values(programme.currentData()),**d.values()),old['id'] if old else None);self.refresh_all()

    def room_form(self,old=None):
        d=FormDialog('考場資料',ROOM_FIELDS,old or {'capacity':80,'enabled':1},self)
        if d.exec()==QDialog.DialogCode.Accepted:self.manager.save_room(dict(d.values(),usable_seats=''),old['id'] if old else None);self.refresh_all()

    def batch_form(self,old=None):
        d=BatchDialog(old,self)
        if d.exec()==QDialog.DialogCode.Accepted:self.manager.save_batch(d.values(),old['id'] if old else None);self.refresh_all()

    def delete_course(self):
        r=selected_row(self.courses_table)
        if QMessageBox.question(self,'刪除科目',f'刪除 {r["code"]}？')==QMessageBox.StandardButton.Yes:self.manager.delete_course(r['id']);self.refresh_all()

    def paste_courses(self):
        d=CoursePasteDialog(self.manager,self)
        if d.exec()==QDialog.DialogCode.Accepted:self.refresh_all()

    def paste_rooms(self):
        d=RoomPasteDialog(self.manager,self)
        if d.exec()==QDialog.DialogCode.Accepted:self.refresh_all()

    def add_student(self):
        courses=[(c['code']+' '+c['name_cn'],c['code']) for c in self.manager.courses()]
        if not courses:raise ValidationError('請先建立科目。')
        d=FormDialog('手動新增修讀記錄',[('student_no','學號','line'),('chinese_name','中文姓名','line'),('english_name','英文姓名','line'),
                      ('course_code','科目',courses),('class_id','已存在授課班',[]),('class_name','新增授課班名稱（沒有名單時）','line')],parent=self)
        def choices():
            code=d.editors['course_code'].currentData()
            populate(d.editors['class_id'],[(c['name']+' · '+c['academic_year']+' '+c['semester'],c['id']) for c in self.manager.classes() if c['code']==code],'新增授課班（手動輸入）')
        d.editors['course_code'].currentIndexChanged.connect(choices);choices()
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();cid=v.pop('class_id');metadata={}
            if cid:
                cls=next(c for c in self.manager.classes() if c['id']==cid)
                v['class_name']=cls['name']
                metadata={k:cls[k] for k in ['teaching_code','academic_year','semester','programme_code','grade']}
            elif any(c['code']==v['course_code'] and c['name']==v['class_name'] for c in self.manager.classes()):
                raise ValidationError('此授課班已有名單，請從「已存在授課班」選取對應學年學期。')
            self.manager.import_records([StudentRecord(**v,**metadata,source='手動新增',raw_name=v['chinese_name']+' '+v['english_name'])]);self.refresh_all()

    def edit_student(self):
        r=selected_row(self.students_table)
        d=FormDialog('編輯學生身份（所有科目同步）',[('student_no','學號','line'),('chinese_name','中文姓名','line'),('english_name','英文姓名','line')],r,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();self.manager.edit_student(r['id'],v['student_no'],v['chinese_name'],v['english_name']);self.refresh_all()

    def remove_student(self):
        r=selected_row(self.students_table)
        if QMessageBox.question(self,'停用修讀',f'停用 {r["course_code"]} {r["class_name"]} 的此學生？\n其他科目與已編排座位會保留；已有座位必須在輸出前人工移除。')==QMessageBox.StandardButton.Yes:
            self.manager.deactivate_enrollment(r['enrollment_id']);self.refresh_all()

    def delete_students(self,whole_class=False):
        if whole_class:
            cid=self.student_class.currentData()
            if not cid:raise ValidationError('請先在班級篩選選取要刪除的授課班。')
            c=next(c for c in self.manager.classes() if c['id']==cid)
            identifiers=[r['id'] for r in self.manager.db.rows('SELECT id FROM enrollments WHERE class_id=?',(cid,))]
            scope=f'{c["code"]} {c["name"]} 班全部 {len(identifiers)} 筆修讀記錄（包括停用記錄，不限目前搜尋結果）'
        else:
            rows=sorted({index.row() for index in self.students_table.selectedIndexes()})
            identifiers=[self.students_table.item(row,0).data(Qt.ItemDataRole.UserRole)['enrollment_id'] for row in rows]
            scope=f'選中的 {len(identifiers)} 筆修讀記錄'
        if not identifiers:raise ValidationError('請先選取要刪除的記錄。')
        text=f'刪除{scope}？\n系統先備份資料庫；此修讀記錄的座位亦會刪除，其他科目修讀保留。相關場次復原歷史會清除，已有 Excel 檔案保留。'
        if QMessageBox.question(self,'刪除名單',text)!=QMessageBox.StandardButton.Yes:return
        self.manager.delete_enrollments(identifiers);self.refresh_all()

    def return_assigned_class(self,aid,cid,sid):
        if sid!=self.current_session():raise ValidationError('請在同一場次內移出班級。')
        allocation=next((a for a in self.manager.allocations(sid) if a['id']==aid),None)
        if not allocation:raise ValidationError('考場已變更，請重新選取。')
        rows=[r for r in self.manager.assigned(aid=aid) if r['class_id']==cid]
        if not rows:raise ValidationError('此班在該考場沒有學生。')
        self.manager.unassign([r['id'] for r in rows]);self.refresh_all()

    def return_room_class(self):
        item=self.room_cards.currentItem()
        if not item:raise ValidationError('請先選取考場。')
        aid=item.data(Qt.ItemDataRole.UserRole)
        rows=self.manager.assigned(aid=aid)
        classes=list(dict.fromkeys(r['class_id'] for r in rows))
        if not classes:raise ValidationError('此考場沒有已分配學生。')
        labels=[next(r['class_name'] for r in rows if r['class_id']==cid)+' 班' for cid in classes]
        label,ok=QInputDialog.getItem(self,'移出考場','選擇要移回待分配的班級',labels,0,False)
        if ok:self.return_assigned_class(aid,classes[labels.index(label)],self.current_session())

    def delete_generation(self):
        rows=[self.generation_table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(self.generation_table.rowCount())
              if self.generation_table.item(i,0).checkState()==Qt.CheckState.Checked]
        if not rows:raise ValidationError('請先勾選要刪除的考場項目。')
        details='\n'.join(f'{r["course"]} · {r["date"]} · {r["room_name"]} · {r["count"]} 人' for r in rows)
        text=f'刪除以下 {len(rows)} 個考場項目及其座位編排？\n{details}\n先備份資料庫；學生回到待分配，其他考場保持不變，相關場次復原歷史清除。已有 Excel 檔案保留。'
        if QMessageBox.question(self,'刪除考場項目',text)!=QMessageBox.StandardButton.Yes:return
        self.manager.delete_allocations([r['id'] for r in rows]);self.refresh_all()

    def delete_batch(self):
        r=selected_row(self.batches_table)
        if self.manager.db.one('SELECT id FROM exams WHERE batch_id=?',(r['id'],)):raise ValidationError('此批次已有考試，請先刪除場次。')
        if QMessageBox.question(self,'刪除批次','確定刪除此空批次？')==QMessageBox.StandardButton.Yes:
            with self.manager.db.conn:self.manager.db.conn.execute('DELETE FROM batches WHERE id=?',(r['id'],))
            self.refresh_all()

    def new_session(self):
        if not self.manager.courses() or not self.manager.batches() or not self.manager.rooms():raise ValidationError('請先匯入名單、建立科目、考場與學年考試設定。')
        d=SessionDialog(self.manager,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();sid=self.manager.create_session(v.pop('batch_id'),v.pop('course_id'),v,d.checked(d.classes),d.checked(d.rooms))
            self.refresh_all();self.select_session(sid,5)

    def edit_session(self,sid=None):
        r=next(s for s in self.manager.sessions() if s['id']==sid) if sid else selected_row(self.sessions_table)
        d=SessionDialog(self.manager,self,r)
        if d.exec()==QDialog.DialogCode.Accepted:
            self.manager.update_session(r['id'],d.values(),{aid:choice.currentData() for aid,choice in d.room_replacements.items()},d.checked(d.rooms))
            self.refresh_all()

    def copy_session(self):
        r=selected_row(self.sessions_table)
        sid=self.manager.copy_session(r['id']);self.refresh_all();self.select_session(sid,5)
        QMessageBox.information(self,'已複製設定','新場次日期預設為次日；班級與考場已複製，學生尚未分配。請確認日期與時段。')

    def delete_session(self):
        r=selected_row(self.sessions_table)
        if QMessageBox.question(self,'刪除場次','刪除本場次及座位編排？學生與科目不會刪除。')==QMessageBox.StandardButton.Yes:self.manager.delete_session(r['id']);self.refresh_all()

    def add_allocation_room(self):
        sid=self.current_session();existing={a['room_id'] for a in self.manager.allocations(sid)}
        choices=[(r['name'],r['id']) for r in self.manager.rooms() if r['enabled'] and r['id'] not in existing]
        if not choices:raise ValidationError('沒有其他啟用考場。')
        d=FormDialog('新增考場分配',[('room_id','考場',choices)],parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:
            room=d.values()['room_id'];self.manager.check_room_conflict(sid,room)
            with self.manager.db.conn:self.manager.db.conn.execute('INSERT INTO allocations VALUES(?,?,?)',(uid(),sid,room))
            self.refresh_all()

    def edit_session_classes(self):
        sid=self.current_session();s=next(s for s in self.manager.sessions() if s['id']==sid)
        d=QDialog(self);d.setWindowTitle('調整參加班級');v=QVBoxLayout(d);lst=QListWidget();v.addWidget(lst)
        current={c['class_id'] for c in self.manager.db.rows('SELECT class_id FROM session_classes WHERE session_id=?',(sid,))}
        for c in self.manager.classes(s['course_id']):
            SessionDialog.add_check(lst,f'{c["name"]} · {c["count"]} 人',c['id'])
            lst.item(lst.count()-1).setCheckState(Qt.CheckState.Checked if c['id'] in current else Qt.CheckState.Unchecked)
        button('保存',d.accept,v);button('取消',d.reject,v)
        if d.exec()==QDialog.DialogCode.Accepted:
            chosen=set(SessionDialog.checked(lst))
            if not chosen:raise ValidationError('至少選取一個班級。')
            if any(r['class_id'] not in chosen for r in self.manager.assigned(sid)):raise ValidationError('被移除班級仍有座位；請先移回待分配。')
            with self.manager.db.conn:
                self.manager.db.conn.execute('DELETE FROM session_classes WHERE session_id=?',(sid,))
                self.manager.db.conn.executemany('INSERT INTO session_classes VALUES(?,?)',[(sid,c) for c in chosen])
                self.manager.db.conn.execute("UPDATE sessions SET status='草稿',modified=? WHERE id=?",(now(),sid))
            self.refresh_all()

    def class_dropped(self,aid,cid,sid):
        if sid!=self.session_combo.currentData():return
        self.guard(lambda:self.assign_class(aid,cid))

    def assign_selected(self):
        c=self.class_cards.currentItem();r=self.room_cards.currentItem()
        if not c or not r:raise ValidationError('請選取班級和考場，或將班級拖到考場。')
        self.assign_class(r.data(Qt.ItemDataRole.UserRole),c.data(Qt.ItemDataRole.UserRole))

    def assign_class(self,aid,cid):
        try:self.manager.assign(aid,class_id=cid)
        except CapacityError as e:
            if e.remaining==0:QMessageBox.warning(self,'容量不足',str(e));return
            box=QMessageBox(self);box.setWindowTitle('容量不足');box.setText(str(e));split=box.addButton('拆分班級',QMessageBox.ButtonRole.AcceptRole)
            box.addButton('取消整班分配',QMessageBox.ButtonRole.RejectRole);box.exec()
            if box.clickedButton()!=split:return
            rows=self.manager.pending(self.current_session(),cid);d=SelectionDialog('拆分班級 · 選擇學生',rows,e.remaining,self)
            if d.exec()!=QDialog.DialogCode.Accepted:return
            chosen=d.selected()
            if not chosen or len(chosen)>e.remaining:raise ValidationError(f'請選擇 1–{e.remaining} 人。')
            self.manager.assign(aid,class_id=cid,student_ids=chosen)
        self.refresh_all()

    def open_seat_editor(self):
        item=self.room_cards.currentItem()
        if item:
            ix=self.seat_room.findData(item.data(Qt.ItemDataRole.UserRole))
            if ix>=0:self.seat_room.setCurrentIndex(ix)
        self.nav.setCurrentRow(6)

    def selected_assignments(self):
        ids=[i.data(0,Qt.ItemDataRole.UserRole) for i in self.seat_tree.selectedItems()]
        if not ids:raise ValidationError('請選擇學生。')
        return ids

    def reorder(self,order):
        try:self.manager.reorder(self.seat_room.currentData(),order)
        finally:self.refresh_all()

    def move_position(self,position):
        ids=self.selected_assignments()
        if len(ids)!=1:raise ValidationError('請選擇一名學生。')
        order=self.seat_tree.order();order.remove(ids[0]);order.insert(position,ids[0]);self.reorder(order)

    def position_dialog(self):
        n,ok=QInputDialog.getInt(self,'指定序號','移至第幾位？',1,1,self.seat_tree.topLevelItemCount())
        if ok:self.move_position(n-1)

    def swap_students(self):
        ids=self.selected_assignments()
        if len(ids)!=2:raise ValidationError('按 Ctrl 選擇兩名學生。')
        order=self.seat_tree.order();a,b=[order.index(i) for i in ids];order[a],order[b]=order[b],order[a];self.reorder(order)

    def special_dialog(self):
        ids=self.selected_assignments()
        if len(ids)!=1:raise ValidationError('請選擇一名學生。')
        r=next(r for r in self.manager.assigned() if r['id']==ids[0])
        fields=[('seat','指定座號','line'),('locked','鎖定實際座號','bool'),
                ('special','內部安排類型',[('無',''),('需要前排','需要前排'),('需要指定座位','需要指定座位'),('其他特殊安排','其他特殊安排')]),('note','內部備註（不輸出）','text')]
        d=FormDialog('特殊安排',fields,r,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();self.manager.special(r['id'],v['seat'],v['locked'],v['special'],v['note']);self.refresh_all()

    def move_room(self):
        ids=self.selected_assignments();current=self.seat_room.currentData()
        choices=[(a['room_name'],a['id']) for a in self.manager.allocations(self.current_session()) if a['id']!=current]
        if not choices:raise ValidationError('請先新增另一考場。')
        d=FormDialog('調至其他考場',[('aid','目標考場',choices)],parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:self.manager.move_students(ids,d.values()['aid']);self.refresh_all()

    def unassign_selected(self):
        ids=self.selected_assignments()
        self.manager.unassign(ids);self.refresh_all()

    def shuffle_seats(self):
        aid=self.seat_room.currentData()
        if not aid:raise ValidationError('請先選擇考場。')
        if self.seat_search.text().strip():raise ValidationError('請先清除搜尋，再隨機打散整個考場。')
        rows=self.manager.assigned(aid=aid)
        unlocked=sum(not r['locked'] for r in rows)
        if unlocked<2:raise ValidationError('至少需要兩位未鎖定座號的學生，才可隨機打散。')
        name=next(a['room_name'] for a in self.manager.allocations() if a['id']==aid)
        if QMessageBox.question(self,'隨機打散座位',f'隨機打散 {name} 的 {unlocked} 位學生？\n已鎖定的 {len(rows)-unlocked} 位學生保留座號及名單位置，其他考場保持不變。\n可按「復原」還原；完成後請重新生成 Excel。')!=QMessageBox.StandardButton.Yes:return
        self.manager.shuffle_seats(aid);self.refresh_all()

    def student_flag_form(self,student):
        identifier=student.get('student_id',student['id'])
        current=self.manager.db.one('SELECT reason FROM student_flags WHERE student_id=?',(identifier,))
        dialog=FormDialog('特殊學生標記（跨科目保存，不輸出）',[
            ('enabled','啟用特殊學生標記','bool'),('reason','原因（例如作弊，僅內部提醒）','text')],
            dict(enabled=True,reason=current['reason'] if current else ''),self)
        identity=QLabel(student['student_no']+' · '+student['chinese_name']+' · '+student['english_name'])
        identity.setTextFormat(Qt.TextFormat.PlainText);dialog.layout().insertRow(0,'學生',identity)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        values=dialog.values();self.manager.set_student_flag(identifier,values['reason'],bool(values['enabled']));self.refresh_all()

    def seat_student_flag(self):
        identifiers=self.selected_assignments()
        if len(identifiers)!=1:raise ValidationError('請選取一位學生。')
        self.student_flag_form(next(r for r in self.manager.assigned() if r['id']==identifiers[0]))

    def history(self,redo):self.manager.undo(self.current_session(),redo);self.refresh_all()

    def complete_session(self):self.manager.complete(self.current_session());self.refresh_all();QMessageBox.information(self,'編排完成','沒有未分配學生或資料衝突，可前往文件生成中心。')

    def check_generation(self,value):
        for i in range(self.generation_table.rowCount()):self.generation_table.item(i,0).setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)

    def confirm_flagged_students(self,aids):
        alerts=self.manager.flagged_in_allocations(aids)
        if not alerts:return True
        reminder=StudentFlagReminder(alerts,len(aids),self)
        if reminder.exec()==QDialog.DialogCode.Accepted:return True
        if reminder.allocation_id:
            al=next(a for a in self.manager.allocations() if a['id']==reminder.allocation_id)
            self.select_session(al['session_id'],6);self.seat_search.clear()
            self.seat_room.setCurrentIndex(self.seat_room.findData(al['id']))
            for i in range(self.seat_tree.topLevelItemCount()):
                item=self.seat_tree.topLevelItem(i)
                if item.data(0,Qt.ItemDataRole.UserRole)==reminder.assignment_id:
                    self.seat_tree.setCurrentItem(item);self.seat_tree.scrollToItem(item);break
        return False

    def generate_selected(self):
        aids=[self.generation_table.item(i,0).data(Qt.ItemDataRole.UserRole)['id'] for i in range(self.generation_table.rowCount()) if self.generation_table.item(i,0).checkState()==Qt.CheckState.Checked]
        if not aids:raise ValidationError('請勾選要生成的考場項目。')
        errors=[]
        for aid in aids:
            try:self.manager.export_data(aid)
            except ValidationError as e:errors.append(str(e))
        if errors:raise ValidationError('生成前檢查未通過：\n'+'\n'.join(dict.fromkeys(errors)))
        alerts=self.manager.flagged_in_allocations(aids)
        if alerts:
            if not self.confirm_flagged_students(aids):return
        elif QMessageBox.question(self,'生成確認',f'即將生成 {len(aids)} 份 Excel，是否繼續？')!=QMessageBox.StandardButton.Yes:return
        folder=QFileDialog.getExistingDirectory(self,'選擇輸出資料夾',str(self.last_output or default_output_directory(self.manager)))
        if not folder:return
        progress=QProgressDialog('正在生成文件…','取消剩餘項目',0,len(aids),self);progress.setWindowModality(Qt.WindowModality.ApplicationModal);progress.setMinimumDuration(0)
        self.generation_results.clear();results=[];self.last_output=Path(folder)
        for i,aid in enumerate(aids):
            if progress.wasCanceled():
                for skipped in aids[i:]:results.append((skipped,'取消','未執行'))
                break
            info,_=self.manager.export_data(aid);path=Path(folder)/safe_filename(info);policy='error'
            if path.exists():
                box=QMessageBox(self);box.setWindowTitle('同名文件已存在');box.setText(path.name)
                over=box.addButton('覆蓋',QMessageBox.ButtonRole.DestructiveRole);rename=box.addButton('另存新檔',QMessageBox.ButtonRole.AcceptRole)
                box.addButton('跳過',QMessageBox.ButtonRole.RejectRole);box.exec()
                policy='overwrite' if box.clickedButton()==over else 'rename' if box.clickedButton()==rename else 'skip'
            result=self.exporter.batch([aid],folder,policy,include_class_index=self.include_class_index.isChecked())[0];results.append(result)
            self.generation_results.addItem(' · '.join(result[1:]));progress.setValue(i+1)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
        progress.close();self.refresh_all()
        QMessageBox.information(self,'生成結果',f'成功：{sum(r[1]=="成功" for r in results)} 份\n失敗：{sum(r[1]=="失敗" for r in results)} 份\n跳過／取消：{sum(r[1] in ("跳過","取消") for r in results)} 份')

    def open_output(self):
        if not self.last_output:
            row=self.manager.db.one("SELECT path FROM generation_logs WHERE status='成功' ORDER BY created DESC,rowid DESC LIMIT 1")
            if row:self.last_output=Path(row['path']).parent
        if not self.last_output:self.last_output=default_output_directory(self.manager)
        self.last_output.mkdir(parents=True,exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output))):raise ValidationError('無法開啟資料夾，請使用檔案總管開啟輸出路徑。')

    def open_generated(self):
        r=selected_row(self.generation_table)
        if not r['path'] or not Path(r['path']).exists():raise ValidationError('未生成或文件已移動。')
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(r['path'])):raise ValidationError('無法開啟文件，請確認已安裝 Excel 或相容軟件。')

    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'備份到新檔案',f'FOF_backup_{date.today()}.sqlite3','SQLite (*.sqlite3)')
        if path:self.manager.db.backup(path);QMessageBox.information(self,'備份成功',path)

    def restore(self):
        path,_=QFileDialog.getOpenFileName(self,'選擇備份檔案','','SQLite (*.sqlite3)')
        if not path:return
        if QMessageBox.question(self,'還原確認','還原將取代目前資料。系統會先自動備份現有資料庫，是否繼續？')!=QMessageBox.StandardButton.Yes:return
        backup=self.manager.db.restore(path)
        repaired=self.manager.repair_combined_names()
        self.refresh_all();QMessageBox.information(self,'已還原','原資料已保存至：\n'+str(backup)+f'\n已拆分舊姓名：{repaired} 人')

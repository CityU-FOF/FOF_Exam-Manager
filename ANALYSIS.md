# Phase 1：實際附件與架構分析

## 學生名單：v1.1 修正授課班語意

四份名單 A:J 的 E 欄是行政班，不是科目授課班。A 帳號、B 中文姓名、C 英文姓名、D 課程、E 行政班；後五欄成績、特殊情形及備註不匯入成身份或特殊安排。

完整科目代碼在 B6，例如 `261BAECF3DBAE30500`，解碼為 2026–2027、第一學期、BAECF、3D 授課班、BAE305。I6 是短科目編號，用於核對；B3 可提供科目中文名稱。BAECF 固定對應「應用經濟學學士學位課程 (中文學制) / Bachelor of Applied Economics Programme (Chinese)」。

匯總 Sheet 表頭第9行、學生第10行開始；行政分頁表頭第8行、學生第9行開始。底部教師簽字及日期不是學生。存在匯總時採完整匯總；只有行政分頁時按相同完整科目代碼合併，依學號去重。有姓名衝突則要求人工核對，不按行政班排除任何修讀學生。

| 檔案 | 授課班 | 行政班組成 | 正確修讀人數 |
|---|---|---|---:|
| 3D.xlsx | 3D | D29 + A1 | 30 |
| 3E.xlsx | 3E | E28 | 28 |
| 3F.xlsx | 3F | F32 + E1 + A1 | 34 |
| 3G.xlsx | 3G | G33 + B1 + E1 | 35 |

共127個不同學號。舊版只取D/E/F/G行政分頁而得到122人，是錯誤解讀。D+F應64人、E+G應63人。這些是實際附件人數，不只是合成示例。

SQLite schema v2：classes增加完整科目代碼、學年、學期、課程代碼及年級，按 course/name/teaching_code 保持唯一；enrollments另存行政班及已確認的授課代碼。相同科目3D在不同學年不互相覆蓋。升級先備份，沿用所有原ID；重新匯入時依原來源檔案把舊行政修讀移回授課班，已有座位不清空。

科目管理改用離線HTML/TSV貼上分析；學年考試設定改為自動名稱，學院和本科課程固定；考場UI以最多人數自動建立連續座號，舊版資料結構仍可讀取。

## 官方模板

兩檔均有 Attendance、Seat Plan，資料從第 18 行開始。

| 區域 | 儲存格 |
|---|---|
| 大學中文 / 英文 | A1 / A2，A:G 合併 |
| 課程中文 / 英文 | A3 / A4，A:G 合併 |
| 學年學期考試標題中英 | A5 / A6，A:G 合併 |
| 科目標籤 / 科名 | A7 / A8，A:G 合併 |
| Intake / 教師 | D10 / E10:G10 |
| 考場 / 日期 | D12 / G12 |
| 考生數 / 時間 | D14 / G14 |
| 簽到說明 | C15:G15（Seat Plan 應清除） |
| 中文 / 英文欄名 | 第 16 / 17 行 |
| 序號 / 座號 / 學號 | A / B / C |
| Attendance 中文 / 英文 | D / E |
| Attendance 簽到 / 簽走時間 | F / G |
| Seat Plan 中文 / 英文 | D:E / F:G 合併 |

Attendance 合併範圍含 A1:G1 至 A8:G8、A9:C9、A11:C11、A13:C13、E9:F9、E10:G10、E11:F11、E13:F13、C15:G15、D16:E16、D17:E17。Seat Plan 使用 D16:G16、D17:G17，並對每條學生行分別合併 D:E 和 F:G。

原 A、B 欄寬 5.625，C 18.625，D 12.625，E 24.625，F 18.625；G 原依預設欄寬。本工具保留既有欄寬並為 G 明確設定 20，避免簽走時間或英文名截斷。原多數行高 16.5、學生行 15；姓名改為要求的 12 pt 後採至少 22 pt，长姓名自動增加。

原使用 Times New Roman、細明體、新細明體，字號 7/8/11/12；本工具保留表頭風格，按需求將學生姓名改為中文標楷體 12、英文 Times New Roman 12，序號、座號及學號 Times New Roman 12。

原打印區域及標題重複行未明確設定，A4 直向、比例 83%、左右邊距約 0.709 英吋、上下約 0.748 英吋。原無手動分頁。本工具設定實際打印區域、重複 1:17 行、單頁寬／不限頁高、保守手動分頁、頁碼；原頁邊距保留。

G2207 Attendance 有 63 人，G2209 有 64 人；COUNTA 分別引用 C18:C81 和 C18:C82，尾端包含空白行。本工具把考生數直接設定為實際記錄數。日期原為 Excel datetime，輸出使用真正日期值及 `yyyy-mm-dd`；時間輸出 HH:MM-HH:MM。

**發現的模板缺陷**：G2209 Seat Plan C80/D80/F80 與 C81/D81/F81 均引用 Attendance 第 81 行。此模板會漏掉第 80 行的學生、重複第 81 行，不能原樣沿用。Seat Plan 也保留了只適用 Attendance 的簽到說明。本工具分開渲染兩種版面，共用同一份確定次序的資料，移除全部公式依賴與簽到說明。原「Abstent」拼字修正為「Absent」。

詳盡合併範圍、欄寬、各行行高、表頭字型、對齊、邊框、日期格式及頁面參數記錄於 `resources/excel-analysis.json`；該報告不含學生姓名或學號。`official_template.xlsx` 僅保留表頭及去值的樣式示範行，無學生資料。

## SQLite 與 GUI

```mermaid
erDiagram
    STUDENTS ||--o{ ENROLLMENTS : identity
    COURSES ||--o{ CLASSES : classes
    CLASSES ||--o{ ENROLLMENTS : membership
    BATCHES ||--o{ EXAMS : exams
    COURSES ||--o{ EXAMS : subject
    EXAMS ||--o{ SESSIONS : dates
    SESSIONS ||--o{ SESSION_CLASSES : participants
    CLASSES ||--o{ SESSION_CLASSES : selected
    SESSIONS ||--o{ ALLOCATIONS : rooms
    ROOMS ||--o{ ALLOCATIONS : venue
    ALLOCATIONS ||--o{ ASSIGNMENTS : seats
    ENROLLMENTS ||--o{ ASSIGNMENTS : membership
    STUDENTS ||--o{ ASSIGNMENTS : identity
    SESSIONS ||--o{ HISTORY : undo
    ALLOCATIONS ||--o{ GENERATION_LOGS : outputs
```

身份及修讀使用 UUID，學號為唯一身份鍵但不是外鍵。座號獨立於 position，鎖定、特殊安排和備註屬於 assignment。重新匯入的移除只停用 enrollment，不刪 assignment；在輸出前顯示待處理錯誤。所有編排 mutation 交易保存 before/after 快照，可跨重啟復原／重做；重新執行其他操作時清除後續 redo 分支。

Qt 主視窗採九頁導航與共用場次選取器；ClassCards 使用 QDrag/QMimeData，RoomCards 接受 Qt drop event；SeatTree 使用 Qt InternalMove 並以 drop 後 order 訊號寫回服務層。容量不足不自動拆分，使用者在勾選對話框確認特定學生。UI 不直接負責座號計算或 Excel 版面。

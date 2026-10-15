# FOF Exam Seating & Attendance Manager v1.0

澳門城市大學金融學院的離線考試座位及簽到表桌面工具。Python 3.12+、PySide6 Qt Widgets、SQLite、openpyxl；獨立專案，不修改或共用現有學生證明系統。運行時不需要網絡、帳號、CDN、API、遠端字型或雲端資料庫。

## 從 GitHub 下載

在本 repository 頁面點 **Code → Download ZIP**，解壓後依以下步驟安裝 Python 原始碼版。

需要 Windows 獨立程式時，到 **Actions → Windows desktop build → Run workflow**，選 `main` 執行。成功後開啟該次執行，在 **Artifacts** 下載 `FOFExamManager-Windows`，解壓完整資料夾，再雙擊 `FOFExamManager.exe`。如果組織停用了 Actions，須由管理員啟用，或在 Windows 執行 [BUILD.md](BUILD.md) 的本地建置步驟。CI 產物仍需 Windows 桌面及 Excel 列印實機驗收。

## 安裝與啟動

Windows 10/11 上安裝 Python 3.12（包含 Python Launcher），在此專案目錄開啟 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

往後可雙擊 `scripts/run_windows.cmd`。初次安裝套件需要網絡；安裝完成後所有業務操作均離線。可在有網絡的相同 OS、架構與 Python 版本上預先執行 `pip download -r requirements.txt -d wheels`，將專案與 wheels 交給離線電腦，再用 `pip install --no-index --find-links wheels -r requirements.txt` 安裝。

Linux/macOS 原始碼開發使用 `python3 -m venv .venv`、`.venv/bin/python -m pip install -r requirements.txt`、`.venv/bin/python run.py`。Windows 獨立程式建置見 [BUILD.md](BUILD.md)。發布時交付整個 `dist/FOFExamManager` 目錄，使用者不需要安裝 Python。

開發環境驗證：Linux、Python 3.12.14、Qt 6.12；自動化結果見 [TESTING.md](TESTING.md)。Windows 原生打包與實機 Excel 列印尚待 Windows 主機驗證，不能將 Linux 打包成果當作 Windows `.exe`。

## 功能與操作流程

1. **學生名單**：單檔、多檔或拖放 `.xlsx` 到視窗。顯示每個 Sheet 的班級與實際人數，預設選取與 `3D/3E/3F/3G` 檔名對應的獨立班級。按「載入所選班級預覽」，核對學號、雙語姓名、班級與科目。可直接修改預覽；有問題列必須手動勾選「已人工核對」。查看差異並確認後才写入 SQLite。
2. **科目管理**：補齊中英文科名、雙語課程名稱、教師名單、學制、備註；可手動新增、編輯、刪除未使用科目、Excel 批量匯入。場次教師可覆寫科目預設。匯入名單提供中文科名及課程，但不猜測未提供的英文名稱。
3. **考場管理**：建立 G2207、G2209 等考場，自訂容量。可用座號留空時為連續 `001` 起編號；例如 `001,003,008` 表示只有這三座可用，容量和座位數分開計算。考場可停用。
4. **考試批次**：建立學年、學期、考試類型、學院／課程及備註。建立場次時選批次、科目、班級、考場，設定日期、起止時間、教師和 Intake。同一批次科目共享 Exam，可有多個 Session。複製設定會建立次日草稿，不複製座位，請核對日期。
5. **考場編排**：把班級卡片拖到考場卡片，或選取班級與考場後雙擊班級。人數、容量使用率與待分配清單即時更新。容量不足可選「拆分班級」或取消；拆分對話框可自訂人數及逐一勾選學生。剩餘學生保持待分配。可新增考場、調整參加班級、復原、重做及驗證完成。
6. **座位調整**：上下拖放學生、移至首位、指定名單序號、Ctrl 選兩人交換。預設座號跟隨次序重編。指定座號可鎖定，鎖定者的實際座號保持不變；其餘学生跳過該號。特殊安排及備註僅內部顯示。解除鎖定後可移回待分配或調至其他考場。搜尋期間停用拖放；清除搜尋可再排序。
7. **文件生成中心**：按科目、日期、考場篩選；勾選項目或全選；生成前要求所有場次學生已分配、無衝突、表頭完整。選擇輸出資料夾，逐份產生文件并顯示結果。已有同名檔案逐份提示覆蓋／另存／跳過。可打開文件及輸出資料夾。
8. **Dashboard**：學生、科目、批次、場次、分配和完成數直接從 SQLite 計算。雙擊場次繼續編排。
9. **設定與資料備份**：查看資料庫路徑、匯入與生成記錄，執行備份和還原。

所有編排操作自動保存，復原／重做歷史也保存於資料庫。「保存草稿」確認目前已保存狀態。關閉程式後可繼續。

## 真實附件分析

| 檔案 | 可用 Sheet／人數 | 預設選取 | 與示例人數差異 |
|---|---|---|---|
| 3D.xlsx | 匯總 30、A 1、D 29 | D 29 | 30 → 29 |
| 3E.xlsx | 匯總 28、E 28 | E 28 | 相同 |
| 3F.xlsx | 匯總 34、A 1、E 1、F 32 | F 32 | 34 → 32 |
| 3G.xlsx | 匯總 35、B 1、E 1、G 33 | G 33 | 35 → 33 |

四個獨立班級共 **122 人**，同班或跨這四班未發現重複學號。按照 D+F、E+G 分配，兩考場均為 **61 人**。127 人是驗收用合成示例，不會代替真實名單。其他班級與匯總 Sheet 都會顯示，可由使用者明確選取。

原 G2209 Seat Plan 第 80、81 列重複引用 Attendance 第 81 列，會漏掉一名並重複另一名。本工具以資料模型直接渲染，沒有此公式問題。詳見 [ANALYSIS.md](ANALYSIS.md) 與 `resources/excel-analysis.json`。

## Excel 匯入要求

只接受 `.xlsx`。辨識「帳號／學號／Student ID」「姓名／中文姓名」「英文姓名」「班級」，支援原附件位於第 8 或第 9 行的表頭。科目資料可來自表頭前的科目名稱、教務科目代碼、授課老師、課程，也可使用資料欄的科目代碼／名稱。缺少科目代碼或班級可在預覽補齊。

姓名支援分欄、中英同格、多行；可靠的中文／英文分界才分開，含空格、連字號、撇號的英文保留。曖昧格式保留原文並要求人工核對。學號保留文字，數值搭配全零格式會保留前導零；超過 Excel 精度或非整數學號要求人工確認。原始姓名保存於資料庫。

不得同时選同班匯總與獨立 Sheet；同科目同學生重複、跨班身份衝突會阻止匯入。學生身份依學號識別但使用 UUID 關聯，同姓名不同學號不合併，同學號可修讀不同科目。

重新匯入顯示新增／移除／姓名更改／無變化。預設保留舊修讀關係；勾選「差異合併」才停用已移除記錄。已有座位不會刪除，會阻止生成直到使用者在座位頁移除該記錄。未變動者的座位與排序保持。手動「停用修讀記錄」只影響此科此班，其他科目不受影響。

科目批量匯入的第一行使用 `code,name_cn,name_en,teachers,programme,programme_en,language,notes`，亦接受對應中文欄名。公式不執行、不匯入為學號；巨集檔拒絕，外部連結不載入執行。

## Excel 輸出規則

採用已去除學生資料的官方雙工作表模板。Attendance 名字分 D 中文、E 英文；Seat Plan 分 D:E 中文、F:G 英文，沿用原合併布局。中英文大学與課程、學年學期、考試類型、科目、Intake、教師、日期、時間、考場和考生數均同步更新。

每人一列，動態生成，不留固定 80 行或舊座號。中文姓名「標楷體」12 pt，英文、學號、數字 Times New Roman 12 pt；目標電腦須有相應字型，否則 Excel 會替代顯示。保留官方表頭合併、欄寬、邊框、A4 直向和頁邊距；依長姓名調整行高，按頁重複 1:17 行表頭、更新打印區域并插入保守分頁。Attendance 保留出缺席及監考簽名區；Seat Plan 不含簽到、簽走或簽到說明。

兩張表直接写值，不依賴 Excel 重新計算，離線或 `data_only` 開啟均有完整學生資料。內部特殊安排與備註永不輸出。表頭啟用無密碼工作表保護，學生與簽到區仍可編輯；需要直接修改表頭可在 Excel「校閱 → 取消保護工作表」，無須密碼。

檔名：`BAE305_公司金融_2026-10-14_1900_G2209.xlsx`。先写同目錄临時檔，重新讀取驗證兩張表的人數、學號、姓名及座號，成功才原子發布；驗證失敗不取代已有檔案。文字值以 Excel 字串保存，即使姓名以 `=` 開頭亦不成公式。

同場次學生只能有一座；同時段考場禁止重用，除非雙方場次皆明確啟用合場。合場共用容量及座號池，以所有重疊場次保守預留，不容許重複座號。同時段同學生的第二次分配會被拒絕。

## 本地資料、備份與還原

Windows 預設 `%LOCALAPPDATA%\FOFExamManager\fof_exam.sqlite3`；Linux 預設 `~/.local/share/FOFExamManager/fof_exam.sqlite3`。可用 `python run.py --data-dir <資料目錄>` 指定另一目錄。不得使用共用網絡磁碟作為即時 SQLite 資料目錄。

使用 UUID、外鍵、唯一約束、交易、WAL、完整性檢查。學生、科目、班級、修讀、批次、Exam、Session、考場、分配、座位、特殊安排、匯入和生成記錄獨立保存。學生資料只在本地 SQLite 和使用者要求的 Excel 中，不寫入一般運行日誌。

「備份」使用 SQLite backup API，含已提交的 WAL 資料；目標存在則拒絕覆蓋。「還原」先檢查 schema 版本、SQLite 完整性及外鍵，再自動保存現有資料庫為 `before_restore_<時間>_<唯一字尾>.sqlite3`，最後還原選取備份。還原不會自動復原已輸出的外部 Excel。需要回到舊資料，選取自動安全備份再還原。

資料庫保存的是本地個人資料，系統不宣稱加密；請使用機構既有的電腦及檔案存取權限。原始六份含學生資料的附件與測試資料庫沒有納入原始碼發布包。

## 開發與驗證

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

將六份附件放在私人資料夾，設定 `FOF_REFERENCE_DIR` 再執行，可一併跑真實附件測試。沒有附件時該項明確 skipped，其餘測試使用合成學生。參見 [TESTING.md](TESTING.md)、[BUILD.md](BUILD.md)、[CHANGELOG.md](CHANGELOG.md)。

專案模組：`app/importers` 辨識 Excel、`app/database` SQLite、`app/models` 資料記錄、`app/services` 業務規則與復原、`app/ui` Qt 介面、`app/templates` 官方版面、`app/exporters` 驗證與安全發布。`main.py` 只啟動應用程式。

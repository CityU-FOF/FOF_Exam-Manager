# 原始碼 ZIP

PDF原頁面填寫研究：[下載測試樣本 ZIP](FOF_PDF_Form_Proof.zip) · [逐份PDF及預覽](pdf-form-proof/README.md)。這是獨立可行性樣本，尚未改變v1.6.2正式輸出流程，不需重新安裝程式。

## v1.6.2（目前版本）

- 檔案：[FOF_Exam_Manager_v1.6.2.zip](FOF_Exam_Manager_v1.6.2.zip)
- 原始碼版本：`551d898f14353d7822a1544d47b6092dc6325700`
- SHA-256：`75bda3ef6f1249fd18dbece50bb0993105f67bb158d20bc79d313e96079d1adc`

修正Python 3.15令Pillow安裝失敗的問題。請先安裝標準64位元[Python 3.12.10](https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe)（可保留3.15），關閉舊程式，完整解壓新版至新資料夾，再執行「首次安裝.bat」及「啟動程式.bat」。

安裝器只選標準64位元CPython 3.12–3.14，優先3.12；不相容的舊venv會保留後重建，原有學生資料與考場編排保留。只下載預編譯wheel，毋須安裝C++ Build Tools。若找不到相容Python，會在更動環境前停止。

169項測試通過、2項私人附件測試略過；已驗證Windows x64 Pillow wheel可下載，並通過此ZIP解壓後的套件檢查及文件生成自檢。Windows批次遷移仍待實機確認。

## v1.6.1（保留舊版）

- 檔案：[FOF_Exam_Manager_v1.6.1.zip](FOF_Exam_Manager_v1.6.1.zip)
- 原始碼版本：`e1ab70cb82972bb224fb5ca933acfddcc063d53e`
- SHA-256：`f78bdc801967045fe5f8aa2a0342cf8b616e66319f0d218f4c3a2cdf19fe4b57`

修正舊環境缺少 Pillow 時生成官方表格失敗，以及生成前「打開輸出資料夾」沒有反應。啟動時核對套件並測試圖像嵌入；缺少或不完整時自動安裝修復，沿用原有本機資料。

請先關閉舊程式，完整解壓新版至新資料夾，執行「首次安裝.bat」，看到 Setup completed 後執行「啟動程式.bat」。附件一、三由系統自動生成，不需要已審批PDF。預設輸出資料夾在本機資料目錄下的「輸出文件」，生成時亦可另選位置。

155項測試通過、2項私人附件測試略過；此ZIP已完整解壓，通過套件／模板檢查及三份考務附件生成自檢。Windows自動修復與Microsoft Excel實際列印仍待實機確認。

## v1.6.0（保留舊版）

- 檔案：[FOF_Exam_Manager_v1.6.0.zip](FOF_Exam_Manager_v1.6.0.zip)
- 原始碼版本：`648b76a5e6c4cc69830bb022271792da9b191743`
- SHA-256：`90771de4b8e3e19e170c11e7248a369a47278c229b7847841107e0891cf4cc00`

新增試卷評審記錄、試題封面、試卷袋封面及跨科印刷統計；已審批 PDF 保留原檔及 QR Code。每班一份後備，按中／英文卷分別計算；每令 500 張、每箱 5 令。

更新時請完整解壓至新資料夾，重新執行「首次安裝.bat」以安裝新增的 Pillow 套件，再執行「啟動程式.bat」。沿用原有本機資料目錄，資料庫升級前會自動備份。

已通過 146 項測試（2 項私人附件測試略過），並通過解壓 ZIP 後的程式自我檢查。官方 Excel 表格使用原表背景及可修改文字框；請在 Windows Microsoft Excel 試印一張，核對字體及列印位置。

## v1.5.0（保留舊版）

- 檔案：[FOF_Exam_Manager_v1.5.0.zip](FOF_Exam_Manager_v1.5.0.zip)
- 原始碼版本：`870eb21d7ccc869a915c2fa3f5ed9815cdabff67`
- SHA-256：`02bf1afbcfa2bf26fb96bbfea632c819e777488d597dee51fb72bcacf1634331`

此為重新打包的完整 Python 原始碼版，內含「首次安裝.bat」、「啟動程式.bat」及所需程式／模板。完整解壓後執行批次檔；資料庫仍使用原本的本機資料目錄。ZIP 不包含學生資料、私有附件、虛擬環境或 Git 歷史。

若 GitHub archive 連結顯示 404，請先以有此儲存庫存取權的 GitHub 帳戶登入，開啟上述 ZIP 的檔案頁，使用 GitHub 的 Download raw／下載原始檔按鈕。這是直接儲存的 ZIP，並非 Actions artifact，不依賴 artifact 保存期限。

儲存庫設為Public時可直接下載；設為Private時需要有讀取權的GitHub帳戶。重新上載ZIP不會更改儲存庫的存取權。

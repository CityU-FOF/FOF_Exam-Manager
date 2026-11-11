# 原始碼 ZIP

## v1.6.0（目前版本）

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

發布端可透過 Git 存取儲存庫，但目前未登入的網頁 archive／codeload 請求回傳 404；重新上載檔案不會更改儲存庫的存取權。若登入後仍為 404，須確認帳戶對 `CityU-FOF/FOF_Exam-Manager` 的讀取權。

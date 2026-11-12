# 原始碼 ZIP

PDF原頁面填寫研究：[下載測試樣本 ZIP](FOF_PDF_Form_Proof.zip) · [逐份PDF及預覽](pdf-form-proof/README.md)。這是最初研究樣本；附件一／三已在v1.7.0正式整合，附件二XFA仍未整合。最新[正式生成示例](v1.7.2-samples/README.md)已套用Calvan、BAECF及考場班級人數。

## v1.7.2（目前版本）

- 檔案：[FOF_Exam_Manager_v1.7.2.zip](FOF_Exam_Manager_v1.7.2.zip)
- 原始碼版本：`ad62f2f14a9d7366f0f750e4025200a5c779e74d`
- SHA-256：`1de265b936b91aedf046ff7748ff5fdf55169c2941353836870868ab3e50389f`
- [附件一PDF及預覽](v1.7.2-samples/README.md)

附件一中英文科目名稱改為同一行並排，英文放在中文右方；長名稱只縮小字型，不換行。附件三沿用已確認的v1.7.1版面與應考／備用份數。

關閉舊程式，完整解壓新版，執行「啟動程式.bat」後重新生成附件一即可。本次沒有新增依賴或資料庫變更，原有資料沿用。37項相關測試及ZIP解壓後生成自檢通過，已實際渲染核對同一行版面。

## v1.7.1（保留舊版）

- 檔案：[FOF_Exam_Manager_v1.7.1.zip](FOF_Exam_Manager_v1.7.1.zip)
- 原始碼版本：`5d410869bbe1d814bba92f4b3daf02a3a221ae62`
- SHA-256：`6c20266770515b1d292744aa8641940718044923752d8c5f148b934cc8d10e17`
- [最新PDF示例及預覽](v1.7.1-samples/README.md)

附件一新增英文科目名稱，置於中文名下方。附件三班級明細移至應考總數右邊；印刷欄顯示每班應考+備用及總份數，例如32+1 (3F)、34+1 (3G)，=68。

同班拆考場仍全班合共1份後備，放在該班按考場名稱排列的首個有學生考場；其他考場顯示+0。移動學生後重新生成會更新。附件二新PDF／XFA流程本次未整合。

關閉舊程式，完整解壓新版，執行「首次安裝.bat」及「啟動程式.bat」，原有資料沿用。178項測試通過、2項私人附件測試略過；解壓ZIP後套件檢查及文件生成自檢通過。列印選「實際大小／100%」。

## v1.7.0（保留舊版）

- 檔案：[FOF_Exam_Manager_v1.7.0.zip](FOF_Exam_Manager_v1.7.0.zip)
- 原始碼版本：`917c1f73cbc6510362ee10c97c986bc01974b0db`
- SHA-256：`6260ba26da1cc8239fe8e409432e07cfac14d2097bb2462c6039eabde2b5627a`
- [實際PDF示例及預覽](v1.7.0-samples/README.md)

附件一／三改為原PDF直接填字。附件一固定送審人Calvan、課程BAECF，送審日期為生成當日（UTC+8）。附件三每個有學生的考場各出一份一頁PDF，列出該考場授課班及實際人數，例如G2108的32 (3B)、30 (3C)，應考62；同班拆場亦按各房實際分配計數，不加入後備份數。

關閉舊程式，完整解壓至新資料夾，執行「首次安裝.bat」安裝新增的純Python pypdf套件，看到Setup completed後執行「啟動程式.bat」。沿用標準64位元Python 3.12–3.14及原有本機資料，無需重新匯入學生。

附件二本次未整合新的PDF／XFA流程。PDF列印選「實際大小／100%」，資料改動後重新生成。177項測試通過、2項私人附件測試略過；解壓ZIP後套件／資源檢查、生成自檢及Linux打包自檢通過，Windows實際列印仍待實機確認。

## v1.6.2（保留舊版）

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

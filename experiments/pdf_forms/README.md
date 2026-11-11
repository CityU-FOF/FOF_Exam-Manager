# 原 PDF 填寫可行性研究（2026-11-11）

這是最初的獨立驗證樣本，查看樣本不需重新安裝。附件一／三於v1.7.0正式整合，並依確認改為Calvan、BAECF及每考場班級人數。此資料夾保留原研究樣本；附件二XFA仍未整合。

## 已確認的文件結構

| 文件 | 實際結構 | 可行方式 |
| --- | --- | --- |
| 附件一：試卷評審記錄 | 未加密、單頁 A4、沒有表單欄位 | 保留原 PDF，按一次設定的座標疊加文字 |
| 附件三：試卷袋封面 | 未加密、單頁 A4、沒有表單欄位 | 同上，每考場填一頁，可重複列印 |
| 附件二：試題封面 | 未加密、XFA 與 AcroForm 並存，20 個葉欄位 | 同步填原 AcroForm 與 XFA 資料；另生成普通 PDF 列印副本 |

附件二的20個欄位包括16個文字／選擇欄、2個勾選框、2個唯讀的開／閉卷文字標籤。`日期[0]`是日期，`日期[1]`實際是時間，程式已分別處理。

原表沒有獨立的「授課班」或「期中／期末」欄位。正式整合時若要加入，可在原PDF另加文字層，但需要先確認位置；本次原欄位樣本未擅自增添或移動這些內容。

XFA不是密碼鎖。原檔另有Adobe Reader延伸權限（`/UR3`）簽章；是否能保留Reader的延伸功能，需要Adobe桌面版實機驗證，不能單憑寫入成功下結論。

## GitHub 工具查證

- [py-pdf/pypdf](https://github.com/py-pdf/pypdf)：純Python、BSD授權；本次採用7.0.1，負責保留原頁面、合併文字層、讀寫欄位與增量存檔。[欄位文件](https://github.com/py-pdf/pypdf/blob/main/docs/user/forms.md)明確說明XFA可能覆蓋一般頁面內容；只填AcroForm並不足夠。[合併頁面文件](https://github.com/py-pdf/pypdf/blob/main/docs/user/add-watermark.md)說明`merge_page`。
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF)：可處理文字、表單及頁面，採AGPL／商業授權。本樣本未加入此依賴。
- 文字層由現有PySide6的QPdfWriter生成，中文採用系統可用字型並嵌入PDF。原有表格、標誌、線條及文字直接保留，沒有經Excel、圖片背景或整頁重新排版。

## 驗證結果及限制

- 附件一／三保留原頁面 `[0,0,595.32,841.92]` points。
- 使用同一Poppler渲染器以110dpi對比原檔，填寫方框外的變動像素為0（方框周圍保留3px抗鋸齒容差）。這證明本次樣本沒有整頁比例或位置改動，不等同已驗證所有印表機設定。
- 原欄位XFA樣本以增量方式存檔：原檔537,218 bytes完整保留為新檔前綴，原XFA版面、設定及UR3簽章內容位元組保持一致。同步設定文字值、勾選狀態及中文欄位外觀；Poppler已確認顯示填入的值。
- **保留簽章位元組不代表簽章或延伸權限已驗證有效。** Adobe Reader可能另有檢查；原欄位樣本需使用Windows Adobe Acrobat Reader檢查顯示、儲存、重開及列印。
- 普通PDF列印副本把各欄位外觀固定到原頁面，沒有XFA或互動欄位，不宣稱保留原Reader延伸權限。已以Poppler及Qt PDFium檢查顯示；其用途是一般PDF閱讀器列印。
- 全部樣本使用示例教師及示例資料，不含學生名單。此次只處理提供的空白官方模板，**不處理已審批／已有QR Code的正式封面**，後者沿用原檔不變。

「上傳PDF」不等於自動知道每個空白位置。附件一／三沒有真正欄位，首次仍需建立版型與座標對應；更換成另一版表格時亦需重新對應。本程式只驗證用戶提供的三份官方版本，不是任意PDF自動辨識器。

## 樣本

下載：[FOF_PDF_Form_Proof.zip](../../downloads/FOF_PDF_Form_Proof.zip)。也可在[樣本頁](../../downloads/pdf-form-proof/README.md)直接查看PDF及預覽。

1. `annex1-review-sample.pdf`：直接填入原評審表。
2. `annex3-bag-sample.pdf`：直接填入原試卷袋封面。
3. `annex2-xfa-sample.pdf`：保留XFA、原欄位及增量寫入，待Adobe桌面版確認。
4. `annex2-print-copy.pdf`：普通PDF列印副本，非互動表單。

先確認樣本版面與列印結果，再決定正式系統輸出方式。若採用Excel模板備案，則應讀取使用者準備好的xlsx模板，只填指定儲存格，不從PDF重建欄寬、字型或間距。

## 重現方法（開發用途）

使用標準64位元Python 3.12–3.14，在儲存庫根目錄執行：

```powershell
python -m pip install -r experiments/pdf_forms/requirements.txt
python experiments/pdf_forms/prototype.py --templates-dir "C:\ExamTemplates" --output-dir "C:\ExamPdfProof"
```

模板資料夾需放入原先提供的`Annex 1-...pdf`、`Annex 2-...pdf`、`Annex 3-...pdf`。程式只讀原檔，使用固定示例資料產出測試副本；不要以已審批封面作為研究模板。

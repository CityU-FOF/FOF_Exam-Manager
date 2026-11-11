# 官方空白表格底稿

自v1.7.0起，附件一／三改用使用者提供的原PDF直接填字：

- `review.pdf`：Annex 1－試卷評審記錄原檔，固定送審人Calvan、課程BAECF，送審日期取生成當日。
- `bag.pdf`：Annex 3－試卷袋封面原檔，每考場一份PDF，列出該考場授課班及實際人數。

兩份原檔均為未加密、無表單欄位、單頁595.32×841.92pt。`app/exporters/paper_pdf.py`只疊加文字，保留原有向量表格、標誌及頁面尺寸。正式已審批封面不作此處理。

下列PNG保留作附件二原有Excel輸出及歷史研究樣本；本次沒有整合附件二的XFA研究流程。

三張 PNG 由使用者提供的官方空白 PDF 第一頁，以 `pdftoppm -r 250 -png -singlefile` 直接渲染，未改動原有校徽、表格、文字或填塗格位置：

- `review.png`：Annex 1－試卷評審記錄。
- `cover.png`：Annex 2－試題封面；來源為 Adobe XFA 動態表單，僅保留可列印的空白版面，不攜帶 JavaScript 或示例表單值。
- `bag.png`：Annex 3－試卷袋封面。

`app/exporters/paper_forms.py` 以 A4 595.32 × 841.92 pt 定位底稿與填字；拉丁填字使用 Times New Roman，中文使用新細明體，試題封面使用標楷體。印刷／審核及簽署等現場資料預設留白。

這些是官方空白表格，不含學生資料或真實試題。真正已審批的 PDF 由使用者在程式內匯入本機資料庫，不存放於此目錄。

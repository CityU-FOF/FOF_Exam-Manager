# 官方空白表格底稿

三張 PNG 由使用者提供的官方空白 PDF 第一頁，以 `pdftoppm -r 250 -png -singlefile` 直接渲染，未改動原有校徽、表格、文字或填塗格位置：

- `review.png`：Annex 1－試卷評審記錄。
- `cover.png`：Annex 2－試題封面；來源為 Adobe XFA 動態表單，僅保留可列印的空白版面，不攜帶 JavaScript 或示例表單值。
- `bag.png`：Annex 3－試卷袋封面。

`app/exporters/paper_forms.py` 以 A4 595.32 × 841.92 pt 定位底稿與填字；拉丁填字使用 Times New Roman，中文使用新細明體，試題封面使用標楷體。印刷／審核及簽署等現場資料預設留白。

這些是官方空白表格，不含學生資料或真實試題。真正已審批的 PDF 由使用者在程式內匯入本機資料庫，不存放於此目錄。

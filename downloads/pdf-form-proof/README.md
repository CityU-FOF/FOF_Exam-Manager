# PDF 直接填寫測試樣本

這不是新程式版本，不需要安裝。請先查看附件一、三的版面，列印時選「實際大小／100%」，確認後再整合正式系統。

- [附件一：試卷評審記錄 PDF](annex1-review-sample.pdf) · [預覽](annex1-review-sample.png)
- [附件三：試卷袋封面 PDF](annex3-bag-sample.pdf) · [預覽](annex3-bag-sample.png)
- [附件二：原XFA欄位填寫 PDF](annex2-xfa-sample.pdf) · [目前渲染預覽](annex2-xfa-sample.png)
- [附件二：普通PDF列印副本](annex2-print-copy.pdf) · [預覽](annex2-print-copy.png)
- [整包下載](../FOF_PDF_Form_Proof.zip)
- [技術查證及重現程式](../../experiments/pdf_forms/README.md)
- [驗證數據](verification.json)

附件一、三直接保留原PDF並加入文字。附件二的XFA原欄位版仍需Windows Adobe Acrobat Reader確認，不以瀏覽器或預覽圖代替此項測試。它採增量寫入保留原始簽署區，但未驗證Adobe的延伸權限是否仍被接受。

附件二的普通PDF副本已固定欄位顯示，不依賴XFA，可用作列印測試。它不是可編輯XFA表單，也不宣稱保留Reader延伸權限。

原有已審批封面及QR Code流程保持原樣；本研究只用空白模板與示例資料。

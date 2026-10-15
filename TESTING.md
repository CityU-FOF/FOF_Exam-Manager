# Phase 6：測試與驗收

## 執行

```bash
FOF_REFERENCE_DIR=/path/to/private/references QT_QPA_PLATFORM=offscreen python -m pytest -q --junitxml=test-results.xml
```

Windows PowerShell：

```powershell
$env:FOF_REFERENCE_DIR='C:\private\references'
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m pytest -q --junitxml=test-results.xml
```

`FOF_REFERENCE_DIR` 目錄可含子目錄，需包含四份名單。此次環境使用使用者上传的六份原始附件，真實名單測試已執行；附件不包进原始碼。未設定該變數時，一項真實附件測試為 skipped，不代表通過。

## 自動化涵蓋

| 驗收要求 | 實際檢查 |
|---|---|
| 1 四班分配 | 合成 D30/E28/F34/G35，G2209=64、G2207=63、合計127，兩份雙 Sheet逐列核對 |
| 2 真實 Excel | 使用實際3D/E/F/G，29/28/32/33，122身份，兩考場61/61，再匯入不重複 |
| 3 容量不足 | 70+25/80 拒絕整班；確認選10後剩15；UI可手動選最後10而非自動前10 |
| 4 調整座位 | 第5位至第2位、001–005重編、重新連線讀回、跨重啟復原／重做 |
| 5 增減學生 | 64→65→63，三次輸出，無殘留學號／座號；1/30/63/64/65/80/120人動態行 |
| 6 拆班跨考場 | 35分20+15，身份不重複、原班級不變，再移一人19+16並復原 |
| 7 批量生成 | 10份真實生成xlsx，每份兩Sheet；失敗不中斷其他項目，同名覆蓋／另存／跳過 |
| 8 再匯入差異 | 新增1、移除1、改名1、不變3；已有座位和UUID保留，移除需人工處理 |
| 9 資料保護 | 將Python socket禁止後生成成功；內部備註無輸出、以=開頭姓名仍為文字 |

另驗證：合場容量與共享座號、考場／學生時段衝突、連接時段不衝突、指定可用座位、座位鎖定、DB安全備份／還原、無效備份拒絕、匯入交易回滾、輸出驗證失敗保留舊檔及清除暫存、表頭修改同步兩表、空白必要表頭拒絕、複製Exam設定無座位、復原不得奪取他場座位。

Qt 測試啟動真實 MainWindow、巡覽九頁、向 RoomCards 投遞 Qt QDropEvent 並驗證服務與畫面更新、名單預覽確認、搜尋、座位控制、持久化排序訊號及本地資料夾 URL。座位拖放由 Qt InternalMove 實作；雲端 Qt 測試驗證其 order 訊號的儲存路徑，沒有宣稱已用 Windows 實體滑鼠完成拖動。

本次結果摘要見 `test-results.xml` 與 CHANGELOG。Qt 測試為 Linux offscreen；以下實機場景仍須 Windows 人工驗收。

最終實測：**49 passed，0 failed，0 skipped**。包含真實附件測試。Linux打包程式 `--self-test` 返回0，selfcheck.json記錄passed、ui_pages=9、students=3、雙Sheet生成成功。原始碼套件內 `resources/package-selfcheck.json` 保留該匿名驗證摘要。

## 可操作 UI 場景

1. 用新資料目錄啟動：`python run.py --data-dir <空資料夾>`。Dashboard應全0。
2. 拖入四份真實名單，預覽預設D29/E28/F32/G33，確認；搜尋任意學號，確認班級與來源。取消預覽不應写資料。
3. 把科目英文補為Corporate Finance、課程英文補為Bachelor of Applied Economics Programme (Chinese)。新增兩個80容量考場和2026–2027第一學期期中批次。建立BAE305場次、勾四班兩考場。
4. 真實拖動D與F卡片到G2209、E與G到G2207：應61/61、待分配0。單次復原，再重做，應恢復。
5. 另建小容量考場或合成70+25，拖入超量班，先取消應完全不变，再拆分、手動勾選特定學生；未分配者仍顯示。
6. 雙擊G2209進座位頁，拖動第5名到第2位，序號立即改變；锁定一人的座號再排序其他人，該座不被佔用。清除搜尋才能拖放。移首位、指定序號、Ctrl兩人交換、移考場、復原／重做逐一檢查。
7. 關閉程式、重新開啟相同資料目錄，場次、名單、次序、鎖定與復原記錄保持。
8. 選兩個考場生成，Excel兩Sheet逐列核對。再次生成測試覆蓋、另存、跳過；以Excel佔用檔案時應報失敗、不破壞原檔。
9. 更新名單再匯入，查看差異，停用已移除者；原座位保留並拒绝輸出，人工移除後重新生成。
10. 備份到新檔，添加一人，再還原；應恢复原數且產生before_restore安全備份。重用現有備份路徑應拒絕覆蓋。
11. 斷網執行完整流程；Microsoft Excel打印預覽檢查不同人數、長姓名及高DPI。使用「打開文件／資料夾」確認Windows檔案關聯。

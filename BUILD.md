# Windows 打包與發布

## 狀態

此環境為 Linux。PyInstaller 的 Linux 建置可驗證依賴收集與資源路徑，但**不能交付或驗證 Windows `.exe`**。Windows 打包需在 Windows 10/11 的原生 Python 3.12 x64 環境執行。此專案附可執行腳本與可手動啟動的 Windows CI 工作流程，沒有在本次工作中推送或執行遠端 CI。

## 一鍵建置

在 Windows 的專案目錄 PowerShell：

```powershell
.\scripts\build_windows.ps1
```

腳本建立 venv、安裝 requirements-dev、執行 pytest，成功才跑 PyInstaller；保留每個步驟失敗狀態，失敗就停止。如果機構政策不允許執行腳本，使用以下手動命令。

## 手動建置

```powershell
$fofVenv = Join-Path $env:LOCALAPPDATA 'FOFExamManager\venv'
py -3.12 scripts/prepare_environment.py "$fofVenv"
$fofPython = Join-Path $fofVenv 'Scripts\python.exe'
& $fofPython -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = 'offscreen'
& $fofPython -m pytest -q
Remove-Item Env:QT_QPA_PLATFORM
& $fofPython -m PyInstaller --noconfirm --clean FOFExamManager.spec
```

測試或安裝失敗時不要繼續打包。希望測試真實附件時先將六個 Excel 放在私人目錄，設定 `$env:FOF_REFERENCE_DIR='C:\private\reference'`。一般 CI 不包含學生附件，所以該項測試會明確 skipped。

Python 套件使用 AppData 內的短路徑，避免 GitHub 長資料夾名稱與 PySide6 內部檔名相加超出 Windows 路徑限制。批次安裝、啟動、PowerShell 建置及 CI 使用同一環境；CI 亦包含帶空格長路徑內重複安裝及匿名啟動自檢。這些原生 Windows 檢查須在 Windows 執行，不能視為已在 Linux 通過。

產物 `dist\FOFExamManager\FOFExamManager.exe`。請複製／壓縮**整個** `FOFExamManager` 目錄，不可只交付 exe。spec 使用 onedir、不啟用 UPX，包含清理後的官方模板；排除 QtWebEngine、QtNetwork 等無關網絡／瀏覽器模組。字型使用本機字型，不從網絡取得。SQLite 資料保存在使用者 LOCALAPPDATA，不放在程式安裝目錄。

## 發布前 Windows 驗證

1. 在沒有 Python 的 Windows 10 和 Windows 11 機器解壓並啟動 exe。
2. 斷開網絡，按 TESTING.md 的 UI 場景匯入、拖放、排序、保存、重啟、備份還原和生成。
3. 用 Microsoft Excel 開啟兩張 Sheet，確認文字、三位座號、12 pt 字型、雙語表頭、姓名邊框與打印預覽；核對 30/64/80 人的分頁，並測試長姓名。
4. 打開輸出資料夾／檔案，檢查 Windows 檔案總管和 Excel 能正常開啟。
5. 測試檔案被 Excel 佔用、資料夾唯讀、同名檔案、非管理員帳號和高 DPI（125%/150%/200%）。生成失敗應保留原文件並提供可理解的訊息。

以上 Windows 原生行為、Microsoft Excel 視覺列印及 OS 檔案總管開啟尚未在此 Linux 雲端環境執行。

## 可選 Windows CI

`.github/workflows/build-windows.yml` 提供 `workflow_dispatch`。將此**獨立專案**放到使用者選定的 GitHub repository 後手動執行工作流程，可下載 Windows artifact。此流程只建置合成測試，不會把真實學生附件上傳。CI 建置成功仍需以上 Windows 桌面人工驗收。

## Linux 開發打包

```bash
.venv/bin/python -m PyInstaller --noconfirm --clean FOFExamManager.spec
./dist/FOFExamManager/FOFExamManager --data-dir ./local-data
```

產物是 Linux ELF，不能在 Windows 運行。無圖形顯示的驗證環境可設定 `QT_QPA_PLATFORM=offscreen`；這只用於測試，不適用於一般桌面使用者。

## 打包產物自檢

程式提供開發用途的 `--self-test <新輸出目錄>`：使用隔離的临時資料庫及三名合成學生，執行匯入、分配、座位排序、兩Sheet生成驗證及九頁GUI啟動，產生 `selfcheck.json`。不讀寫一般使用者資料庫，也不需要真實學生附件。相同報告已存在會拒绝重用目錄。

Linux：`QT_QPA_PLATFORM=offscreen ./dist/FOFExamManager/FOFExamManager --self-test ./package-check`。

Windows PowerShell：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$p = Start-Process '.\dist\FOFExamManager\FOFExamManager.exe' -ArgumentList '--self-test', 'C:\temp\fof-package-check' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Packaged application check failed.' }
Remove-Item Env:QT_QPA_PLATFORM
Get-Content 'C:\temp\fof-package-check\selfcheck.json'
```

這項自檢不能替代Windows實體拖放、字型、Excel打印及檔案總管人工驗收。

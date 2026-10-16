$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if ($env:OS -ne 'Windows_NT') { throw 'Windows executable must be built on Windows 10/11.' }
& (Join-Path $PSScriptRoot 'install_windows.cmd') --no-pause
if ($LASTEXITCODE -ne 0) { throw 'First-time setup failed.' }
$fofEnvironment = if ($env:FOF_VENV_DIR) { [IO.Path]::GetFullPath($env:FOF_VENV_DIR) } else { Join-Path $env:LOCALAPPDATA 'FOFExamManager\venv' }
$fofPython = Join-Path $fofEnvironment 'Scripts\python.exe'
& $fofPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $fofPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $fofPython -m PyInstaller --noconfirm --clean FOFExamManager.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
Write-Host 'Built: dist\FOFExamManager\FOFExamManager.exe. Distribute the entire FOFExamManager folder.'

@echo off
rem Called within the install/launch script's setlocal scope.
rem Keep Qt's deeply nested files outside long GitHub ZIP checkout paths.
if defined FOF_VENV_DIR goto resolve_path
if not defined LOCALAPPDATA (
  echo LOCALAPPDATA is unavailable. Set FOF_VENV_DIR to a short writable path.
  exit /b 1
)
set "FOF_VENV_DIR=%LOCALAPPDATA%\FOFExamManager\venv"
:resolve_path
for %%I in ("%FOF_VENV_DIR%") do set "FOF_VENV_DIR=%%~fI"
set "FOF_PYTHON=%FOF_VENV_DIR%\Scripts\python.exe"
exit /b 0

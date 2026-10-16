@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0\.."
if /i "%~1"=="--no-pause" set "FOF_NO_PAUSE=1"
title FOF Exam Manager - First-time setup
echo FOF Exam Seating and Attendance Manager
echo First-time setup requires Internet access. Daily use is offline.
echo.
if exist ".venv\Scripts\python.exe" goto validate_environment

echo [1/3] Looking for 64-bit Python 3.12 or newer...
py -3.12 -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py312
python -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if "%errorlevel%"=="0" goto create_with_python
py -3 -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py3
echo Python was not found, is older than 3.12, or is not 64-bit.
echo Please install 64-bit Python 3.12 or newer from https://www.python.org/downloads/windows/
echo During installation, select Add Python to PATH, then run this file again.
goto failed

:create_with_py312
py -3.12 -m venv .venv
if not "%errorlevel%"=="0" goto failed
goto validate_environment

:create_with_python
python -m venv .venv
if not "%errorlevel%"=="0" goto failed
goto validate_environment

:create_with_py3
py -3 -m venv .venv
if not "%errorlevel%"=="0" goto failed

:validate_environment
".venv\Scripts\python.exe" -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)"
if not "%errorlevel%"=="0" goto unsupported_environment
echo [2/3] Installing the required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if not "%errorlevel%"=="0" goto failed
echo [3/3] Checking Qt, Excel support, and the official template...
".venv\Scripts\python.exe" -c "from PySide6 import QtWidgets; import openpyxl; from app.templates.engine import template_path; from openpyxl import load_workbook; w=load_workbook(template_path(),keep_links=False); assert w.sheetnames==['Attendance','Seat Plan']; w.close()"
if not "%errorlevel%"=="0" goto failed
echo.
echo Setup completed. Close this window and double-click the launch batch file.
echo Existing student data and saved exam arrangements have been kept.
if not defined FOF_NO_PAUSE pause
exit /b 0

:unsupported_environment
echo The existing .venv does not use supported 64-bit Python 3.12 or newer.
echo Install the correct Python, rename .venv to .venv_old, then run setup again.

:failed
echo.
echo Setup did not complete. Please keep the error message above for troubleshooting.
if not defined FOF_NO_PAUSE pause
exit /b 1

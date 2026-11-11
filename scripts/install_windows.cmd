@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0\.."
if /i "%~1"=="--no-pause" set "FOF_NO_PAUSE=1"
title FOF Exam Manager - First-time setup
echo FOF Exam Seating and Attendance Manager
echo First-time setup requires Internet access. Daily use is offline.
echo.
call "%~dp0windows_environment.cmd"
if not "%errorlevel%"=="0" goto failed
echo Python environment: "%FOF_VENV_DIR%"
echo [1/3] Looking for standard 64-bit Python 3.12, 3.13 or 3.14...
if not exist "%FOF_PYTHON%" goto find_python
"%FOF_PYTHON%" "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto install_packages
echo The existing environment uses an unsupported Python. Looking for a compatible version.

:find_python
py -3.12 "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py312
py -3.13 "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py313
py -3.14 "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py314
python "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto create_with_python
py -3 "%~dp0prepare_environment.py" --probe >nul 2>&1
if "%errorlevel%"=="0" goto create_with_py3

echo No compatible standard 64-bit Python was found.
echo Python 3.15 and preview/free-threaded builds are not supported by these packages.
echo Install Python 3.12 x64, then run this setup again. You can keep Python 3.15 installed.
echo Download: https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
echo C++ Build Tools are not needed. Existing data and environments have not been changed.
goto failed

:create_with_py312
py -3.12 "%~dp0prepare_environment.py" "%FOF_VENV_DIR%"
if not "%errorlevel%"=="0" goto failed
goto install_packages

:create_with_py313
py -3.13 "%~dp0prepare_environment.py" "%FOF_VENV_DIR%"
if not "%errorlevel%"=="0" goto failed
goto install_packages

:create_with_py314
py -3.14 "%~dp0prepare_environment.py" "%FOF_VENV_DIR%"
if not "%errorlevel%"=="0" goto failed
goto install_packages

:create_with_python
python "%~dp0prepare_environment.py" "%FOF_VENV_DIR%"
if not "%errorlevel%"=="0" goto failed
goto install_packages

:create_with_py3
py -3 "%~dp0prepare_environment.py" "%FOF_VENV_DIR%"
if not "%errorlevel%"=="0" goto failed

:install_packages
echo [2/3] Installing the required packages...
set "FOF_PIP_REPAIR="
rem A failed installation may leave package metadata behind. Reinstall until
rem a complete Qt/template verification has succeeded at least once.
if not exist "%FOF_VENV_DIR%\.fof-setup-complete" set "FOF_PIP_REPAIR=--force-reinstall"
if exist "%FOF_VENV_DIR%\.fof-setup-complete" del /q "%FOF_VENV_DIR%\.fof-setup-complete"
"%FOF_PYTHON%" -m pip install --only-binary=:all: --disable-pip-version-check %FOF_PIP_REPAIR% -r requirements.txt
if not "%errorlevel%"=="0" goto failed
echo [3/3] Checking Qt, Excel support, and the official template...
"%FOF_PYTHON%" "%~dp0check_environment.py"
if "%errorlevel%"=="0" goto verified_environment
rem Metadata may exist even when a package is incomplete; repair it once.
echo Repairing incomplete packages...
"%FOF_PYTHON%" -m pip install --only-binary=:all: --disable-pip-version-check --force-reinstall -r requirements.txt
if not "%errorlevel%"=="0" goto failed
"%FOF_PYTHON%" "%~dp0check_environment.py"
if not "%errorlevel%"=="0" goto failed

:verified_environment
echo verified>"%FOF_VENV_DIR%\.fof-setup-complete"
if not "%errorlevel%"=="0" goto failed
echo.
echo Setup completed. Close this window and double-click the launch batch file.
echo Existing student data and saved exam arrangements have been kept.
if not defined FOF_NO_PAUSE pause
exit /b 0

:failed
echo.
echo Setup did not complete. Please keep the error message above for troubleshooting.
if not defined FOF_NO_PAUSE pause
exit /b 1

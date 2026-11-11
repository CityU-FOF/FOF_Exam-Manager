@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0\.."
title FOF Exam Manager
call "%~dp0windows_environment.cmd"
if not "%errorlevel%"=="0" exit /b 1
if not exist "%FOF_PYTHON%" goto repair_environment
if not exist "%FOF_VENV_DIR%\.fof-setup-complete" goto repair_environment
"%FOF_PYTHON%" "%~dp0check_environment.py"
if "%errorlevel%"=="0" goto launch

:repair_environment
echo Installing or updating required packages. Internet access is needed for this step.
call "%~dp0install_windows.cmd" --no-pause
if not "%errorlevel%"=="0" goto failed
"%FOF_PYTHON%" "%~dp0check_environment.py"
if not "%errorlevel%"=="0" goto failed

:launch
"%FOF_PYTHON%" run.py %*
set "FOF_EXIT_CODE=%errorlevel%"
if not "%FOF_EXIT_CODE%"=="0" (
  echo The application could not complete. Please keep the error message above.
  if not defined FOF_NO_PAUSE pause
)
exit /b %FOF_EXIT_CODE%

:failed
echo Required packages could not be prepared. Please keep the error message above.
if not defined FOF_NO_PAUSE pause
exit /b 1

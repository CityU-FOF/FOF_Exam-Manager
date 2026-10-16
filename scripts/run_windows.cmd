@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0\.."
title FOF Exam Manager
call "%~dp0windows_environment.cmd"
if not "%errorlevel%"=="0" exit /b 1
if not exist "%FOF_PYTHON%" (
  echo Please double-click the first-time setup batch file in the main folder first.
  if not defined FOF_NO_PAUSE pause
  exit /b 1
)
if not exist "%FOF_VENV_DIR%\.fof-setup-complete" (
  echo Package installation has not completed. Run the first-time setup again.
  if not defined FOF_NO_PAUSE pause
  exit /b 1
)
"%FOF_PYTHON%" run.py %*
set "FOF_EXIT_CODE=%errorlevel%"
if not "%FOF_EXIT_CODE%"=="0" (
  echo The application could not complete. Please keep the error message above.
  if not defined FOF_NO_PAUSE pause
)
exit /b %FOF_EXIT_CODE%

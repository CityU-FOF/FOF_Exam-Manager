@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0\.."
title FOF Exam Manager
if not exist ".venv\Scripts\python.exe" (
  echo Please double-click the first-time setup batch file in the main folder first.
  if not defined FOF_NO_PAUSE pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py %*
set "FOF_EXIT_CODE=%errorlevel%"
if not "%FOF_EXIT_CODE%"=="0" (
  echo The application could not complete. Please keep the error message above.
  if not defined FOF_NO_PAUSE pause
)
exit /b %FOF_EXIT_CODE%

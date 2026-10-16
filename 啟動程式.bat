@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0scripts\run_windows.cmd" %*
exit /b %errorlevel%

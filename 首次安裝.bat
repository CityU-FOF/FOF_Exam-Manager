@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0scripts\install_windows.cmd" %*
exit /b %errorlevel%

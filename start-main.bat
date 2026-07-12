@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PS1_PATH=%ROOT_DIR%scripts\start-main.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_PATH%" %*
exit /b %ERRORLEVEL%

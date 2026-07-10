@echo off
setlocal
set "ROOT_DIR=%~dp0"
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\start-main.ps1" %*

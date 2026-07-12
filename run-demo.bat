@echo off
setlocal
set "ROOT_DIR=%~dp0"
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\set-run-mode.ps1" -RunMode "demo"
call "%ROOT_DIR%run_bot.bat" demo

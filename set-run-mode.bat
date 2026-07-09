@echo off
setlocal
set "ROOT_DIR=%~dp0"
set "RUN_MODE=%~1"
if "%RUN_MODE%"=="" (
    set /p RUN_MODE=Enter run mode (auto / mock / live): 
)
if "%RUN_MODE%"=="" (
    echo [Error] Run mode cannot be empty.
    exit /b 1
)
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\set-run-mode.ps1" -RunMode "%RUN_MODE%"

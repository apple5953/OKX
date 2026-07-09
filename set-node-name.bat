@echo off
setlocal
set "ROOT_DIR=%~dp0"
set "NODE_NAME=%~1"
if "%NODE_NAME%"=="" (
    set /p NODE_NAME=Enter node name: 
)
if "%NODE_NAME%"=="" (
    echo [Error] Node name cannot be empty.
    exit /b 1
)
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\set-node-name.ps1" -NodeName "%NODE_NAME%"

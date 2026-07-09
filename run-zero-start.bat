@echo off
setlocal
set "ROOT_DIR=%~dp0"
set "NODE_NAME=%~1"
if "%NODE_NAME%"=="" set "NODE_NAME=%OKX_NODE_NAME%"
if "%NODE_NAME%"=="" set "NODE_NAME=%NODE_NAME%"
powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\bootstrap-zero-start.ps1" -NodeName "%NODE_NAME%"

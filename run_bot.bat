@echo off
setlocal enabledelayedexpansion
title OKX V12 Harmonic Agent Portable Suite

set "RUN_MODE=%~1"
if not "%RUN_MODE%"=="" (
    set "OKX_RUN_MODE=%RUN_MODE%"
)

echo ===================================================
echo   OKX V12 Harmonic Agent - Portable Startup Script
echo   Status: Pure Portable (No Install, No Admin Required)
echo ===================================================
echo.

:: Detect current directory and drive
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: Set paths for dependencies inside the project folder to keep it 100% self-contained
set "DEPS_DIR=%ROOT_DIR%.deps"
set "PORTABLE_PYTHON_DIR=%DEPS_DIR%\python-portable"
set "PYTHON_EXE=%PORTABLE_PYTHON_DIR%\python.exe"

if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"

:: Check if portable Python is already configured
if exist "%PYTHON_EXE%" (
    echo [OK] Portable Python environment detected.
    goto :run_app
)

echo [Info] Configuring portable Python environment in: 
echo        %PORTABLE_PYTHON_DIR%
echo.

:: 1. Download Portable Python Zip from official servers
echo [1/4] Downloading official Python 3.12.3 Windows 64-bit embeddable suite...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip', '%DEPS_DIR%\python-portable.zip')"

if not exist "%DEPS_DIR%\python-portable.zip" (
    echo [Error] Failed to download Python portable zip. Please check internet connection.
    pause
    exit /b 1
)

:: 2. Extract Python zip
echo [2/4] Extracting Python package...
if not exist "%PORTABLE_PYTHON_DIR%" mkdir "%PORTABLE_PYTHON_DIR%"
powershell -Command "Expand-Archive -Path '%DEPS_DIR%\python-portable.zip' -DestinationPath '%PORTABLE_PYTHON_DIR%' -Force"
del /f /q "%DEPS_DIR%\python-portable.zip"

:: Enable site-packages in embeddable python (CRITICAL step for portable python.exe)
set "PTH_FILE=%PORTABLE_PYTHON_DIR%\python312._pth"
if exist "%PTH_FILE%" (
    echo import site >> "%PTH_FILE%"
    findstr /x /c:"..\.." "%PTH_FILE%" >nul 2>nul || echo ..\..>> "%PTH_FILE%"
)

:: 3. Download & Configure pip (python packaging utility)
echo [3/4] Fetching green pip installer...
powershell -Command "(New-Object System.Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%DEPS_DIR%\get-pip.py')"
"%PYTHON_EXE%" "%DEPS_DIR%\get-pip.py" --no-warn-script-location
del /f /q "%DEPS_DIR%\get-pip.py"

:: 4. Install requirements to the portable site-packages
echo [4/4] Installing robot libraries (CCXT, pandas, Flask, etc.)...
"%PYTHON_EXE%" -m pip install --no-warn-script-location ccxt pandas flask

echo.
echo ===================================================
echo [Success] Green Sandbox environment is now ready!
echo ===================================================
echo.

:run_app
if not "%OKX_RUN_MODE%"=="" (
    echo [Info] Run mode: %OKX_RUN_MODE%
)
echo [Info] Booting OKX V12 Harmonic Agent...
if not "%OKX_OPEN_UI%"=="0" (
    echo [Info] UI will open at http://127.0.0.1:5000
    start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:5000'"
)
"%PYTHON_EXE%" server.py
pause

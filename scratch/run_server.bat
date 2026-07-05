@echo off
setlocal
set "PYTHONPATH=D:\okx\harmonic_agent\.deps"
set "PYTHONUNBUFFERED=1"
cd /d D:\okx\harmonic_agent
echo [%date% %time%] launching server>> "D:\okx\harmonic_agent\scratch\server.out.log"
"C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -u server.py >> "D:\okx\harmonic_agent\scratch\server.out.log" 2>> "D:\okx\harmonic_agent\scratch\server.err.log"

@echo off
cd /d "%~dp0"
set "PYW=C:\Users\Lu\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\pythonw.exe"
set "PY=C:\Users\Lu\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"
if exist "%PYW%" (
    start "" "%PYW%" main.py
    exit /b 0
)
if exist "%PY%" (
    start "" "%PY%" main.py
    exit /b 0
)
echo ERROR: Python with PySide6 not found. Ask TRAE assistant to fix.
pause

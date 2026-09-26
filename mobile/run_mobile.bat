@echo off
rem ==============================================================
rem DTC Knowledge Graph - Galaxy Mobile Web Server Launcher
rem Pure ASCII Script adhering to Global Encoding Standards
rem ==============================================================

cd /d "%~dp0"

echo [INFO] Starting DTC Knowledge Graph Galaxy Mobile Server...
echo [INFO] Working Directory: %CD%

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not found in system PATH.
    echo [ERROR] Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

python app.py --port 5050
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Server exited with an error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

pause

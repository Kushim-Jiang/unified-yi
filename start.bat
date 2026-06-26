@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   Unified Yi Character Manager
echo   Starting server...
echo ============================================
echo.

:: ─── Kill existing server on port 8080 ───
echo [1/3] Checking for existing server on port 8080...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080.*LISTENING" 2^>nul') do (
    set PID=%%a
    echo   Found process PID !PID! on port 8080, killing...
    taskkill /PID !PID! /F >nul 2>&1
    echo   Killed PID !PID!
)

:: Wait a moment for port to free
timeout /t 2 /nobreak >nul

:: Also kill any uvicorn processes (extra safety)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "uvicorn" 2^>nul') do (
    echo   Found uvicorn process %%a, killing...
    taskkill /PID %%a /F >nul 2>&1
)

echo   Port 8080 is clear.
echo.

:: ─── Activate venv if exists ───
if exist "%~dp0.venv\Scripts\activate.bat" (
    call "%~dp0.venv\Scripts\activate.bat"
)

:: ─── Install dependencies ───
echo [2/3] Installing Python dependencies...
python -m pip install -q -r src\backend\requirements.txt
echo   Dependencies ready.
echo.

:: ─── Start server ───
echo [3/3] Starting backend server at http://localhost:8080
echo.
echo   Frontend:  http://localhost:8080
echo   Align:     http://localhost:8080/align.html
echo   API Docs:  http://localhost:8080/docs
echo.
echo   Press Ctrl+C to stop.
echo ============================================
echo.

cd /d "%~dp0"
python src/backend/main.py

pause

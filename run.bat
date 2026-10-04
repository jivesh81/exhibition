@echo off
REM ============================================================
REM  SafeSight AI - One-Command Startup (Windows)
REM  AI-Powered Workplace Safety Monitoring and Risk Assessment
REM  Group 173 Prototype
REM ============================================================
title SafeSight AI - Group 173

echo.
echo  ============================================
echo    SafeSight AI - Starting...
echo    AI-Powered Workplace Safety Monitoring
echo    Group 173 Prototype
echo  ============================================
echo.

cd /d "%~dp0"

REM ---- Optional: check dependencies and install if missing ----
python -c "import fastapi, uvicorn, cv2, numpy" >nul 2>&1
if errorlevel 1 (
    echo  [Setup] Installing backend dependencies...
    pip install -r backend\requirements.txt
    echo.
)

if not exist "frontend\dist\index.html" (
    echo  [Setup] Building frontend ^(first run only^)...
    if not exist "frontend\node_modules" (
        cd frontend
        call npm install --no-audit --no-fund
        cd ..
    )
    cd frontend
    call npm run build
    cd ..
    echo.
)

REM ---- Start backend (serves the built frontend on port 8000) ----
echo  [SafeSight] Starting backend on http://127.0.0.1:8000
start "SafeSight Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

REM ---- Wait for the backend to come up ----
timeout /t 4 /nobreak >nul

REM ---- Open the app in the default browser ----
start http://127.0.0.1:8000/

echo.
echo  ============================================
echo    SafeSight AI is running:
echo      URL:  http://127.0.0.1:8000
echo      API:  http://127.0.0.1:8000/docs
echo.
echo    Then click  START LIVE DEMO  on the dashboard.
echo    Close the "SafeSight Backend" window to stop.
echo  ============================================
echo.
pause

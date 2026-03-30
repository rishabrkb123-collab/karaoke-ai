@echo off
title VocalRemover Launcher
color 0A
echo ================================================
echo   VocalRemover - Free Karaoke Maker
echo   Powered by Demucs (Meta AI)
echo ================================================
echo.

:: ── 1. Ensure venv exists ────────────────────────────────────────────────────
if not exist "backend\venv\Scripts\python.exe" (
    echo [1/4] Creating Python virtual environment...
    python -m venv backend\venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual env.
        echo Run install.bat first to set everything up.
        pause
        exit /b 1
    )
)

:: ── 2. Activate venv ─────────────────────────────────────────────────────────
call backend\venv\Scripts\activate.bat

:: ── 3. Install / verify backend deps (errors now visible) ────────────────────
echo [2/4] Checking backend dependencies...
pip install -q -r backend\requirements.txt
if errorlevel 1 (
    echo.
    echo WARNING: Some packages failed to install.
    echo If uploads fail, close this window and run install.bat to reinstall.
    echo.
)

:: ── 4. Install frontend deps if needed ───────────────────────────────────────
if not exist "frontend\node_modules" (
    echo [3/4] Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

:: ── 5. Kill old backend so we always run fresh updated code ──────────────────
echo [4/4] Starting servers...
echo.

:: Read the old port BEFORE deleting the file, then kill that process
set OLD_PORT=8000
if exist "backend\.port" (
    set /p OLD_PORT=<backend\.port
)
echo   Stopping any old backend on port %OLD_PORT%...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%OLD_PORT% " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Delete stale port file so vite reads a fresh one
if exist "backend\.port" del /f "backend\.port" >nul 2>&1

:: ── 6. Launch backend (run.py picks a free port and writes .port) ─────────────
start "VocalRemover Backend" cmd /k "call backend\venv\Scripts\activate.bat && cd backend && python run.py"

:: Wait for run.py to write .port (happens in ~1s, before uvicorn starts)
echo   Waiting for backend to choose a port...
set /a dot_attempts=0
:wait_port_file
timeout /t 1 /nobreak >nul
set /a dot_attempts+=1
if exist "backend\.port" goto read_port
if %dot_attempts% geq 20 (
    echo   WARNING: backend\.port not written after 20s. Defaulting to 8000.
    set BACKEND_PORT=8000
    goto wait_health
)
goto wait_port_file

:read_port
set /p BACKEND_PORT=<backend\.port
echo   Backend using port %BACKEND_PORT%

:: Poll health endpoint until uvicorn is ready (up to 60s)
:wait_health
echo   Waiting for backend to be ready...
set /a health_attempts=0
:wait_health_loop
timeout /t 2 /nobreak >nul
set /a health_attempts+=1
curl -s --max-time 1 http://localhost:%BACKEND_PORT%/api/health >nul 2>&1
if not errorlevel 1 goto backend_ready
if %health_attempts% geq 30 (
    echo.
    echo   WARNING: Backend did not respond after 60s.
    echo   Check the "VocalRemover Backend" window for errors.
    goto start_frontend
)
goto wait_health_loop

:backend_ready
echo   Backend is ready on http://localhost:%BACKEND_PORT%
echo.

:: ── 7. Start frontend ─────────────────────────────────────────────────────────
:start_frontend
echo   Starting frontend (URL shown below)...
echo   Press Ctrl+C to stop. Close the backend window separately.
echo.
cd frontend
npm run dev

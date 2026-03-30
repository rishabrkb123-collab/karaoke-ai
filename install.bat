@echo off
title VocalRemover - First Time Setup
color 0B
echo ================================================
echo   VocalRemover - Installation
echo ================================================
echo.
echo This will install all dependencies.
echo Requires: Python 3.9+, Node.js 18+, pip
echo.
pause

echo.

:: Skip venv creation if it already exists (avoids Permission Denied when backend is running)
if exist "backend\venv\Scripts\python.exe" (
    echo [1/5] Virtual environment already exists, skipping creation.
) else (
    echo [1/5] Creating Python virtual environment...
    python -m venv backend\venv
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create virtual environment.
        echo   - Make sure Python 3.9+ is installed: python.org
        echo   - If backend\venv exists but is broken, delete it manually and re-run.
        pause
        exit /b 1
    )
)

echo [2/5] Activating virtual environment...
call backend\venv\Scripts\activate.bat

echo [3/5] Installing PyTorch 2.5.0 CPU (no FFmpeg needed)...
pip install torch==2.5.0+cpu torchaudio==2.5.0+cpu --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo ERROR: Failed to install PyTorch. Check your internet connection.
    pause
    exit /b 1
)

echo [4/5] Installing remaining dependencies (Demucs + FastAPI)...
pip install fastapi "uvicorn[standard]" python-multipart demucs==4.0.1 soundfile
if errorlevel 1 (
    echo ERROR: Failed to install Python packages.
    pause
    exit /b 1
)

echo [5/5] Installing Node.js dependencies...
cd frontend
call npm install
cd ..
if errorlevel 1 (
    echo ERROR: npm install failed. Make sure Node.js 18+ is installed: nodejs.org
    pause
    exit /b 1
)

echo.
echo Pre-downloading Demucs AI models (htdemucs_ft, ~160MB)...
python -c "from demucs.pretrained import get_model; get_model('htdemucs_ft'); print('Model downloaded and ready!')"

echo.
echo ================================================
echo   Installation complete!
echo   Run start.bat to launch VocalRemover
echo ================================================
pause

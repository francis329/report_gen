@echo off
chcp 65001 >nul
echo ================================
echo   Report Generator - Starter
echo ================================
echo.

:: Initialize conda
where conda >nul 2>&1
if errorlevel 1 (
    echo [Error] Conda not found. Please install Anaconda/Miniconda.
    pause
    exit /b 1
)

:: Activate report environment
echo [0/4] Activating conda environment: report...
call conda activate report

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python not found in report environment
    pause
    exit /b 1
)

echo [1/4] Starting backend service...
start cmd /k "cd /d %~dp0 && conda activate report && python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

:: Wait for backend
timeout /t 3 /nobreak >nul

echo [2/4] Backend started (http://localhost:8000)
echo.

:: Check Node.js
cd frontend
node --version >nul 2>&1
if errorlevel 1 (
    echo [Warning] Node.js not found, cannot start frontend
    echo Please run manually: cd frontend ^&^& npm run dev
    pause
    exit /b 0
)

:: Check node_modules
if not exist "node_modules" (
    echo [3/4] First run, installing frontend dependencies...
    call npm install
)

echo [4/4] Starting frontend service...
start cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ================================
echo   Startup complete!
echo   Backend: http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/docs
echo ================================
echo.
pause

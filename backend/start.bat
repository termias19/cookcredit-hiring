@echo off
echo.
echo  ====================================
echo   Mise Backend - Local Setup (Windows)
echo  ====================================
echo.

REM ── Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from python.org
    pause & exit /b 1
)

REM ── Create virtual environment ────────────────────────────────────────────
if not exist "venv" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/4] Virtual environment already exists, skipping...
)

REM ── Activate venv ─────────────────────────────────────────────────────────
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

REM ── Install dependencies ──────────────────────────────────────────────────
echo [3/4] Installing dependencies...
pip install -r requirements.txt --quiet

REM ── Check .env ────────────────────────────────────────────────────────────
if not exist ".env" (
    echo.
    echo [!] No .env file found - copying from .env.example
    echo [!] IMPORTANT: Open .env and fill in your real keys before continuing
    echo.
    copy .env.example .env
    pause
)

REM ── Check Firebase credentials ────────────────────────────────────────────
if not exist "firebase-credentials.json" (
    echo.
    echo [!] firebase-credentials.json not found!
    echo [!] Download it from Firebase Console and place it in the backend/ folder
    echo.
    pause
)

REM ── Start Flask ───────────────────────────────────────────────────────────
echo [4/4] Starting Flask server on http://localhost:5000
echo.
echo  API endpoints ready:
echo    GET  http://localhost:5000/api/health
echo    POST http://localhost:5000/api/auth/sync
echo    GET  http://localhost:5000/api/auth/me
echo    POST http://localhost:5000/api/requests/
echo    GET  http://localhost:5000/api/requests/
echo    POST http://localhost:5000/api/stripe/connect/onboard
echo    POST http://localhost:5000/api/stripe/tip/create
echo    POST http://localhost:5000/api/stripe/webhook
echo.
echo  Press Ctrl+C to stop
echo.

python app.py

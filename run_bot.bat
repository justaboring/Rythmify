@echo off
chcp 65001 >nul
title Discord Music Bot
cd /d "%~dp0"

:: ── Activate venv ────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [run] Using .venv Python
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [run] Using venv Python
) else (
    echo [run] No .venv found, using system Python
)

:: ── Check .env ───────────────────────────────────────────────
if not exist ".env" (
    echo [ERROR] .env file not found!
    echo         Copy .env.example to .env and fill in DISCORD_TOKEN
    pause
    exit /b 1
)

:: ── Run the bot ──────────────────────────────────────────────
echo [run] Starting Discord Music Bot...
python bot.py
if errorlevel 1 (
    echo.
    echo [ERROR] Bot exited with an error.
    pause
)

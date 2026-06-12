@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Discord Music Bot — Windows Installer

echo ================================================
echo   Discord Music Bot — Windows Installer
echo ================================================

:: ── 1. Check Python ─────────────────────────────────────────
echo.
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Python not found!
    echo   Install Python 3.10+ from: https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [OK] %%v

:: ── 2. Check / Install FFmpeg ────────────────────────────────
echo.
echo [2/4] Checking FFmpeg...
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('ffmpeg -version 2^>^&1 ^| findstr "ffmpeg version"') do echo   [OK] %%v
    goto ffmpeg_done
)

echo   FFmpeg not found in PATH.
echo   Attempting to install via winget...

winget --version >nul 2>&1
if not errorlevel 1 (
    winget install --id Gyan.FFmpeg --source winget --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 (
        echo   [OK] FFmpeg installed via winget
        echo   [!] Please restart this script after adding FFmpeg to PATH.
        echo       Or set FFMPEG_PATH in .env to the full path of ffmpeg.exe
        goto ffmpeg_done
    )
)

choco --version >nul 2>&1
if not errorlevel 1 (
    choco install ffmpeg -y
    if not errorlevel 1 (
        echo   [OK] FFmpeg installed via Chocolatey
        goto ffmpeg_done
    )
)

echo   [WARN] Could not auto-install FFmpeg.
echo   Manual install options:
echo     1. winget install Gyan.FFmpeg
echo     2. choco install ffmpeg
echo     3. Download from https://www.gyan.dev/ffmpeg/builds/
echo        Extract and add bin\ folder to PATH
echo        OR set FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe in .env

:ffmpeg_done

:: ── 3. Python virtual environment ───────────────────────────
echo.
echo [3/4] Setting up Python virtual environment...

if not exist ".venv" (
    python -m venv .venv
    echo   [OK] Created .venv
) else (
    echo   [INFO] .venv already exists, reusing it
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo   [OK] Python dependencies installed

:: ── 4. .env setup ───────────────────────────────────────────
echo.
echo [4/4] Environment setup...

if not exist ".env" (
    copy .env.example .env >nul
    echo   [ACTION REQUIRED] .env created from template.
    echo   Edit .env and add your DISCORD_TOKEN:
    echo     notepad .env
) else (
    echo   [OK] .env already exists
)

:: ── Done ─────────────────────────────────────────────────────
echo.
echo ================================================
echo   Installation complete!
echo ================================================
echo.
echo   Next steps:
echo   1. Edit .env -^> set your DISCORD_TOKEN
echo   2. Run: run_bot.bat
echo   3. Run diagnostics: .venv\Scripts\python diagnose.py
echo.
pause

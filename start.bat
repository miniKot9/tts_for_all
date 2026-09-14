@echo off
cd /d "%~dp0"

if not exist python\python.exe (
    echo [ERROR] Python not found!
    pause
    exit /b
)

echo Starting TTS for Discord...
echo.

python\python.exe tts_app_v16.py

if errorlevel 1 (
    echo.
    echo [ERROR] Program finished with error.
    pause
)
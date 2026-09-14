@echo off
cd /d "%~dp0"

echo ====================================
echo Portable Python Check
echo ====================================
echo.

if not exist python\python.exe (
    echo [ERROR] python.exe not found in python\ folder
    pause
    exit /b
)

echo [OK] python.exe found
echo.
python\python.exe --version
echo.
echo Python path:
python\python.exe -c "import sys; print(sys.executable)"
echo.
echo ====================================
echo Library check
echo ====================================
echo.

python\python.exe -c "import tkinter; print('[OK] tkinter')" 2>nul || echo [ERROR] tkinter
python\python.exe -c "import torch; print('[OK] torch')" 2>nul || echo [ERROR] torch
python\python.exe -c "import sounddevice; print('[OK] sounddevice')" 2>nul || echo [ERROR] sounddevice
python\python.exe -c "import soundfile; print('[OK] soundfile')" 2>nul || echo [ERROR] soundfile
python\python.exe -c "import numpy; print('[OK] numpy')" 2>nul || echo [ERROR] numpy
python\python.exe -c "import keyboard; print('[OK] keyboard')" 2>nul || echo [ERROR] keyboard
python\python.exe -c "import win32gui; print('[OK] pywin32')" 2>nul || echo [ERROR] pywin32
python\python.exe -c "import omegaconf; print('[OK] omegaconf')" 2>nul || echo [ERROR] omegaconf

echo.
pause
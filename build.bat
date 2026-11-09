@echo off
REM ===== Jaber - build Windows .exe =====
REM Needs Python 3.11 or 3.12 from python.org (tick "Add python.exe to PATH" during install)
cd /d "%~dp0"
if not exist .venv python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :err
pyinstaller --noconfirm --onefile --windowed --name Jaber ^
  --collect-all playwright --collect-all ddgs --collect-all primp ^
  --collect-data edge_tts --collect-submodules googleapiclient ^
  --collect-all sounddevice ^
  main.py || goto :err
echo.
echo DONE: %~dp0dist\Jaber.exe
pause
exit /b 0
:err
echo ERROR - see messages above.
pause
exit /b 1

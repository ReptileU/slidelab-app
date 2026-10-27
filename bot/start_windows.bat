@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv" (
    echo Первый запуск: устанавливаю библиотеки, подождите...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
python bot.py
pause

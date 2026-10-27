@echo off
chcp 65001 >nul
title SlideLab bot
cd /d "%~dp0"
if not exist ".venv" (
    echo Первый запуск: устанавливаю библиотеки, подождите...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
:loop
python bot.py
if %errorlevel%==3 (
    echo.
    echo ===== Перезапуск после обновления =====
    timeout /t 2 /nobreak >nul
    goto loop
)
echo.
echo Бот остановлен. Чтобы запустить снова — дважды щёлкните start_bot.bat
pause

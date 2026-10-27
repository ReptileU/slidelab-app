@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: запуск бота на компьютере. Окно не закрывайте.

where uv >nul 2>nul
if errorlevel 1 (
    echo Первый запуск: устанавливаю uv — он сам поставит нужный Python и библиотеки...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
if not exist ".env" (
    copy .env.example .env >nul
    echo Создал файл .env — впишите в него BOT_TOKEN и ADMIN_ID и запустите снова.
    notepad .env
    pause
    exit /b
)
if not exist "data" mkdir data

uv sync --python 3.12 --no-dev
uv run alembic upgrade head
uv run python -m slidelab.core.seed

:loop
echo Бот SlideLab запущен. Остановить: Ctrl+C
uv run python -m slidelab.bot.main
echo Бот остановился — перезапускаю через 5 секунд...
timeout /t 5 >nul
goto loop

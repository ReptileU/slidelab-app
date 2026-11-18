@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SlideLab: скачивание данных из облака на компьютер (откат)
uv run --no-dev python -m slidelab.tools.cloud_transfer pull
pause

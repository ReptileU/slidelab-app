@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SlideLab: перенос данных с компьютера в облако
uv run --no-dev python -m slidelab.tools.cloud_transfer push
pause

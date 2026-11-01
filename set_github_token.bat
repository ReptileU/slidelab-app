@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: вставить токен GitHub для кнопки «Открыть». Вся работа — в set_github_token.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set_github_token.ps1"
pause

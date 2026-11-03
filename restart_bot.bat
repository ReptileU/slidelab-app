@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: перезапуск бота, если запуск завис. Вся работа — в restart_bot.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_bot.ps1"

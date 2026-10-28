@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: переход со старого бота на новый (один раз). Вся работа — в migrate_windows.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0migrate_windows.ps1" %*
pause

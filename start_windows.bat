@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: запуск всего одним кликом. Вся работа — в start_windows.ps1 (PowerShell есть в любой Windows 10/11).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1"
pause

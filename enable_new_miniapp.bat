@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem SlideLab: включить новую Mini App (один раз). Вся работа — в enable_new_miniapp.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable_new_miniapp.ps1"
pause

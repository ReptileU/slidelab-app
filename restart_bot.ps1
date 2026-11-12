# SlideLab: перезапуск бота, если запуск завис (например, на шаге «Библиотеки и база»).
# Закрывает зависшие процессы бота (uv, python из .venv, cloudflared, окно запуска) и запускает заново.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath $PSScriptRoot
$Root = $PSScriptRoot
Write-Host "> Закрываю зависшие процессы бота..." -ForegroundColor Cyan
$mine = $PID
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $mine -and (
            $_.Name -eq "uv.exe" -or
            ($_.CommandLine -and (
                $_.CommandLine -like "*start_windows.ps1*" -or
                $_.CommandLine -like "*slidelab.bot.main*" -or
                $_.CommandLine -like "*slidelab.api.main*" -or
                $_.CommandLine -like "*slidelab.core.seed*" -or
                $_.CommandLine -like "*alembic*" -or
                $_.CommandLine -like "*cloudflared*localhost:8010*" -or
                $_.CommandLine -like "*cloudflared*tunnel*run*")) -or
            ($_.ExecutablePath -and $_.ExecutablePath -like "$Root\.venv\*"))
    } |
    ForEach-Object {
        Write-Host "  стоп: $($_.Name) ($($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Seconds 2
Write-Host "> Запускаю бота..." -ForegroundColor Cyan
Start-Process -FilePath (Join-Path $Root "start_windows.bat") -WorkingDirectory $Root
Write-Host "Готово. Бот запускается в новом окне — его не закрывайте." -ForegroundColor Green
Start-Sleep -Seconds 3

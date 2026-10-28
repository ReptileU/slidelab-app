# SlideLab: запуск всего одним кликом на Windows — база, API для Mini App, временная ссылка, бот.
# Запускается из start_windows.bat. Окно не закрывайте: Ctrl+C или закрытие окна останавливает всё.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath $PSScriptRoot
$Root = $PSScriptRoot
$Logs = Join-Path $Root "data\logs"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
# Python пишет в UTF-8 — иначе кириллица в логах превратится в «????»
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Step($text) { Write-Host "> $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function EnvValue($name) {
    $line = Get-Content -LiteralPath ".env" -Encoding UTF8 | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
    if ($line) { return $line.Substring($name.Length + 1).Trim() } else { return "" }
}
function StopOld {
    # Прежний запуск ещё работает — останавливаем, иначе два бота будут спорить за обновления Telegram
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and $_.ProcessId -ne $PID -and (
                $_.CommandLine -like "*slidelab.bot.main*" -or
                $_.CommandLine -like "*slidelab.api.main*" -or
                $_.CommandLine -like "*cloudflared*localhost:8010*")
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if (-not (Has "uv")) {
    Step "Первый запуск: устанавливаю uv — он сам поставит нужный Python и библиотеки..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Создал файл .env — впишите в него BOT_TOKEN и ADMIN_ID и запустите снова."
    Start-Process notepad ".env"
    exit 0
}
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

StopOld
Start-Sleep -Seconds 1

# PostgreSQL и Redis — только если они указаны в .env (на домашнем компьютере хватает SQLite)
if ((EnvValue "DATABASE_URL") -like "*postgresql*" -and (Has "docker")) {
    Step "База PostgreSQL и Redis (Docker)..."
    docker compose -p slidelab up -d --wait | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "  Docker не ответил — запустите Docker Desktop" -ForegroundColor Yellow }
}

Step "Библиотеки и база..."
uv sync --python 3.12 --no-dev -q
uv run alembic upgrade head | Out-Null
uv run python -m slidelab.core.seed

# Mini App: собираем, если сборки нет или код новее неё
if (Has "npm") {
    $dist = Join-Path $Root "webapp\dist\index.html"
    $stale = -not (Test-Path $dist)
    if (-not $stale) {
        $built = (Get-Item $dist).LastWriteTime
        $stale = [bool](Get-ChildItem -Recurse -File "webapp\src", "webapp\index.html" | Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 1)
    }
    if ($stale) {
        Step "Собираю Mini App..."
        Push-Location webapp
        if (-not (Test-Path "node_modules")) { npm ci --silent }
        npm run build --silent | Out-Null
        Pop-Location
    }
}

Step "API для Mini App (порт 8010)..."
$apiJob = Start-Job -ArgumentList $Root, $Logs -ScriptBlock {
    param($Root, $Logs)
    Set-Location -LiteralPath $Root
    while ($true) {
        $log = Join-Path $Logs "api.log"
        cmd /c "uv run uvicorn --factory slidelab.api.main:create_app --host 127.0.0.1 --port 8010 >> `"$log`" 2>&1"
        Start-Sleep -Seconds 3
    }
}

# Временная https-ссылка, чтобы Telegram открыл Mini App с этого компьютера.
# Нужна, только если включена новая Mini App (LEGACY_WEBAPP=false) и стоит cloudflared:
#   winget install Cloudflare.cloudflared
$tunnel = $null
if ((EnvValue "LEGACY_WEBAPP") -eq "false") {
    if (Has "cloudflared") {
        Step "Временная ссылка для Mini App..."
        $tunnelLog = Join-Path $Logs "tunnel.log"
        Set-Content -LiteralPath $tunnelLog -Value "" -Encoding UTF8
        $tunnel = Start-Process cloudflared -ArgumentList "tunnel", "--url", "http://localhost:8010" `
            -RedirectStandardError $tunnelLog -RedirectStandardOutput (Join-Path $Logs "tunnel.out.log") `
            -WindowStyle Hidden -PassThru
        $url = $null
        for ($i = 0; $i -lt 40 -and -not $url; $i++) {
            Start-Sleep -Milliseconds 500
            $m = Select-String -LiteralPath $tunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
        if ($url) {
            # Новая ссылка — в .env (UTF-8 без BOM): бот при запуске поставит её на кнопку меню
            $lines = [System.IO.File]::ReadAllLines((Join-Path $Root ".env"), $Utf8NoBom)
            if ($lines | Where-Object { $_ -match "^WEBAPP_URL=" }) {
                $lines = $lines | ForEach-Object { if ($_ -match "^WEBAPP_URL=") { "WEBAPP_URL=$url/" } else { $_ } }
            } else {
                $lines = @($lines) + "WEBAPP_URL=$url/"
            }
            [System.IO.File]::WriteAllLines((Join-Path $Root ".env"), [string[]]$lines, $Utf8NoBom)
            Write-Host "  Mini App: $url"
        } else {
            Write-Host "  Ссылка не создалась — см. $tunnelLog" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Для новой Mini App с этого компьютера нужен cloudflared: winget install Cloudflare.cloudflared" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "SlideLab запущен. Логи: data\logs\. Остановить: Ctrl+C или закрыть окно." -ForegroundColor Green
Write-Host ""
try {
    while ($true) {
        # через cmd: логи Python идут в поток ошибок, а PowerShell показал бы каждую строку красной «ошибкой»
        cmd /c "uv run python -m slidelab.bot.main 2>&1" | Tee-Object -FilePath (Join-Path $Logs "bot.log") -Append
        Write-Host "Бот остановился — перезапускаю через 5 секунд..."
        Start-Sleep -Seconds 5
    }
} finally {
    Write-Host "Останавливаю SlideLab..."
    Stop-Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job $apiJob -Force -ErrorAction SilentlyContinue
    if ($tunnel) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    StopOld
}

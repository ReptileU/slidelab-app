# SlideLab: переход со старого бота (папка slidelab_bot) на новый — один раз.
# Запускается из migrate_windows.bat. Что делает:
#   1) останавливает старый бот и отключает его запуск (start_bot.bat → start_bot.bat.old);
#   2) делает .env из старого settings.txt (имена настроек те же) + настройки нового бота;
#   3) ставит библиотеки, создаёт базу и переносит в неё заказы, клиентов и пакеты;
#   4) переносит состояние постов канала и картинки, чтобы старые посты не ушли повторно;
#   5) запускает новый бот (start_windows.ps1).
# Папка заказов остаётся прежней (slidelab_bot\orders) — задание Claude менять не нужно.
param([string]$Old = (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "slidelab_bot"))

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location -LiteralPath $PSScriptRoot
$Root = $PSScriptRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Step($text) { Write-Host "> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "X $text" -ForegroundColor Red; exit 1 }

if (-not (Test-Path -LiteralPath (Join-Path $Old "orders.json"))) {
    Fail "Не нашёл старый бот в $Old (нет orders.json). Запустите: migrate_windows.bat ""полный\путь\к\slidelab_bot"""
}
$OldOrders = Join-Path $Old "orders"

# 1) Старый бот — стоп
Step "Останавливаю старый бот..."
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and
        $_.CommandLine -like "*slidelab_bot*" -and
        ($_.CommandLine -like "*bot.py*" -or $_.CommandLine -like "*start_bot*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$oldStart = Join-Path $Old "start_bot.bat"
if (Test-Path -LiteralPath $oldStart) {
    Rename-Item -LiteralPath $oldStart -NewName "start_bot.bat.old" -Force
    Write-Host "  start_bot.bat → start_bot.bat.old (вернуть старый бот: переименовать обратно)"
}

# 2) .env
$envFile = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Step "Переношу настройки из settings.txt в .env..."
    $src = Join-Path $Old "settings.txt"
    if (-not (Test-Path -LiteralPath $src)) { Fail "Нет $src" }
    $lines = [System.Collections.Generic.List[string]]::new()
    [System.IO.File]::ReadAllLines($src) | ForEach-Object { $lines.Add($_) }
    $have = @{}
    foreach ($l in $lines) { if ($l -match "^\s*([A-Z_]+)\s*=") { $have[$Matches[1]] = $true } }
    $add = [ordered]@{
        "DATABASE_URL"  = "sqlite+aiosqlite:///data/slidelab.db"
        "REDIS_URL"     = ""
        "WORK_DIR"      = $OldOrders
        "CONTENT_DIR"   = "content"
        "LEGACY_WEBAPP" = "true"
        "MINIAPP_URL"   = "https://reptileu.github.io/slidelab-app/"
        "MENU_BUTTON"   = "SlideLab"
        "STUCK_HOURS"   = "3"
    }
    $lines.Add("")
    $lines.Add("# --- Новый бот (добавлено при переносе) ---")
    foreach ($k in $add.Keys) { if (-not $have[$k]) { $lines.Add("$k=$($add[$k])") } }
    [System.IO.File]::WriteAllLines($envFile, $lines.ToArray(), $Utf8NoBom)
    Write-Host "  .env готов (токен и реквизиты — из settings.txt, в git не попадает)"
} else {
    Write-Host "  .env уже есть — оставляю как есть"
}

# 3) Библиотеки, база, перенос заказов
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Step "Устанавливаю uv (он сам поставит Python 3.12 и библиотеки)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data\logs") | Out-Null
Step "Библиотеки..."
uv sync --python 3.12 --no-dev -q
if ($LASTEXITCODE -ne 0) { Fail "Библиотеки не установились (нужен интернет)" }
Step "База..."
uv run --no-dev python -m alembic upgrade head
uv run --no-dev python -m slidelab.core.seed
Step "Переношу заказы, клиентов и пакеты из старого бота..."
uv run --no-dev python -m slidelab.tools.import_legacy "$Old"
if ($LASTEXITCODE -ne 0) { Fail "Перенос заказов не удался — старый бот не тронут, можно вернуть start_bot.bat" }

# 4) Посты канала и картинки
$oldState = Join-Path $Old "posts\state.json"
if (Test-Path -LiteralPath $oldState) {
    Copy-Item -LiteralPath $oldState -Destination (Join-Path $Root "content\posts\state.json") -Force
    Write-Host "  состояние постов канала перенесено (опубликованные не повторятся)"
}
$oldMedia = Join-Path $Old "media"
if (Test-Path -LiteralPath $oldMedia) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "content\media") | Out-Null
    Copy-Item -Path (Join-Path $oldMedia "*") -Destination (Join-Path $Root "content\media") -Recurse -Force
}

Set-Content -LiteralPath (Join-Path $Root "data\migrated.txt") -Value (Get-Date -Format "yyyy-MM-dd HH:mm") -Encoding UTF8
Write-Host ""
Write-Host "Перенос готов. Запускаю новый бот..." -ForegroundColor Green
Write-Host "Дальше запускайте его файлом start_windows.bat." -ForegroundColor Green
Write-Host ""
& (Join-Path $Root "start_windows.ps1")

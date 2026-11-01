# SlideLab: включить НОВУЮ Mini App на этом компьютере — один раз.
# Запускается из enable_new_miniapp.bat. Что делает:
#   1) останавливает запущенный бот (и окно, которое его перезапускает);
#   2) ставит cloudflared — он даёт Mini App публичную https-ссылку с этого компьютера;
#   3) в .env ставит LEGACY_WEBAPP=false (остальные настройки не трогает и не показывает);
#   4) добавляет бота в автозагрузку Windows;
#   5) запускает бота заново (start_windows.bat) — он сам создаст ссылку и поставит её на кнопку меню.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath $PSScriptRoot
$Root = $PSScriptRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Step($text) { Write-Host "> $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function RefreshPath {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$m;$u"
    foreach ($p in @("$env:ProgramFiles\cloudflared", "${env:ProgramFiles(x86)}\cloudflared",
                     "$env:LOCALAPPDATA\Microsoft\WinGet\Links")) {
        if ($p -and (Test-Path $p)) { $env:Path = "$env:Path;$p" }
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) {
    Write-Host "X Нет файла .env — сначала запустите migrate_windows.bat" -ForegroundColor Red
    exit 1
}

# 1) Стоп текущего бота
Step "Останавливаю запущенный бот..."
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and $_.ProcessId -ne $PID -and (
            $_.CommandLine -like "*start_windows.ps1*" -or
            $_.CommandLine -like "*slidelab.bot.main*" -or
            $_.CommandLine -like "*slidelab.api.main*" -or
            $_.CommandLine -like "*cloudflared*localhost:8010*")
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# 2) cloudflared
RefreshPath
if (-not (Has "cloudflared")) {
    Step "Устанавливаю cloudflared (ссылка для Mini App)..."
    if (Has "winget") {
        winget install --id Cloudflare.cloudflared -e --silent --accept-source-agreements --accept-package-agreements
    } else {
        $dir = Join-Path $env:LOCALAPPDATA "cloudflared"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Invoke-WebRequest "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile (Join-Path $dir "cloudflared.exe")
        $u = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($u -notlike "*$dir*") { [Environment]::SetEnvironmentVariable("Path", "$u;$dir", "User") }
    }
    RefreshPath
}
if (Has "cloudflared") {
    Write-Host "  cloudflared готов"
} else {
    Write-Host "X cloudflared не установился — бот запустится со старой витриной" -ForegroundColor Yellow
}

# 3) .env: LEGACY_WEBAPP=false
Step "Включаю новую Mini App в .env..."
$envFile = Join-Path $Root ".env"
$lines = [System.Collections.Generic.List[string]]::new()
$found = $false
foreach ($l in [System.IO.File]::ReadAllLines($envFile, $Utf8NoBom)) {
    if ($l -match "^\s*LEGACY_WEBAPP\s*=") { $lines.Add("LEGACY_WEBAPP=false"); $found = $true } else { $lines.Add($l) }
}
if (-not $found) { $lines.Add("LEGACY_WEBAPP=false") }
[System.IO.File]::WriteAllLines($envFile, $lines.ToArray(), $Utf8NoBom)
Write-Host "  LEGACY_WEBAPP=false"

# 4) Автозагрузка: ярлык на slidelab_bot\start_bot.bat (он запускает новый бот)
Step "Автозапуск при включении компьютера..."
$startup = [Environment]::GetFolderPath("Startup")
$target = Join-Path (Split-Path $Root -Parent) "start_bot.bat"
if (-not (Test-Path -LiteralPath $target)) { $target = Join-Path $Root "start_windows.bat" }
$already = Get-ChildItem -LiteralPath $startup -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*SlideLab*" -or $_.Name -like "*start_bot*" }
if ($already) {
    Write-Host "  уже есть: $($already.Name -join ', ')"
} else {
    $sh = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup "SlideLab.lnk"))
    $sh.TargetPath = $target
    $sh.WorkingDirectory = Split-Path $target -Parent
    $sh.WindowStyle = 7
    $sh.Save()
    Write-Host "  добавлен ярлык SlideLab в автозагрузку"
}

# 5) Запуск
Step "Запускаю бота с новой Mini App..."
Start-Process -FilePath (Join-Path $Root "start_windows.bat") -WorkingDirectory $Root
Set-Content -LiteralPath (Join-Path $Root "data\new_miniapp.txt") -Value (Get-Date -Format "yyyy-MM-dd HH:mm") -Encoding UTF8
Write-Host ""
Write-Host "Готово. Бот запущен в новом окне — его не закрывайте. Это окно можно закрыть." -ForegroundColor Green

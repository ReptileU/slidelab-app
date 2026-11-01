# SlideLab: один раз вставить токен GitHub, чтобы кнопка «Открыть» всегда вела в актуальное приложение.
# Токен вводится скрыто, записывается только в .env на этом компьютере и нигде не показывается.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) { Write-Host "Нет файла .env" -ForegroundColor Red; exit 1 }

Write-Host "Вставьте токен GitHub (Ctrl+V или правая кнопка мыши) и нажмите Enter." -ForegroundColor Cyan
Write-Host "Символы не будут видны — так и задумано." -ForegroundColor DarkGray
$secure = Read-Host -AsSecureString "Токен"
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ($token.Length -lt 20) { Write-Host "Похоже, токен не вставился. Запустите ещё раз." -ForegroundColor Red; exit 1 }

# Проверка: токен может писать в репозиторий ReptileU/slidelab-app
try {
    $repo = Invoke-RestMethod -Uri "https://api.github.com/repos/ReptileU/slidelab-app" -Headers @{ Authorization = "Bearer $token"; "User-Agent" = "slidelab" }
    if (-not $repo.permissions.push) { Write-Host "Токен не даёт права записи в slidelab-app (нужно Contents: Read and write)." -ForegroundColor Red; exit 1 }
} catch {
    Write-Host "GitHub не принял токен. Проверьте, что он скопирован целиком и выдан на репозиторий slidelab-app." -ForegroundColor Red; exit 1
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$lines = [System.Collections.Generic.List[string]]::new()
$found = $false
foreach ($l in [System.IO.File]::ReadAllLines($envFile, $utf8)) {
    if ($l -match "^\s*GITHUB_TOKEN\s*=") { $lines.Add("GITHUB_TOKEN=$token"); $found = $true } else { $lines.Add($l) }
}
if (-not $found) { $lines.Add("GITHUB_TOKEN=$token") }
[System.IO.File]::WriteAllLines($envFile, $lines.ToArray(), $utf8)
$token = $null
Write-Host "Токен сохранён в .env. Перезапускаю бота..." -ForegroundColor Green
& (Join-Path $PSScriptRoot "enable_new_miniapp.ps1")

# tools/create_shortcut.ps1 — Crea acceso directo en el escritorio del usuario.
#
# Uso:
#   PowerShell:
#       powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1
#   o con ruta custom:
#       powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1 -ExePath "C:\custom\DaniBOD_ZZZ_Analytics.exe"
#
# Si no se pasa -ExePath, busca el .exe en:
#   <repo_root>\app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe

param(
    [string]$ExePath,
    [string]$ShortcutName = "DaniBOD ZZZ Analytics"
)

$ErrorActionPreference = "Stop"

# Resolver ruta del repo (carpeta padre del script)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Resolver ExePath default
if (-not $ExePath) {
    $ExePath = Join-Path $repoRoot "app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"
}

if (-not (Test-Path $ExePath)) {
    Write-Host "ERROR: no se encontro el .exe en: $ExePath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Si todavia no compilaste, ejecuta:"
    Write-Host "    python -m PyInstaller app\build\main.spec --clean --noconfirm --distpath app\build\dist --workpath app\build\work"
    exit 1
}

$iconPath = Join-Path $repoRoot "app\resources\icon.ico"
$workDir  = Split-Path -Parent $ExePath
$desktop  = [Environment]::GetFolderPath("Desktop")
$lnkPath  = Join-Path $desktop "$ShortcutName.lnk"

# Crear shortcut
$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($lnkPath)
$lnk.TargetPath       = $ExePath
$lnk.WorkingDirectory = $workDir
$lnk.WindowStyle      = 1   # Normal
$lnk.Description      = "DaniBOD ZZZ Analytics - Captura y scoring de discos de Zenless Zone Zero"
if (Test-Path $iconPath) {
    $lnk.IconLocation = "$iconPath,0"
} else {
    $lnk.IconLocation = "$ExePath,0"
}
$lnk.Save()

Write-Host "OK: shortcut creado." -ForegroundColor Green
Write-Host "  Target  : $ExePath"
Write-Host "  Shortcut: $lnkPath"
Write-Host "  Icon    : $($lnk.IconLocation)"

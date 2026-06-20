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
    [string]$ShortcutName = "DaniBOD ZZZ Analytics",
    [switch]$Direct   # opt-out: apunta al .exe plano (modo normal, escribe DB). Por
                      # defecto el shortcut va por el launcher READONLY (QA sin tocar datos).
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
if ($Direct) {
    # Modo normal: el .exe plano (escribe DB/avatares).
    $lnk.TargetPath  = $ExePath
    $lnk.Arguments   = ""
    $lnk.Description  = "DaniBOD ZZZ Analytics - modo normal (escribe DB)"
    $mode = "NORMAL (.exe directo)"
} else {
    # Modo READONLY (default): via launcher VBS que setea DANIBOD_READONLY=1 y lanza el
    # .exe sin ventana de consola. El .exe NO escribe DB ni la libreria de avatares.
    $vbs = Join-Path $repoRoot "tools\launch_readonly.vbs"
    if (-not (Test-Path $vbs)) { Write-Host "ERROR: falta $vbs" -ForegroundColor Red; exit 1 }
    $lnk.TargetPath  = (Join-Path $env:WINDIR "System32\wscript.exe")
    $lnk.Arguments   = "`"$vbs`""
    $lnk.Description  = "DaniBOD ZZZ Analytics - modo READONLY (QA: no escribe DB ni avatares)"
    $mode = "READONLY (via launch_readonly.vbs)"
}
$lnk.WorkingDirectory = $workDir
$lnk.WindowStyle      = 1   # Normal
if (Test-Path $iconPath) {
    $lnk.IconLocation = "$iconPath,0"
} else {
    $lnk.IconLocation = "$ExePath,0"
}
$lnk.Save()

Write-Host "OK: shortcut creado." -ForegroundColor Green
Write-Host "  Modo    : $mode"
Write-Host "  Target  : $($lnk.TargetPath) $($lnk.Arguments)"
Write-Host "  Exe     : $ExePath"
Write-Host "  Shortcut: $lnkPath"
Write-Host "  Icon    : $($lnk.IconLocation)"

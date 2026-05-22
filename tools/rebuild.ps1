# tools/rebuild.ps1 — Rebuild completo del .exe + redirige el shortcut del escritorio.
#
# Por qué existe:
#   PyInstaller en --onedir genera el .exe en app\build\dist\DaniBOD_ZZZ_Analytics\.
#   El shortcut del escritorio queda apuntando a la ruta donde se compiló la PRIMERA
#   vez (por ej. una worktree de Claude). En cada rebuild hay que re-apuntarlo, si no
#   el usuario lanza el .exe viejo sin darse cuenta.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1 -SkipBuild   # solo redirige shortcut
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1 -KillRunning # mata instancias previas

param(
    [switch]$SkipBuild,
    [switch]$KillRunning
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exePath  = Join-Path $repoRoot "app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"
$specPath = Join-Path $repoRoot "app\build\main.spec"
$workDir  = Join-Path $repoRoot "app\build\work"
$distDir  = Join-Path $repoRoot "app\build\dist"

Write-Host "=== DaniBOD ZZZ Analytics — Rebuild ===" -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"

# 1) Matar instancias previas (opcional pero recomendado, si no falla el rm)
if ($KillRunning) {
    Write-Host ""
    Write-Host "[1/4] Matando instancias previas del .exe..." -ForegroundColor Yellow
    Get-Process -Name "DaniBOD_ZZZ_Analytics" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  Matando PID $($_.Id)"
        Stop-Process -Id $_.Id -Force
    }
    Start-Sleep -Seconds 2
}

# 2) Rebuild
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[2/4] Limpiando build anterior..." -ForegroundColor Yellow
    if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
    if (Test-Path $distDir) {
        try {
            Remove-Item -Recurse -Force $distDir
        } catch {
            Write-Host "  WARNING: no se pudo limpiar $distDir (.exe corriendo?)" -ForegroundColor Red
            Write-Host "  Reintenta con: powershell -File tools\rebuild.ps1 -KillRunning" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "[3/4] PyInstaller (puede tardar 3-5 min)..." -ForegroundColor Yellow
    Push-Location $repoRoot
    try {
        python -m PyInstaller $specPath --clean --noconfirm --distpath $distDir --workpath $workDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: PyInstaller falló con exit code $LASTEXITCODE" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "[skip] SkipBuild activo — no se compila." -ForegroundColor DarkGray
}

# 3) Verificar que el .exe existe
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: el .exe no existe en $exePath tras el build." -ForegroundColor Red
    exit 1
}
$exeInfo = Get-Item $exePath
Write-Host ""
Write-Host "OK: build presente." -ForegroundColor Green
Write-Host "  Ruta:      $exePath"
Write-Host "  Tamaño:    $([math]::Round($exeInfo.Length / 1MB, 2)) MB"
Write-Host "  Timestamp: $($exeInfo.LastWriteTime)"

# 4) Redirigir el shortcut del escritorio
Write-Host ""
Write-Host "[4/4] Redirigiendo shortcut del escritorio..." -ForegroundColor Yellow
$shortcutScript = Join-Path $PSScriptRoot "create_shortcut.ps1"
powershell -ExecutionPolicy Bypass -File $shortcutScript -ExePath $exePath
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: la creación del shortcut falló (exit $LASTEXITCODE)" -ForegroundColor Yellow
} else {
    Write-Host "OK: shortcut actualizado." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== LISTO ===" -ForegroundColor Cyan
Write-Host "Lanzar con doble-click en 'DaniBOD ZZZ Analytics' del escritorio."
Write-Host "Logs persistentes en: %LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\app.log"

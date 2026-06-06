# tools/rebuild.ps1 - Rebuild .exe + redirect shortcut.
#
# Why: PyInstaller --onedir generates the .exe at app\build\dist\DaniBOD_ZZZ_Analytics\.
# The desktop shortcut needs to be re-pointed each rebuild (specially when builds
# come from different folders, e.g. worktrees vs main repo).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1 -SkipBuild
#   powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1 -KillRunning
#
# Notes:
#   ASCII-only output strings to avoid PowerShell 5.1 + UTF-8 (no BOM) parser issues.

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

Write-Host "=== DaniBOD ZZZ Analytics - Rebuild ===" -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"

# 0) Pick the build interpreter. MUST be the project .venv: it has the clean
#    PaddleOCR stack (numpy 1.26.4 + paddleocr 2.8.1 + paddlepaddle 2.6.2) that
#    produces DETERMINISTIC OCR. The bare 'python' resolves to the Windows Store
#    Python (App Execution Alias) which has numpy 2.x + torch and NO paddleocr ->
#    a degraded, non-deterministic bundle (regression seen 2026-06-06). See
#    Documentacion/Dev_IA/2026-05-31_Hito_2.8_Migracion_Python_PaddleOCR.md.
$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $py = $venvPy
    Write-Host "Interpreter: .venv ($py)" -ForegroundColor Green
} else {
    $py = "python"
    Write-Host "WARNING: .venv not found - falling back to bare 'python'. The build may bundle the wrong PaddleOCR." -ForegroundColor Red
}

# Build-env guard: abort if the interpreter is not the clean paddle env. Prevents
# silently bundling the broken numpy-2.x paddle again.
$envCheck = & $py -c "import numpy, importlib.util as u; ok = numpy.__version__.startswith('1.') and (u.find_spec('paddleocr') is not None); print(numpy.__version__ + '|' + ('OK' if ok else 'BAD'))"
Write-Host "Build env: numpy/paddleocr -> $envCheck"
if ($envCheck -notmatch "\|OK$") {
    Write-Host "ERROR: wrong build environment (need numpy 1.x + paddleocr). Use the project .venv:" -ForegroundColor Red
    Write-Host "  .venv\Scripts\python.exe -m pip install paddlepaddle==2.6.2 paddleocr==2.8.1 numpy==1.26.4" -ForegroundColor Red
    exit 1
}

# 1) Kill running instances (optional)
if ($KillRunning) {
    Write-Host ""
    Write-Host "[1/4] Killing previous .exe instances..." -ForegroundColor Yellow
    Get-Process -Name "DaniBOD_ZZZ_Analytics" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  Killing PID $($_.Id)"
        Stop-Process -Id $_.Id -Force
    }
    Start-Sleep -Seconds 2
}

# 2) Rebuild
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[2/4] Cleaning previous build..." -ForegroundColor Yellow
    if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
    if (Test-Path $distDir) {
        try {
            Remove-Item -Recurse -Force $distDir
        } catch {
            Write-Host "  WARNING: could not remove $distDir (.exe still running?)" -ForegroundColor Red
            Write-Host "  Retry with: powershell -File tools\rebuild.ps1 -KillRunning" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "[3/4] Running PyInstaller (3-5 minutes)..." -ForegroundColor Yellow
    Push-Location $repoRoot
    try {
        & $py -m PyInstaller $specPath --clean --noconfirm --distpath $distDir --workpath $workDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: PyInstaller failed with exit code $LASTEXITCODE" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "[skip] SkipBuild active - no build performed." -ForegroundColor DarkGray
}

# 3) Verify .exe exists
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: .exe not found at $exePath after build." -ForegroundColor Red
    exit 1
}
$exeInfo = Get-Item $exePath
Write-Host ""
Write-Host "OK: build present." -ForegroundColor Green
Write-Host "  Path:      $exePath"
Write-Host "  Size:      $([math]::Round($exeInfo.Length / 1MB, 2)) MB"
Write-Host "  Timestamp: $($exeInfo.LastWriteTime)"

# 4) Redirect desktop shortcut
Write-Host ""
Write-Host "[4/4] Redirecting desktop shortcut..." -ForegroundColor Yellow
$shortcutScript = Join-Path $PSScriptRoot "create_shortcut.ps1"
powershell -ExecutionPolicy Bypass -File $shortcutScript -ExePath $exePath
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: shortcut creation failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
} else {
    Write-Host "OK: shortcut updated." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan
Write-Host "Launch via desktop shortcut: 'DaniBOD ZZZ Analytics'"
Write-Host "Persistent logs at: %LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\app.log"

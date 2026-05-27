# tools/run_debug.ps1 - Launch .exe with debug frame dumping enabled.
#
# Sets DANIBOD_DUMP_FRAMES=1 in the process environment, then launches the
# .exe. Every time _process_agent_stats fires (S18 detected), the raw frame
# is dumped to %LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\debug_frames\.
#
# Combined with F8 (force scan, now resets dedup too), you can iterate
# parser tests over the same screen by hitting F8 multiple times.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\run_debug.ps1
#
# To stop dumping: close the .exe and relaunch normally via desktop shortcut.

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exePath  = Join-Path $repoRoot "app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"

if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: .exe not found at $exePath" -ForegroundColor Red
    Write-Host "Run tools\rebuild.ps1 first." -ForegroundColor Red
    exit 1
}

# Kill any existing instance to avoid double-monitor confusion
Get-Process -Name "DaniBOD_ZZZ_Analytics" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Killing existing PID $($_.Id)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
}
Start-Sleep -Seconds 2

# Dump dir
$dumpDir = Join-Path $env:LOCALAPPDATA "DaniBOD_ZZZ_Analytics\debug_frames"
New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null

Write-Host "=== DEBUG MODE ===" -ForegroundColor Cyan
Write-Host "Frames will be dumped to:"
Write-Host "  $dumpDir"
Write-Host ""
Write-Host "Workflow:"
Write-Host "  1. Open ZZZ, navigate to a character profile -> Atributos base"
Write-Host "  2. Press F8 (force scan) to re-trigger stats extraction"
Write-Host "  3. Repeat F8 as needed - each press dumps a new frame + retries OCR"
Write-Host "  4. Inspect frames in $dumpDir"
Write-Host ""

# Launch with env var set in current process scope
$env:DANIBOD_DUMP_FRAMES = "1"
Write-Host "Launching .exe with DANIBOD_DUMP_FRAMES=1..." -ForegroundColor Green
Start-Process -FilePath $exePath -WorkingDirectory (Split-Path -Parent $exePath)

Write-Host ""
Write-Host "Done. Check logs at: $env:LOCALAPPDATA\DaniBOD_ZZZ_Analytics\app.log"

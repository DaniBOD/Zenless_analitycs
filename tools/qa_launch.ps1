# qa_launch.ps1 — Lanza el .exe apuntado a la DB del REPO (override DANIBOD_DB_PATH).
#
# Para QA en vivo del persist S17: la app escribe en db\danibod_zzz_v2.db (la misma
# que ve el agente), evitando la DB de %LOCALAPPDATA% que el sandbox no puede tocar.
# Ver Dev_IA 2026-06-06 §4f y app\db\connection.py::_resolve_db_path.
#
# Uso:  powershell -ExecutionPolicy Bypass -File tools\qa_launch.ps1
#       powershell -ExecutionPolicy Bypass -File tools\qa_launch.ps1 -ReadOnly
#
# -ReadOnly: setea DANIBOD_READONLY=1 → la app detecta y loguea normal pero NO
#   escribe nada (DB ni librería de avatares). Para testear sin corromper datos.
#
# RNF-01: hace backup timestamped del repo DB antes de lanzar (la app va a escribir).

param(
    [switch]$ReadOnly,
    [string]$Harvest,        # carpeta destino: cosecha frames etiquetados por latch (5R.3)
    [string]$S2Harvest,      # carpeta destino: cosecha tiles de S2 (center+tile) etiquetados
                             # por nodo+slot, para construir refs reales del matcher de sets.
                             # NO toca DB (solo PNGs).
    [switch]$BadgeHarvest,   # crece la librería de badges (avatar_badge_v2.npz) en vivo,
                             # gateada por flujo-ancla (solo disco equipado). NO toca DB.
    [string]$GridDiag,       # carpeta destino: vuelca recortes de badge S17 + verdicto por
                             # disco (DANIBOD_GRID_DIAG). Diagnóstico de crops. NO toca DB.
    [switch]$MemDiag,        # heartbeat de memoria RNF-06 (DANIBOD_MEM_DIAG): loguea RSS +
                             # heap Python + contador OCR cada ~20s al app.log. Diagnóstico.
    [switch]$IdDiag,         # instrumentación de identidad (DANIBOD_ID_DIAG): por disco emitido
                             # loguea [id_diag] grid/det loc+match+voto al app.log. Diagnóstico L.0.
    [switch]$FromSource,     # corre desde fuente (.venv python -m app.main) en vez del .exe.
                             # NECESARIO para instrumentación nueva (id_diag) hasta rebuildear el .exe.
    [switch]$Recapture,      # QA: re-emite cualquier disco al VOLVER a verlo (desactiva la
                             # dedup de sesión, DANIBOD_RECAPTURE). Para re-testear/confirmar.
    [switch]$NoRamGuard,     # QA: apaga el watchdog de RAM (DANIBOD_NO_RAM_GUARD) para no
                             # interrumpir sesiones largas. La RAM crece (fuga residual RNF-06):
                             # usar en QA acotado, cerrar la app al terminar.
    [switch]$NoFocusGate     # QA: desactiva el gate anti-FP por foco (DANIBOD_NO_FOCUS_GATE) →
                             # sigue capturando aunque el juego no esté al frente (para poder
                             # inspeccionar/loguear sin que el alt-tab pause la captura).
)

$ErrorActionPreference = "Stop"

# Raíz del repo = carpeta padre de tools\
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoDb   = Join-Path $repoRoot "db\danibod_zzz_v2.db"
$exe      = Join-Path $repoRoot "app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"

if (-not (Test-Path $repoDb)) { throw "No existe la DB del repo: $repoDb" }
if (-not $FromSource -and -not (Test-Path $exe)) { throw "No existe el .exe (rebuildeá primero o usá -FromSource): $exe" }

# Backup RNF-01 (gitignoreado: db\*.backup_premig_*.db)
$ts  = Get-Date -Format "yyyyMMdd_HHmmss"
$bak = Join-Path $repoRoot "db\danibod_zzz_v2.backup_premig_$ts.db"
Copy-Item $repoDb $bak
Write-Host "[qa_launch] Backup repo DB -> $bak"

# Override: la app abre ESTA DB tal cual (incluso siendo .exe frozen)
$env:DANIBOD_DB_PATH = $repoDb
Write-Host "[qa_launch] DANIBOD_DB_PATH = $($env:DANIBOD_DB_PATH)"

if ($ReadOnly) {
    $env:DANIBOD_READONLY = "1"
    Write-Host "[qa_launch] DANIBOD_READONLY = 1 (modo offline: NO escribe DB ni avatares)"
} else {
    Remove-Item Env:\DANIBOD_READONLY -ErrorAction SilentlyContinue
}
if ($Harvest) {
    $harvestDir = if ([System.IO.Path]::IsPathRooted($Harvest)) { $Harvest } else { Join-Path $repoRoot $Harvest }
    New-Item -ItemType Directory -Force -Path $harvestDir | Out-Null
    $env:DANIBOD_HARVEST = $harvestDir
    Write-Host "[qa_launch] DANIBOD_HARVEST = $harvestDir (cosecha frames etiquetados por latch)"
} else {
    Remove-Item Env:\DANIBOD_HARVEST -ErrorAction SilentlyContinue
}
if ($S2Harvest) {
    $s2Dir = if ([System.IO.Path]::IsPathRooted($S2Harvest)) { $S2Harvest } else { Join-Path $repoRoot $S2Harvest }
    New-Item -ItemType Directory -Force -Path $s2Dir | Out-Null
    $env:DANIBOD_S2_HARVEST = $s2Dir
    Write-Host "[qa_launch] DANIBOD_S2_HARVEST = $s2Dir (cosecha tiles S2 etiquetados nodo+slot)"
} else {
    Remove-Item Env:\DANIBOD_S2_HARVEST -ErrorAction SilentlyContinue
}
if ($BadgeHarvest) {
    $env:DANIBOD_BADGE_HARVEST = "1"
    Write-Host "[qa_launch] DANIBOD_BADGE_HARVEST = 1 (crece avatar_badge_v2.npz · solo disco equipado · NO toca DB)"
    # Verdad de tierra (5R.C): mapa firma_disco→dueño certero del flujo-ancla.
    $mapPath = Join-Path $repoRoot ("audit\equip_map_{0}.json" -f (Get-Date -Format "yyyyMMdd"))
    $env:DANIBOD_EQUIP_MAP = $mapPath
    Write-Host "[qa_launch] DANIBOD_EQUIP_MAP = $mapPath (mapa disco->dueño · verdad de tierra)"
} else {
    Remove-Item Env:\DANIBOD_BADGE_HARVEST -ErrorAction SilentlyContinue
    Remove-Item Env:\DANIBOD_EQUIP_MAP -ErrorAction SilentlyContinue
}
if ($GridDiag) {
    $diagDir = if ([System.IO.Path]::IsPathRooted($GridDiag)) { $GridDiag } else { Join-Path $repoRoot $GridDiag }
    New-Item -ItemType Directory -Force -Path $diagDir | Out-Null
    $env:DANIBOD_GRID_DIAG = $diagDir
    Write-Host "[qa_launch] DANIBOD_GRID_DIAG = $diagDir (vuelca recortes de badge S17 + verdicto)"
} else {
    Remove-Item Env:\DANIBOD_GRID_DIAG -ErrorAction SilentlyContinue
}
if ($MemDiag) {
    $env:DANIBOD_MEM_DIAG = "1"
    Write-Host "[qa_launch] DANIBOD_MEM_DIAG = 1 (heartbeat RSS + pyheap + ocr_calls cada ~20s -> app.log)"
} else {
    Remove-Item Env:\DANIBOD_MEM_DIAG -ErrorAction SilentlyContinue
}
if ($IdDiag) {
    $env:DANIBOD_ID_DIAG = "1"
    Write-Host "[qa_launch] DANIBOD_ID_DIAG = 1 (por disco: [id_diag] grid/det loc+match+voto -> app.log)"
} else {
    Remove-Item Env:\DANIBOD_ID_DIAG -ErrorAction SilentlyContinue
}
if ($Recapture) {
    $env:DANIBOD_RECAPTURE = "1"
    Write-Host "[qa_launch] DANIBOD_RECAPTURE = 1 (QA: re-emite discos al volver a verlos)"
} else {
    Remove-Item Env:\DANIBOD_RECAPTURE -ErrorAction SilentlyContinue
}
if ($NoRamGuard) {
    $env:DANIBOD_NO_RAM_GUARD = "1"
    Write-Host "[qa_launch] DANIBOD_NO_RAM_GUARD = 1 (watchdog RAM OFF - sesion continua)"
} else {
    Remove-Item Env:\DANIBOD_NO_RAM_GUARD -ErrorAction SilentlyContinue
}
if ($NoFocusGate) {
    $env:DANIBOD_NO_FOCUS_GATE = "1"
    Write-Host "[qa_launch] DANIBOD_NO_FOCUS_GATE = 1 (captura sigue aunque el juego no esté al frente)"
} else {
    Remove-Item Env:\DANIBOD_NO_FOCUS_GATE -ErrorAction SilentlyContinue
}
if ($FromSource) {
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "No existe el venv: $py" }
    Write-Host "[qa_launch] Lanzando desde FUENTE: $py -m app.main ..."
    & $py -m app.main
} else {
    Write-Host "[qa_launch] Lanzando $exe ..."
    & $exe
}

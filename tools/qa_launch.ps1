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
    [switch]$BadgeHarvest    # crece la librería de badges (avatar_badge_v2.npz) en vivo,
                             # gateada por flujo-ancla (solo disco equipado). NO toca DB.
)

$ErrorActionPreference = "Stop"

# Raíz del repo = carpeta padre de tools\
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoDb   = Join-Path $repoRoot "db\danibod_zzz_v2.db"
$exe      = Join-Path $repoRoot "app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"

if (-not (Test-Path $repoDb)) { throw "No existe la DB del repo: $repoDb" }
if (-not (Test-Path $exe))    { throw "No existe el .exe (rebuildeá primero): $exe" }

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
Write-Host "[qa_launch] Lanzando $exe ..."

& $exe

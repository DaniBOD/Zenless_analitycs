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
    [switch]$LogDebug,       # baja el piso del log a DEBUG (DANIBOD_LOG_DEBUG): agrega el
                             # RAZONAMIENTO (por qué se vetó un ancla, por qué no se cosechó, por
                             # qué no se persistió). En INFO va un evento por línea y nada más.
    [switch]$Metrics,        # latencia por etapa (DANIBOD_METRICS): capturer/detector/ocr_text a
                             # db\metrics.db, una DB APARTE — la de dominio queda intacta, así que
                             # el sha256 sigue sirviendo de prueba en las corridas readonly.
    [switch]$IdDiag,         # instrumentación de identidad (DANIBOD_ID_DIAG): por disco emitido
                             # loguea [id_diag] grid/det loc+match+voto al app.log. Diagnóstico L.0.
    [switch]$FromSource,     # corre desde fuente (.venv python -m app.main) en vez del .exe.
                             # NECESARIO para instrumentación nueva (id_diag) hasta rebuildear el .exe.
    [switch]$Censo,          # censo de roster (DANIBOD_CENSO): abre o REANUDA una pasada y
                             # cuenta que PJ viste al recorrer el menu. F8 la cierra. El estado
                             # vive en db\census.db, NUNCA en la DB de dominio.
    [switch]$Recapture,      # QA: re-emite cualquier disco al VOLVER a verlo (desactiva la
                             # dedup de sesión, DANIBOD_RECAPTURE). Para re-testear/confirmar.
    [switch]$NoRamGuard,     # QA: apaga el watchdog de RAM (DANIBOD_NO_RAM_GUARD) para no
                             # interrumpir sesiones largas. La RAM crece (fuga residual RNF-06):
                             # usar en QA acotado, cerrar la app al terminar.
    [switch]$NoFocusGate,    # REDUNDANTE desde 2026-07-30: el gate por foco ya viene OFF por
                             # defecto (defaults.toml). Se mantiene por compatibilidad.
    [switch]$FocusGate,      # QA: ACTIVA el gate anti-FP por foco (DANIBOD_FOCUS_GATE) → la
                             # captura se pausa cuando el juego pasa a segundo plano. Sirve para
                             # reproducir el comportamiento viejo si se sospecha de un FP por
                             # ventana ajena tapando el juego.
    [switch]$NoAutoStart,    # QA: arranca la app en REPOSO (DANIBOD_NO_AUTOSTART) → el watcher
                             # de ZZZ queda OFF y la captura NO empieza sola aunque el juego esté
                             # abierto. El usuario la activa a mano con "Iniciar captura".
    [switch]$RestoreFarm     # QA: al arrancar, recarga el contexto de farmeo (última predicción
                             # S13) desde el breadcrumb en disco (DANIBOD_RESTORE_FARM). Sirve
                             # cuando se reinicia la app para aplicar un fix estando en pleno
                             # farmeo: S2 vuelve a tener los 2 candidatos sin revisitar S13.
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
if ($LogDebug) {
    $env:DANIBOD_LOG_DEBUG = "1"
    Write-Host "[qa_launch] DANIBOD_LOG_DEBUG = 1 (agrega el razonamiento interno al app.log)"
} else {
    Remove-Item Env:\DANIBOD_LOG_DEBUG -ErrorAction SilentlyContinue
}
if ($Metrics) {
    $env:DANIBOD_METRICS = "1"
    Write-Host "[qa_launch] DANIBOD_METRICS = 1 (latencia por etapa -> db\metrics.db · NO toca la DB de dominio)"
    Write-Host "[qa_launch]   leer despues con: .\.venv\Scripts\python.exe -m app.scripts.qa.report_latency"
} else {
    Remove-Item Env:\DANIBOD_METRICS -ErrorAction SilentlyContinue
}
if ($Censo) {
    $env:DANIBOD_CENSO = "1"
    Write-Host "[qa_launch] DANIBOD_CENSO = 1 (censo de roster: abre o REANUDA una pasada)"
    Write-Host "[qa_launch]   recorre el menu de personajes PJ por PJ; el estado va a db\census.db"
    Write-Host "[qa_launch]   F8 CIERRA la pasada -> reporte en audit\censos\ + marca de huerfanos"
    Write-Host "[qa_launch]   una pasada que no cerras NO produce huerfanos: podes seguir manana"
} else {
    Remove-Item Env:\DANIBOD_CENSO -ErrorAction SilentlyContinue
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
# El gate por foco ya viene OFF por defecto desde 2026-07-30 (defaults.toml), asi que -NoFocusGate
# quedo redundante: se mantiene por compatibilidad con scripts y con la costumbre de tipearlo.
# Para volver al comportamiento anti-FP en una sesion puntual: -FocusGate.
if ($NoFocusGate) {
    $env:DANIBOD_NO_FOCUS_GATE = "1"
    Write-Host "[qa_launch] DANIBOD_NO_FOCUS_GATE = 1 (redundante: el gate ya viene OFF por defecto)"
} else {
    Remove-Item Env:\DANIBOD_NO_FOCUS_GATE -ErrorAction SilentlyContinue
}
if ($FocusGate) {
    $env:DANIBOD_FOCUS_GATE = "1"
    Write-Host "[qa_launch] DANIBOD_FOCUS_GATE = 1 (gate anti-FP por foco ACTIVADO: pausa en segundo plano)"
} else {
    Remove-Item Env:\DANIBOD_FOCUS_GATE -ErrorAction SilentlyContinue
}
# Breadcrumb del contexto de farmeo: SIEMPRE se deja en QA (barato, un JSON chico) para que un
# relance posterior con -RestoreFarm pueda recargar la última predicción S13. Ruta estable en el
# dir de datos de la app (gitignoreada, no versionada; junto a app.log).
$farmState = Join-Path $env:LOCALAPPDATA "DaniBOD_ZZZ_Analytics\farm_state_qa.json"
$env:DANIBOD_FARM_STATE = $farmState
Write-Host "[qa_launch] DANIBOD_FARM_STATE = $farmState (breadcrumb de predicción S13)"
if ($NoAutoStart) {
    $env:DANIBOD_NO_AUTOSTART = "1"
    Write-Host "[qa_launch] DANIBOD_NO_AUTOSTART = 1 (arranca en reposo: la captura NO empieza sola)"
} else {
    Remove-Item Env:\DANIBOD_NO_AUTOSTART -ErrorAction SilentlyContinue
}
if ($RestoreFarm) {
    $env:DANIBOD_RESTORE_FARM = "1"
    Write-Host "[qa_launch] DANIBOD_RESTORE_FARM = 1 (recarga el contexto de farmeo previo al arrancar)"
} else {
    Remove-Item Env:\DANIBOD_RESTORE_FARM -ErrorAction SilentlyContinue
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

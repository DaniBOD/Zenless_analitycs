# =============================================================================
# Mantenimiento semanal — poda de backups + commit de la DB de dominio
# =============================================================================
# Uso (desde la raíz del repo):
#     powershell -ExecutionPolicy Bypass -File tools\mantenimiento_semanal.ps1
#     ... -DryRun          muestra lo que haría, sin tocar nada
#     ... -Force           commitea aunque no hayan pasado 7 días
#     ... -NoPush          commitea local, sin pushear
#
# Dos tareas que van juntas porque las dos nacen del uso DIARIO de la app:
#
#   1. PODA. Cada arranque deja un backup (`premig` + `session`). En 4 meses de
#      desarrollo se juntaron 592 archivos / 728 MB. El problema no es el disco:
#      es que 592 backups equivalen a ninguno, porque no sabés cuál restaurar.
#      Se conservan los N más nuevos de cada tipo automático y **todos** los
#      nombrados (`precenso_discos`, `predeclaracion`, `prerevert`…), que son los
#      que marcan un evento real.
#
#   2. COMMIT DE LA DB. `db/danibod_zzz_v2.db` está versionada y con uso diario
#      cambia todos los días. Commitearla cada tanto mantiene una copia en el
#      repo sin llenar el historial de blobs.
#
# GUARDAS (RNF-01) — el script se niega a commitear si:
#   · la app está corriendo (la DB podría estar a medio escribir),
#   · `integrity_check` no dice ok, o
#   · `foreign_key_check` devuelve alguna violación.
# =============================================================================
param(
    [switch]$DryRun,
    [switch]$Force,
    [switch]$NoPush,
    [int]$Conservar = 10,
    [int]$DiasMinimos = 7
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$db = Join-Path $repo 'db\danibod_zzz_v2.db'
$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

function Say($msg) { Write-Host "[mant] $msg" }
if ($DryRun) { Say "DRY-RUN: no se toca nada" }

# --- 1. Poda de backups ------------------------------------------------------
$auto = @{}
$nombrados = 0
Get-ChildItem (Join-Path $repo 'db') -Filter 'danibod_zzz_v2.backup_*.db' |
    Sort-Object LastWriteTime | ForEach-Object {
        if ($_.Name -match '^danibod_zzz_v2\.backup_(premig_|session_)?\d{8}_\d{6}\.db$') {
            $tipo = if ($matches[1]) { $matches[1].TrimEnd('_') } else { 'pelado' }
            if (-not $auto.ContainsKey($tipo)) { $auto[$tipo] = @() }
            $auto[$tipo] += $_
        } else { $nombrados++ }
    }

$borrar = @()
foreach ($tipo in $auto.Keys) {
    $fs = $auto[$tipo]
    if ($fs.Count -gt $Conservar) { $borrar += $fs[0..($fs.Count - $Conservar - 1)] }
}
if ($borrar.Count -gt 0) {
    $mb = [math]::Round(($borrar | Measure-Object Length -Sum).Sum / 1MB)
    Say "poda: $($borrar.Count) backups automáticos ($mb MB). Conservo $Conservar por tipo y $nombrados nombrados."
    if (-not $DryRun) { $borrar | Remove-Item -Force }
} else {
    Say "poda: nada que borrar (conservo $Conservar por tipo y $nombrados nombrados)."
}

# --- 2. Commit de la DB ------------------------------------------------------
$viva = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'app\.main' }
if ($viva) {
    Say "LA APP ESTÁ CORRIENDO (pid $($viva.ProcessId -join ', ')) — no se commitea la DB."
    Say "Cerrala y volvé a correr esto; la poda ya se hizo."
    exit 0
}

if (-not (git status --porcelain -- $db)) {
    Say "la DB no cambió desde el último commit — nada que hacer."
    exit 0
}

$ultimo = git log -1 --format=%ct -- $db
if ($ultimo -and -not $Force) {
    $dias = [math]::Floor(((Get-Date) - [DateTimeOffset]::FromUnixTimeSeconds([int]$ultimo).LocalDateTime).TotalDays)
    if ($dias -lt $DiasMinimos) {
        Say "el último commit de la DB fue hace $dias días (mínimo $DiasMinimos). Usá -Force para forzar."
        exit 0
    }
    Say "último commit de la DB: hace $dias días."
}

# Integridad ANTES de commitear: una DB corrupta commiteada es peor que ninguna.
$chequeo = & $py -c @"
import sqlite3, sys
con = sqlite3.connect('file:db/danibod_zzz_v2.db?mode=ro', uri=True)
integ = con.execute('PRAGMA integrity_check').fetchone()[0]
fk = con.execute('PRAGMA foreign_key_check').fetchall()
d = con.execute('SELECT COUNT(*) FROM inventory_discs').fetchone()[0]
a = con.execute('SELECT COUNT(*) FROM agents').fetchone()[0]
w = con.execute('SELECT COUNT(*) FROM inventory_weapons').fetchone()[0]
print(f'{integ}|{len(fk)}|{d}|{a}|{w}')
sys.exit(0 if integ == 'ok' and not fk else 1)
"@
if ($LASTEXITCODE -ne 0) {
    Say "LA DB NO PASA LAS VALIDACIONES ($chequeo) — no se commitea."
    exit 1
}
$integ, $fk, $discos, $agentes, $armas = $chequeo.Trim().Split('|')
Say "integrity=$integ  fk_violaciones=$fk  discos=$discos  agentes=$agentes  armas=$armas"

$msg = @"
data: snapshot semanal de la DB de dominio

discos=$discos  agentes=$agentes  armas=$armas
integrity_check=$integ  foreign_key_check=$fk violaciones

Commit automatico de tools/mantenimiento_semanal.ps1.
"@

if ($DryRun) { Say "commitearía:"; Write-Host $msg; exit 0 }

git add -- $db
git commit -m $msg | Out-Null
Say "commiteado: $(git log -1 --format='%h %s')"
if (-not $NoPush) {
    git push origin HEAD:main | Out-Null
    Say "pusheado a main."
} else {
    Say "sin push (-NoPush)."
}

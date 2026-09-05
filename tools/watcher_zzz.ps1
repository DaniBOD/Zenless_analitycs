# =============================================================================
# Watcher — abre DaniBOD ZZZ Analytics cuando arranca el juego
# =============================================================================
# La app YA detecta la ventana del juego sola (`_check_zzz_window`, cada 3 s) y
# arranca el monitor. Lo unico que le falta es estar viva para poder detectarlo.
# Esto es eso: un proceso chico que mira si `ZenlessZoneZero.exe` existe y,
# cuando aparece, lanza la app.
#
# RNF-03: solo lee la lista de procesos del sistema operativo. No lee memoria del
# juego, no inyecta nada, no simula input. Equivalente a mirar el Administrador
# de tareas.
#
# NO CIERRA LA APP. Decision de Daniel (2026-09-05): la cierra el usuario, porque
# despues de jugar puede querer mirar el panel, el historico u otras pantallas.
# Es coherente con lo que ya hace el controller, que desde el 2026-07-25 tampoco
# detiene el monitor solo cuando la ventana del juego desaparece.
#
# MANTENIMIENTO AL CERRAR. Cuando la app pasa de viva a cerrada, se corre
# `mantenimiento_semanal.ps1`. Ese es el unico momento garantizado en que la DB
# esta quieta y nadie la escribe. El script se auto-limita (no hace nada si no
# pasaron 7 dias, ni si la DB no cambio), asi que llamarlo en cada cierre es
# barato — y resuelve el problema de que Daniel no juega a horario fijo, sin
# depender de una tarea programada a una hora que quiza nunca sirva.
#
# Uso:
#     powershell -ExecutionPolicy Bypass -File tools\watcher_zzz.ps1
#     ... -Instalar         deja un acceso directo en la carpeta Inicio
#     ... -Desinstalar      lo saca
#     ... -SinMantenimiento no corre el mantenimiento al cerrar la app
#     ... -SinPush          el mantenimiento commitea local, sin pushear
# =============================================================================
param(
    [switch]$Instalar,
    [switch]$Desinstalar,
    [switch]$SinMantenimiento,
    [switch]$SinPush,
    [int]$IntervaloSegundos = 15
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$lanzador = Join-Path $repo 'tools\qa_launch.ps1'
$mant = Join-Path $repo 'tools\mantenimiento_semanal.ps1'
$inicio = [Environment]::GetFolderPath('Startup')
$acceso = Join-Path $inicio 'DaniBOD ZZZ Watcher.lnk'
$logDir = Join-Path $env:LOCALAPPDATA 'DaniBOD_ZZZ_Analytics'
$log = Join-Path $logDir 'watcher.log'

# Los mismos nombres que usa `app/core/capturer.py::ZZZ_EXECUTABLE_NAMES`. Son dos
# listas para una sola pregunta: si alla cambian, hay que cambiarlos aca tambien.
$JUEGO = @('ZenlessZoneZero', 'ZZZ')

function Say($m) {
    $linea = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m"
    Write-Host $linea
    try {
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        Add-Content -Path $log -Value $linea -Encoding utf8
    } catch { }
}

# --- instalar / desinstalar el arranque con Windows --------------------------
if ($Desinstalar) {
    if (Test-Path $acceso) { Remove-Item $acceso -Force; Say "quitado de Inicio: $acceso" }
    else { Say "no estaba instalado." }
    exit 0
}
if ($Instalar) {
    $argumentos = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    if ($SinMantenimiento) { $argumentos += " -SinMantenimiento" }
    if ($SinPush) { $argumentos += " -SinPush" }
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut($acceso)
    $lnk.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $lnk.Arguments = $argumentos
    $lnk.WorkingDirectory = $repo
    $lnk.Description = 'Abre DaniBOD ZZZ Analytics cuando arranca Zenless Zone Zero'
    $lnk.Save()
    Say "instalado en Inicio: $acceso"
    Say "argumentos: $argumentos"
    Say "log del watcher: $log"
    Say "para sacarlo:  powershell -File tools\watcher_zzz.ps1 -Desinstalar"
    exit 0
}

# --- el loop -----------------------------------------------------------------
function Juego-Vivo { [bool](Get-Process -Name $JUEGO -ErrorAction SilentlyContinue) }
function App-Viva {
    [bool](Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -match 'app\.main' })
}

Say "watcher arriba (cada $IntervaloSegundos s). Mantenimiento al cerrar: $(if ($SinMantenimiento) {'no'} else {'si'})"
$appAntes = App-Viva

while ($true) {
    try {
        $juego = Juego-Vivo
        $app = App-Viva

        if ($juego -and -not $app) {
            Say "juego detectado y la app no esta -> lanzando"
            Start-Process powershell -ArgumentList @(
                '-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$lanzador,'-FromSource'
            ) -WorkingDirectory $repo
            Start-Sleep -Seconds 30   # darle tiempo a levantar antes de re-evaluar
            $app = App-Viva
        }
        elseif ($appAntes -and -not $app -and -not $SinMantenimiento) {
            # La app se acaba de cerrar: la DB esta quieta. Es el unico momento
            # garantizado para tocarla sin competir con nadie.
            Say "la app se cerro -> corriendo mantenimiento (se auto-limita a 1 vez por semana)"
            try {
                $a = @('-ExecutionPolicy','Bypass','-File',$mant)
                if ($SinPush) { $a += '-NoPush' }
                $salida = & powershell @a 2>&1
                foreach ($l in $salida) { Say "  $l" }
            } catch { Say "  el mantenimiento fallo: $($_.Exception.Message)" }
        }

        $appAntes = $app
    }
    catch { Say "error en el ciclo: $($_.Exception.Message)" }

    Start-Sleep -Seconds $IntervaloSegundos
}

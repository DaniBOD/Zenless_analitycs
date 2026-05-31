# ============================================================================
# install_python_paddle.ps1
# ----------------------------------------------------------------------------
# Migra el proyecto de Windows Store Python -> Python 3.11.9 normal y deja
# PaddleOCR instalado y validado.
#
# Uso:
#   Doble click sobre este archivo en el File Explorer, o desde PowerShell:
#       powershell -ExecutionPolicy Bypass -File .\tools\install_python_paddle.ps1
#
# Lo que hace, en orden:
#   1. Se auto-eleva via UAC (1 prompt) si no esta en admin
#   2. Descarga python-3.11.9-amd64.exe a %TEMP%
#   3. Instala silenciosamente en C:\Python311 con PATH agregado
#   4. Crea D:\Proyectos\Zenless_analitycs\.venv usando C:\Python311\python.exe
#   5. pip install -e ".[dev]" desde pyproject.toml
#   6. pip install paddlepaddle==2.6.2 paddleocr==2.8.1
#   7. Verifica imports de paddle/paddleocr/pytesseract/cv2/PySide6/mss
#   8. Inicializa PaddleOCR (descarga modelos ~50-100MB la primera vez)
#   9. Corre pytest app/tests -x
#  10. Escribe log en tools\install_python_paddle_*.log + status JSON
#
# Si algo falla a mitad de camino, el log dice exactamente donde y por que.
#
# Autor: Claude para DaniBOD ZZZ Analytics
# Fecha: 2026-05-27
# ============================================================================

#Requires -Version 5.0

# ----------------------------------------------------------------------------
# 0. Configuracion
# ----------------------------------------------------------------------------
$ErrorActionPreference = "Continue"  # NO romper a la primera; queremos log completo

$PYTHON_VERSION   = "3.11.9"
$PYTHON_URL       = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-amd64.exe"
$PYTHON_INSTALLER = "$env:TEMP\python-$PYTHON_VERSION-amd64.exe"
$PYTHON_TARGET    = "C:\Python311"
$PYTHON_EXE       = "$PYTHON_TARGET\python.exe"

$PROJECT_ROOT = "D:\Proyectos\Zenless_analitycs"
$VENV_PATH    = "$PROJECT_ROOT\.venv"
$VENV_PYTHON  = "$VENV_PATH\Scripts\python.exe"
$VENV_PIP     = "$VENV_PATH\Scripts\pip.exe"

$TIMESTAMP   = Get-Date -Format "yyyyMMdd_HHmmss"
$LOG_FILE    = "$PROJECT_ROOT\tools\install_python_paddle_$TIMESTAMP.log"
$STATUS_FILE = "$PROJECT_ROOT\tools\install_python_paddle_status.json"

# Si el proyecto no esta donde esperamos, abortar limpio
if (-not (Test-Path $PROJECT_ROOT)) {
    Write-Host "ERROR: no encuentro $PROJECT_ROOT" -ForegroundColor Red
    Write-Host "Editá el script y ajustá `$PROJECT_ROOT al path correcto" -ForegroundColor Yellow
    Read-Host "Presioná Enter para salir"
    exit 1
}

# Asegurar que la carpeta tools/ existe (deberia, pero por las dudas)
if (-not (Test-Path "$PROJECT_ROOT\tools")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\tools" -Force | Out-Null
}

# ----------------------------------------------------------------------------
# 1. Self-elevation a admin
# ----------------------------------------------------------------------------
function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  install_python_paddle.ps1 -- necesita permisos de administrador" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Estoy por re-abrir este script con elevation. Vas a ver un prompt UAC."
    Write-Host "Cuando aparezca 'Quieres permitir que esta app haga cambios?' apretá SI."
    Write-Host ""
    Write-Host "Si lo cancelas, el script se aborta sin tocar nada de tu sistema."
    Write-Host ""

    try {
        Start-Process -FilePath "powershell.exe" `
                      -Verb RunAs `
                      -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
    } catch {
        Write-Host "Cancelado por el usuario o fallo UAC: $_" -ForegroundColor Red
        Read-Host "Presioná Enter para salir"
    }
    exit
}

# ----------------------------------------------------------------------------
# 2. Logging
# ----------------------------------------------------------------------------
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO","WARN","ERROR","OK","STEP")]
        [string]$Level = "INFO"
    )
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] [$Level] $Message"

    # Color por nivel en consola
    switch ($Level) {
        "ERROR" { Write-Host $line -ForegroundColor Red }
        "WARN"  { Write-Host $line -ForegroundColor Yellow }
        "OK"    { Write-Host $line -ForegroundColor Green }
        "STEP"  { Write-Host $line -ForegroundColor Cyan }
        default { Write-Host $line }
    }

    # Persistir a log
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Log "" "STEP"
    Write-Log ("=" * 70) "STEP"
    Write-Log "PASO: $Title" "STEP"
    Write-Log ("=" * 70) "STEP"
    try {
        & $Action
        return $true
    } catch {
        Write-Log "Excepcion en paso '$Title': $($_.Exception.Message)" "ERROR"
        Write-Log "Stack: $($_.ScriptStackTrace)" "ERROR"
        return $false
    }
}

# Estado a volcar a JSON al final
$status = [ordered]@{
    started_at         = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    log_file           = $LOG_FILE
    python_already     = $false
    python_installed   = $false
    python_version     = $null
    venv_created       = $false
    venv_existed       = $false
    deps_installed     = $false
    paddle_installed   = $false
    paddleocr_version  = $null
    paddlepaddle_version = $null
    paddle_init_ok     = $false
    pytest_ran         = $false
    pytest_passed      = $null
    pytest_failed      = $null
    pytest_skipped     = $null
    errors             = @()
    completed_at       = $null
    overall_ok         = $false
}

function Add-Error([string]$msg) {
    $status.errors += $msg
    Write-Log $msg "ERROR"
}

Write-Log "Arrancando instalacion. Log: $LOG_FILE"

# ----------------------------------------------------------------------------
# 3. Verificar si Python 3.11.9 ya esta instalado
# ----------------------------------------------------------------------------
$pythonAlreadyOk = $false

Invoke-Step "Verificar si C:\Python311\python.exe ya existe" {
    if (Test-Path $PYTHON_EXE) {
        Write-Log "$PYTHON_EXE encontrado. Verificando version..." "INFO"
        $verOutput = & $PYTHON_EXE --version 2>&1
        Write-Log "Output: $verOutput" "INFO"
        if ($verOutput -match "3\.11\.\d+") {
            Write-Log "Python 3.11.x ya esta instalado. Skipping install." "OK"
            $script:pythonAlreadyOk = $true
            $status.python_already = $true
            $status.python_version = ($verOutput -replace "Python ","").Trim()
        } else {
            Write-Log "Existe el dir pero no es 3.11.x. Reinstalando..." "WARN"
        }
    } else {
        Write-Log "$PYTHON_EXE no existe. Procederemos a instalar." "INFO"
    }
} | Out-Null

# ----------------------------------------------------------------------------
# 4. Descargar instalador (si hace falta)
# ----------------------------------------------------------------------------
if (-not $pythonAlreadyOk) {

    Invoke-Step "Descargar python-$PYTHON_VERSION-amd64.exe" {
        if (Test-Path $PYTHON_INSTALLER) {
            $sizeMB = [math]::Round((Get-Item $PYTHON_INSTALLER).Length / 1MB, 1)
            Write-Log "Instalador ya esta en $PYTHON_INSTALLER ($sizeMB MB). Skipping download." "OK"
            return
        }
        Write-Log "Bajando $PYTHON_URL ..."
        Write-Log "Destino: $PYTHON_INSTALLER"
        # TLS 1.2 explicito por si hay sistema viejo
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        try {
            $ProgressPreference = 'SilentlyContinue'  # acelera Invoke-WebRequest
            Invoke-WebRequest -Uri $PYTHON_URL -OutFile $PYTHON_INSTALLER -UseBasicParsing
            $sizeMB = [math]::Round((Get-Item $PYTHON_INSTALLER).Length / 1MB, 1)
            Write-Log "Descarga OK ($sizeMB MB)" "OK"
        } catch {
            Add-Error "Fallo descarga: $($_.Exception.Message)"
            throw
        }
    } | Out-Null

    # ----------------------------------------------------------------------------
    # 5. Instalar Python silenciosamente (si descarga OK)
    # ----------------------------------------------------------------------------
    if ($status.errors.Count -eq 0) {
    Invoke-Step "Instalar Python en $PYTHON_TARGET (silent)" {
        Write-Log "Ejecutando: $PYTHON_INSTALLER /quiet ..."
        $args = @(
            "/quiet",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_test=0",
            "Include_doc=0",
            "Include_dev=1",
            "Include_pip=1",
            "Include_launcher=1",
            "TargetDir=$PYTHON_TARGET"
        )
        $proc = Start-Process -FilePath $PYTHON_INSTALLER -ArgumentList $args -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            Add-Error "Instalador devolvio ExitCode $($proc.ExitCode)"
            throw "Install failed"
        }
        Write-Log "Instalador termino. Verificando $PYTHON_EXE..." "INFO"
        if (-not (Test-Path $PYTHON_EXE)) {
            Add-Error "$PYTHON_EXE no existe despues del install"
            throw "Install failed"
        }
        $verOutput = & $PYTHON_EXE --version 2>&1
        Write-Log "Version instalada: $verOutput" "OK"
        $status.python_installed = $true
        $status.python_version = ($verOutput -replace "Python ","").Trim()
    } | Out-Null
    }  # cierre del if-no-errors paso 5
}

# ----------------------------------------------------------------------------
# 6. Crear venv en proyecto
# ----------------------------------------------------------------------------
Invoke-Step "Crear venv en $VENV_PATH" {
    if (Test-Path $VENV_PYTHON) {
        # Verificar que el venv apunte al Python correcto
        $existingVer = & $VENV_PYTHON --version 2>&1
        Write-Log "Venv ya existe ($existingVer). Reusando." "OK"
        $status.venv_existed = $true
        return
    }
    if (Test-Path $VENV_PATH) {
        Write-Log "Carpeta .venv existe pero sin python.exe valido. Borrando para recrear..." "WARN"
        Remove-Item -Path $VENV_PATH -Recurse -Force
    }
    Write-Log "Creando venv con $PYTHON_EXE..."
    & $PYTHON_EXE -m venv $VENV_PATH 2>&1 | ForEach-Object { Write-Log $_ }
    if (-not (Test-Path $VENV_PYTHON)) {
        Add-Error "Venv no se creo correctamente"
        throw "Venv create failed"
    }
    $venvVer = & $VENV_PYTHON --version 2>&1
    Write-Log "Venv listo: $venvVer" "OK"
    $status.venv_created = $true
} | Out-Null

if ($status.errors.Count -gt 0) {
    Write-Log "Saltando pasos posteriores por errores previos" "WARN"
} else {

    # ----------------------------------------------------------------------------
    # 7. Actualizar pip
    # ----------------------------------------------------------------------------
    Invoke-Step "Actualizar pip" {
        & $VENV_PYTHON -m pip install --upgrade pip 2>&1 | ForEach-Object { Write-Log $_ }
        if ($LASTEXITCODE -ne 0) { Add-Error "pip upgrade fallo"; throw }
    } | Out-Null

    # ----------------------------------------------------------------------------
    # 8. Instalar deps del proyecto (-e .[dev])
    # ----------------------------------------------------------------------------
    Invoke-Step "Instalar deps del proyecto (pip install -e .[dev])" {
        Push-Location $PROJECT_ROOT
        try {
            & $VENV_PIP install -e ".[dev]" 2>&1 | ForEach-Object { Write-Log $_ }
            if ($LASTEXITCODE -ne 0) { Add-Error "pip install -e .[dev] fallo"; throw }
            $status.deps_installed = $true
            Write-Log "Deps del pyproject instaladas OK" "OK"
        } finally {
            Pop-Location
        }
    } | Out-Null

    # ----------------------------------------------------------------------------
    # 9. Instalar PaddleOCR + PaddlePaddle (versiones validadas)
    # ----------------------------------------------------------------------------
    Invoke-Step "Instalar paddlepaddle==2.6.2 + paddleocr==2.8.1" {
        & $VENV_PIP install "paddlepaddle==2.6.2" "paddleocr==2.8.1" 2>&1 | ForEach-Object { Write-Log $_ }
        if ($LASTEXITCODE -ne 0) {
            Add-Error "pip install paddle fallo (probablemente OneDNN o MAX_PATH)"
            throw "Paddle install failed"
        }
        $status.paddle_installed = $true
        Write-Log "Paddle instalado OK" "OK"
    } | Out-Null

    # ----------------------------------------------------------------------------
    # 10. Verificar imports
    # ----------------------------------------------------------------------------
    Invoke-Step "Verificar imports basicos" {
        $checks = @(
            @{ name="paddleocr"; cmd="import paddleocr; print(paddleocr.__version__)" },
            @{ name="paddle";    cmd="import paddle; print(paddle.__version__)" },
            @{ name="cv2";       cmd="import cv2; print(cv2.__version__)" },
            @{ name="pytesseract"; cmd="import pytesseract; print(pytesseract.__version__)" },
            @{ name="mss";       cmd="import mss; print(mss.__version__)" },
            @{ name="PySide6";   cmd="import PySide6; print(PySide6.__version__)" }
        )
        foreach ($c in $checks) {
            $out = & $VENV_PYTHON -c $c.cmd 2>&1
            $ok = ($LASTEXITCODE -eq 0)
            if ($ok) {
                Write-Log "$($c.name) import OK: $out" "OK"
                if ($c.name -eq "paddleocr") { $status.paddleocr_version = "$out".Trim() }
                if ($c.name -eq "paddle")    { $status.paddlepaddle_version = "$out".Trim() }
            } else {
                Add-Error "$($c.name) import FALLO: $out"
            }
        }
    } | Out-Null

    # ----------------------------------------------------------------------------
    # 11. Inicializar PaddleOCR (baja modelos)
    # ----------------------------------------------------------------------------
    if ($status.errors.Count -eq 0) {
        Invoke-Step "Inicializar PaddleOCR (descarga modelos ~50-100MB)" {
            Write-Log "Esto puede tardar 1-3 min segun tu conexion..." "INFO"
            $initCmd = "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='es', use_textline_orientation=False); print('PaddleOCR init OK')"
            $out = & $VENV_PYTHON -c $initCmd 2>&1
            if ($LASTEXITCODE -eq 0 -and $out -match "PaddleOCR init OK") {
                Write-Log "PaddleOCR inicializado correctamente" "OK"
                $status.paddle_init_ok = $true
            } else {
                Add-Error "PaddleOCR init fallo. Output: $out"
            }
        } | Out-Null
    }

    # ----------------------------------------------------------------------------
    # 12. Correr pytest del proyecto
    # ----------------------------------------------------------------------------
    Invoke-Step "Correr pytest app/tests" {
        Push-Location $PROJECT_ROOT
        try {
            $pytestOut = & $VENV_PYTHON -m pytest "app/tests" "--tb=short" "-q" 2>&1
            $pytestOut | ForEach-Object { Write-Log $_ }
            $status.pytest_ran = $true

            # Parsear resumen "N passed, M failed, K skipped"
            $summary = ($pytestOut | Out-String)
            if ($summary -match "(\d+)\s+passed")  { $status.pytest_passed = [int]$matches[1] }
            if ($summary -match "(\d+)\s+failed")  { $status.pytest_failed = [int]$matches[1] }
            if ($summary -match "(\d+)\s+skipped") { $status.pytest_skipped = [int]$matches[1] }

            Write-Log "pytest summary: passed=$($status.pytest_passed) failed=$($status.pytest_failed) skipped=$($status.pytest_skipped)" "INFO"
        } finally {
            Pop-Location
        }
    } | Out-Null
}

# ----------------------------------------------------------------------------
# cleanup: volcar status JSON + mensaje final
# ----------------------------------------------------------------------------
:cleanup
$status.completed_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
$status.overall_ok = ($status.errors.Count -eq 0)

# Serializar JSON
$status | ConvertTo-Json -Depth 4 | Set-Content -Path $STATUS_FILE -Encoding UTF8

Write-Log "" "STEP"
Write-Log ("=" * 70) "STEP"
if ($status.overall_ok) {
    Write-Log "INSTALACION COMPLETA OK" "OK"
} else {
    Write-Log "INSTALACION TERMINO CON ERRORES ($($status.errors.Count))" "ERROR"
    foreach ($e in $status.errors) {
        Write-Log "  - $e" "ERROR"
    }
}
Write-Log ("=" * 70) "STEP"
Write-Log "Log completo: $LOG_FILE"
Write-Log "Status JSON:  $STATUS_FILE"
Write-Log ""
Write-Log "Reportale a Claude el contenido de install_python_paddle_status.json"
Write-Log "(esta en D:\Proyectos\Zenless_analitycs\tools\)"
Write-Log ""

Read-Host "Presioná Enter para cerrar la ventana"

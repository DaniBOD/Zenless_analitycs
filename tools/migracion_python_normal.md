# Migración de Windows Store Python → Python normal de python.org

> **Fecha:** 2026-05-27
> **Motivo:** Windows Store Python rompe PaddleOCR (MAX_PATH + sandboxing impide extraer DLLs nativas en `paddle/libs/`). Necesario para desbloquear Hito 2.9 (refuerzo OCR).
> **Tiempo estimado:** 30-45 min
> **Reversibilidad:** Alta. Si algo falla, podés volver al Python de Store sin perder el proyecto.

---

## 0. Pre-flight — guardar estado actual

```powershell
cd D:\Proyectos\Zenless_analitycs

# Confirmar que no hay cambios sin commitear
git status

# Si hay cambios pendientes, commitear o stashear
# git add -A; git commit -m "wip: guardar antes de migracion python"

# Snapshot de paquetes instalados en Windows Store Python (por si necesitamos referencia)
python -m pip freeze > tools\pip_snapshot_winstore_$(Get-Date -Format "yyyyMMdd").txt

# Anotar versión actual
python --version > tools\python_version_pre.txt
```

---

## 1. Descargar e instalar Python 3.11.9 de python.org

### 1.1 Descargar

Abrí esta URL en el browser:
**https://www.python.org/downloads/release/python-3119/**

Bajá hasta la sección "Files" al final de la página. Descargá:

> **Windows installer (64-bit)** — archivo `python-3.11.9-amd64.exe` (~28 MB)

> ¿Por qué 3.11.9 y no 3.12+? Porque el `pyproject.toml` declara `requires-python = ">=3.11"` y PaddlePaddle 2.6.2 está validado contra 3.11. PaddlePaddle 3.x sí soporta 3.12 pero introduce el problema OneDNN que el dev encontró.

### 1.2 Ejecutar el instalador

Doble click en `python-3.11.9-amd64.exe`.

**En la primera pantalla:**

- ✅ **Use admin privileges when installing py.exe** (recomendado)
- ✅ **Add python.exe to PATH** ← CRÍTICO, no olvidarse
- Click **Customize installation** (NO "Install Now")

**Pantalla "Optional Features":** dejá todo tildado (pip, tcl/tk, py launcher, test suite). Click **Next**.

**Pantalla "Advanced Options":**

- ✅ Install Python 3.11 for all users
- ✅ Associate files with Python
- ✅ Create shortcuts for installed applications
- ✅ Add Python to environment variables
- ✅ Precompile standard library
- **Customize install location:** `C:\Python311\` ← PATH CORTO, no usar el default que es muy largo

Click **Install**. Tarda ~2-3 min.

Al terminar, si te ofrece "Disable path length limit" → click sí (es la cereza, sube MAX_PATH a 32K).

### 1.3 Verificar instalación

**Cerrá TODOS los terminales abiertos** (PowerShell, CMD, VS Code, etc.). Esto es importante porque el PATH solo se refresca en sesiones nuevas.

Abrí PowerShell nuevo y corré:

```powershell
where.exe python
python --version
```

Salida esperada:

```
C:\Python311\python.exe
C:\Users\danie\AppData\Local\Microsoft\WindowsApps\python.exe   ← Windows Store, queda atrás
Python 3.11.9
```

Si `where.exe python` muestra **PRIMERO** el de WindowsApps, hay que desactivar los App Execution Aliases (paso 1.4). Si muestra primero `C:\Python311\python.exe`, **saltá al paso 2**.

### 1.4 (Solo si hace falta) Desactivar App Execution Aliases

Windows tiene "alias" que redirigen `python` al de Store aunque tengas otro instalado.

- Windows + I → **Apps** → **Advanced app settings** → **App execution aliases**
- O directo: ejecutá `ms-settings:advanced-apps` desde Win+R
- Buscá las entradas:
  - **Python (App Installer) — python.exe** → OFF
  - **Python (App Installer) — python3.exe** → OFF
  - **Python (App Installer) — python3.11.exe** → OFF (si aparece)

Después cerrá terminal y abrí uno nuevo. Re-verificá:

```powershell
where.exe python
python --version
```

Ahora debería mostrar solo `C:\Python311\python.exe`.

---

## 2. Crear entorno virtual para el proyecto

Esto AISLA las dependencias del proyecto del Python del sistema. Es la práctica estándar y previene conflictos.

```powershell
cd D:\Proyectos\Zenless_analitycs

# Crear venv usando explícitamente el Python nuevo
C:\Python311\python.exe -m venv .venv

# Activar
.\.venv\Scripts\Activate.ps1
```

Si PowerShell se queja de execution policy, corré una vez:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
y reintentá la activación.

**Verificar venv activo:**

```powershell
python --version        # Python 3.11.9
where.exe python        # D:\Proyectos\Zenless_analitycs\.venv\Scripts\python.exe
```

El prompt de PowerShell ahora debería tener `(.venv)` al principio.

> **Importante:** cada vez que abras terminal nuevo para trabajar en el proyecto, **activá el venv** con `.\.venv\Scripts\Activate.ps1`. Si vés que el prompt no dice `(.venv)`, no está activado.

---

## 3. Instalar dependencias del proyecto

### 3.1 Actualizar pip primero

```powershell
python -m pip install --upgrade pip
```

### 3.2 Instalar deps del proyecto

```powershell
# Editable install — usa pyproject.toml
pip install -e ".[dev]"
```

Esto instala todo lo declarado en `pyproject.toml`: PySide6, mss, opencv-python, pytesseract, pynput, pywin32, anthropic, pytest, ruff, mypy.

Tarda ~3-5 min (PySide6 pesa 200 MB).

### 3.3 Instalar PaddleOCR (versiones validadas)

```powershell
pip install paddlepaddle==2.6.2 paddleocr==2.8.2
```

Tarda ~2-3 min. Bajan ~500 MB combinado (paddlepaddle es grande).

### 3.4 Instalar PyInstaller (para build .exe)

```powershell
pip install pyinstaller
```

---

## 4. Verificar que todo funciona

### 4.1 Imports básicos

```powershell
python -c "import paddleocr; print('paddleocr:', paddleocr.__version__)"
python -c "import paddle; print('paddlepaddle:', paddle.__version__)"
python -c "import cv2; print('cv2:', cv2.__version__)"
python -c "import PySide6; print('PySide6:', PySide6.__version__)"
python -c "import mss; print('mss:', mss.__version__)"
```

Esperado: todas las versiones imprimen sin errores.

### 4.2 Inicializar PaddleOCR (descarga modelos)

```powershell
python -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='es', use_textline_orientation=False); print('PaddleOCR init OK')"
```

**Primera ejecución:** descarga ~50-100 MB de modelos a `~/.paddleocr/`. Toma 1-3 min según conexión.

**Salida esperada al final:** `PaddleOCR init OK`. Si tira error de OneDNN o `fused_conv2d` → reportarme exactamente qué dice.

### 4.3 Correr suite de tests del proyecto

```powershell
pytest app/tests -x --tb=short
```

**Esperado:**
- ~188 tests passed
- 7 tests `test_extracts_all_11_stats[1-7]` que antes estaban skipped por PaddleOCR ahora deberían ejecutarse y pasar
- ~7 tests `test_extracts_some_stats_with_tesseract[1-7]` siguen skipped si tu Tesseract binario no está en PATH (no es problema, ya andaba)

### 4.4 Build del .exe (opcional, solo si tocaste algo de la app)

```powershell
# Si tu shortcut o tools/ tiene el comando exacto, usalo
# Sino, build genérico:
pyinstaller --clean app/build/danibod_zzz_analytics.spec
```

---

## 5. Actualizar herramientas del proyecto

### 5.1 Verificar `tools/run_debug.ps1`

Abrí el archivo y revisá si tiene path hardcodeado a Python o al .exe. Si está apuntando al .exe en `app/build/dist/...`, eso sigue OK. Si tiene un `python.exe` explícito, actualizalo al venv.

### 5.2 VS Code (si lo usás)

`Ctrl+Shift+P` → **Python: Select Interpreter** → elegí `D:\Proyectos\Zenless_analitycs\.venv\Scripts\python.exe`.

Esto hace que el linter, debugger, IntelliSense, todo use el venv.

### 5.3 Commit del estado

```powershell
git add tools\migracion_python_normal.md
# .venv/ debería estar en .gitignore — verificar
echo ".venv/" >> .gitignore  # solo si no estaba ya
git add .gitignore
git commit -m "chore: migrar a Python 3.11.9 normal + venv para PaddleOCR

- Documentar proceso en tools/migracion_python_normal.md
- Desbloquea PaddleOCR 2.6.2 + 2.8.2 sin workaround D:\\paddle_site
- Resuelve OneDNN incompatibility del dev log 2026-05-13
- Requisito para Hito 2.9 (refuerzo OCR)"
git push origin HEAD:main
```

---

## 6. Limpieza opcional (después de validar 1-2 días)

Una vez que confirmes que todo anda con el Python normal:

### 6.1 Desinstalar Windows Store Python

Si lo querés (no es obligatorio):
- Win + I → Apps → Installed apps → Python 3.11 → Uninstall

Esto libera ~150 MB y elimina la fuente de confusión PATH.

### 6.2 Limpiar el workaround `D:\paddle_site`

Si existe la carpeta:

```powershell
Remove-Item -Path D:\paddle_site -Recurse -Force
```

El módulo `app/core/ocr_paddle.py` tiene un `_ensure_paddle_site()` que la usa como fallback. Ya no es necesario, pero el código sigue siendo seguro: solo agrega al sys.path si el directorio existe.

### 6.3 Opcional: simplificar `ocr_paddle.py`

Si querés limpiar el workaround del código:

```python
# Eliminar líneas 17-36 (_PADDLE_SITE y _ensure_paddle_site)
# Eliminar llamada en línea 36 y dentro de _get_ocr
```

Pero conservar el código no rompe nada. Decisión cosmética para más adelante.

---

## 7. Troubleshooting

### Error: "Microsoft Visual C++ 14.0 or greater is required"

Algún paquete (rara vez con estas versiones) necesita compilar C extension. Instalá:
**https://visualstudio.microsoft.com/visual-cpp-build-tools/** — "Build Tools for Visual Studio 2022"

Tildá "Desktop development with C++". Reintentá `pip install`.

### Error: paddleocr import: "fused_conv2d not supported by OneDNN"

Esto es lo que pasó al dev. Solución: bajar versiones:

```powershell
pip uninstall -y paddlepaddle paddleocr
pip install paddlepaddle==2.6.2 paddleocr==2.8.2 --no-cache-dir
```

Si ya las tenés y aún falla, podés probar:

```powershell
pip install paddlepaddle==2.5.2 paddleocr==2.7.0.3 --no-cache-dir
```

### Error: PaddleOCR init: timeout descargando modelos

Si tu conexión es lenta o hay firewall corporativo: bajá los modelos manualmente desde **https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_en/models_list_en.md** y descomprimí en `~\.paddleocr\whl\det\es\` y `~\.paddleocr\whl\rec\es\`.

### El terminal sigue agarrando el Python de Store

1. ¿Cerraste y reabriste el terminal después de instalar?
2. ¿Activaste el venv? Si sí, debería mandar el del venv sí o sí.
3. ¿`where.exe python` muestra el de Store primero? → desactivar App Execution Aliases (paso 1.4).

### pip install falla con "WinError 5: Access denied"

Estás corriendo sin venv y pip está intentando escribir a `C:\Python311\Lib\site-packages` que requiere admin. **Soluciones:**

- Activá el venv (`.\.venv\Scripts\Activate.ps1`) y reintentá.
- O agregá `--user` al pip install (pero el venv es mejor).

### El .exe que rebuildié anda raro con Paddle

Es normal — `pyinstaller` necesita aprender a empaquetar los modelos de PaddleOCR. Es trabajo adicional para más adelante (parte de Hito 2.10 si tocara).

---

## 8. Después de cerrar la migración

Reportame:

1. Versión final de Python (`python --version` con venv activado)
2. Versión final de paddleocr y paddlepaddle (paso 4.1)
3. Resultado de `pytest app/tests -x` (cantidad de passed/failed/skipped)

Con eso, empezamos a planear el Hito 2.9 (refuerzo OCR) con base sólida.

---

*Doc generado 2026-05-27 como parte de investigación pre-Hito 2.9. Mover a `audit/` o eliminar después de cerrar la migración.*

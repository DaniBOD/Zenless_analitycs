# Guía QA — Domingo 2026-05-10

> **Objetivo:** validar end-to-end el motor de captura RF-04 (estado, ROIs, OCR, parser, recommender, toast) con el juego abierto en vivo.
>
> **Tiempo estimado:** 45-60 min · **Prerequisito:** Tesseract instalado (~3 min) + juego ZZZ abierto en modo ventana 16:9.

---

## 0. Pre-flight — instalación de Tesseract (3 min, hacer ANTES)

El binario de Tesseract OCR no viene con el `.exe`; hay que instalarlo aparte.

```powershell
# 1. Instalar Tesseract
winget install UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements

# 2. Agregar al PATH (sólo si el installer no lo hizo automáticamente)
$env:PATH += ";C:\Program Files\Tesseract-OCR"

# 3. Descargar pack español (si no viene incluido)
$tessdata = "C:\Program Files\Tesseract-OCR\tessdata"
Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata" `
                  -OutFile "$tessdata\spa.traineddata"

# 4. Verificar
tesseract --version
tesseract --list-langs    # debe incluir "spa"
```

**Si falla la instalación:** el controller emite el mensaje de error en el log del panel Live. La app sigue siendo usable para ver el roster y discos persistidos, sólo no captura en vivo.

---

## 1. Smoke tests OFFLINE (10 min) — sin el juego abierto

Estos validan que el pipeline mecánico funciona sin depender del cliente del juego.

### 1.1 Tests unitarios
```powershell
python -m pytest app\tests -q
```
**Pass:** 42 tests pasan (incluye 5 nuevos de mapping de ROIs por estado).
**Fail:** ver output de pytest. No avanzar a 1.2 si hay fallas aquí.

### 1.2 Anotación visual de ROIs
```powershell
python tools\annotate_rois.py
```
Genera imágenes en `Documentacion\QA\calibracion_visual\<S3|S6|S7|S8|S10>\`.

**Criterio:** abrir 1-2 imágenes de cada estado y verificar visualmente:
- ✅ S3: cuadros sobre título, nivel, mainstat (PV/550), substats grilla 2×2.
- ✅ S6: cuadros sobre título grande izq, nivel arriba-der, mainstat, substats.
- ✅ S7: idem S6 (vista tienda música fullscreen).
- ✅ S10: cuadros sobre mainstat + substats + 3 chips EXP + botón "Mejorar".

**Si una caja cae en zona vacía:** anotar en log y ajustar `app/config/rois.toml`.

### 1.3 Pipeline E2E sobre screenshots reales (requiere Tesseract)
```powershell
python tools\run_pipeline_on_screenshots.py
```
Genera `audit\calibracion_<TIMESTAMP>.md` con detalle por imagen.

**Criterio mínimo aceptable:**
| Estado | Confianza promedio | Slot detectado | Mainstat canónico |
|--------|--------------------|----------------|---------------------|
| S3     | ≥ 0.70             | ≥ 75%          | ≥ 75%               |
| S6     | ≥ 0.70             | ≥ 75%          | ≥ 75%               |
| S10    | ≥ 0.65             | n/a            | ≥ 70%               |

Si la confianza baja de eso, hay un ajuste de ROIs pendiente o el OCR necesita mejor preprocesado.

### 1.4 Render preview del toast (validar UI)
```powershell
python tools\render_toast_preview.py
```
Genera `Documentacion\QA\calibracion_visual\toast_previews\toast_<variant>.png`.

**Criterio:** los 4 PNG existen y se ve correctamente:
- Border + glow del color del variant.
- Chevron + label legible ("EQUIPAR" / "MEJORAR" / etc).
- Thumbnail con set logo (o hexágono fallback) + rarity badge.
- Score grande en color del variant.
- Urgency bar abajo.

---

## 2. Smoke test del `.exe` (5 min) — sin juego

### 2.1 Lanzar desde shortcut
- Doble-click en el shortcut `DaniBOD ZZZ Analytics` del escritorio.

**Pass:**
- Aparece ícono en system tray.
- La ventana principal se muestra (1320×820, paleta oscura).
- Tab "Estado" muestra counts reales de la DB (46 agentes, 334 discos, 50 armas, etc).
- Tab "Live" se ve con botones "Iniciar captura", "Pausa (F10)", "Probar captura (F8)".
- Tab "Discos" carga la grilla con scores.
- Tab "Roster" carga los 46 agentes.

**Fail común:** no carga la DB. Verificar que la app encuentra `db\danibod_zzz_v2.db` (el `.exe` lo busca en `_internal\db\` dentro del onedir).

### 2.2 Iniciar captura sin juego
- En tab "Live", click "Iniciar captura".

**Pass esperado SIN juego abierto:**
- El log dice `[monitor] Capturando. F8 fuerza scan · F10 pausa.`
- El indicador del header pasa a `● Monitor: ON` verde.
- El state pill no aparece (porque no hay ventana ZZZ que clasificar).

**Pass alternativo si Tesseract NO está instalado:**
- El log muestra: `Tesseract OCR no esta instalado. Ejecutar: winget install UB-Mannheim.TesseractOCR`
- El botón "Iniciar captura" no cambia de estado (no arranca el monitor).

---

## 3. Test LIVE con el juego abierto (30 min) — el escenario real

Pre-requisito: ZZZ abierto en modo ventana 16:9, resolución cualquiera (1920×1080 o 2560×1440 verificadas).

### 3.1 Detección de pantalla (5 min)
1. Lanzar el `.exe`, ir a tab "Live", click "Iniciar captura".
2. Cambiar entre las siguientes pantallas del juego y observar el **state pill** en el panel Live:

| Pantalla del juego                          | State esperado | Acción del monitor    |
|---------------------------------------------|----------------|-----------------------|
| Patrulla / menú principal                   | S1 / S12       | Idle (polling 4s)     |
| Resultado del desafío                       | S2             | Pre-captura (1s)      |
| **Modal detalle drop (clickeas un drop)**   | **S3**         | **Captura disco**     |
| Vista agente (slots equipados)              | S8             | Idle (polling 2s)     |
| Inventario discos                           | S9             | Idle (polling 2s)     |
| **Tienda Música (panel detalle)**           | **S6**         | **Captura disco**     |
| **Tienda Música (fullscreen detalle)**      | **S7**         | **Captura disco**     |
| **Modal upgrade (botón "Mejorar")**         | **S10**        | **Pre/POST sync**     |
| Pantalla desmontaje                         | S11            | Idle (polling 5s)     |

**Pass:** el state pill cambia correctamente al pasar entre pantallas. La confianza del template debe ser ≥ 0.85.

### 3.2 Captura de disco en S3 (modal drop) — escenario canónico
1. Terminar una actividad de farmeo (Shiyu, DA, Hollow, lo que sea).
2. En la pantalla de Resultado del Desafío, clickear sobre un disco dropeado.
3. Esperar que el modal se estabilice (medio segundo).

**Pass esperado:**
- Log muestra: `[disco] <set> slot <N> → <recomendación> <score> (→ <agente>)`
- Card "último disco" se actualiza con el set, slot, mainstat, target, score.
- **Toast aparece** en bottom-right de la pantalla con la card de recomendación.
- Latencia entre que aparece el modal y el toast: **< 1 segundo**.

**Fail:**
- Toast nunca aparece → revisar log del panel Live, debería haber un `[error]` o un `[disco] ... confianza X.XX` con X < 0.70.
- Toast aparece pero recomendación dice "—" / score 0 → el set no se reconoció, OCR puede haber fallado el título.

### 3.3 Captura desde Tienda Música (S6/S7) — escenario crítico
1. Ir a Tienda Música → seleccionar un disco del inventario.
2. Verificar que aparece el panel detalle (S6) o fullscreen (S7).

**Pass:** mismo flujo que 3.2 (log + card + toast).

**Importante:** S6 y S7 fueron calibrados con menos screenshots que S3. Si el OCR falla aquí pero funciona en S3, anotar y ajustar `modal_detalle_s6` en `rois.toml`.

### 3.4 Upgrade flow (S10 PRE → POST)
1. En tu inventario, seleccionar un disco para mejorar.
2. Modal de upgrade aparece (S10 PRE).
3. Confirmar upgrade (gastar materiales).
4. Animación de upgrade.
5. Estado POST con valores actualizados.

**Pass esperado:**
- Log muestra entrada a S10 + salida (mensajes del UpgradeSyncer).
- El disco se actualiza en `inventory_discs` (verificar con `python tools\quick_score_sample.py`).

### 3.5 Hotkeys globales
Con el juego al frente, presionar:
- **F8** → fuerza scan inmediato. Log debe mostrar nueva entrada de captura si hay disco en pantalla.
- **F10** → pausa/reanuda. Indicador header pasa a "PAUSADO" amarillo.

### 3.6 Toast interactivo
1. Hover sobre el toast cuando aparezca.
**Pass:** countdown pausa, label "PAUSE" amarillo, opacity sube a 100%.
2. Click sobre el toast.
**Pass:** toast desaparece (TODO: en versión completa abriría el panel — actualmente solo se cierra).

---

## 4. Criterios pass/fail globales

| Criterio                                    | Severidad | Mínimo para QA pass |
|---------------------------------------------|-----------|---------------------|
| `.exe` arranca sin crash                    | crítico   | ✅ obligatorio       |
| DB carga + tab Estado muestra counts        | crítico   | ✅ obligatorio       |
| Detector clasifica S3/S6/S7/S10 correctamente | crítico | ✅ obligatorio       |
| Toast aparece en < 1s tras captura S3       | alta      | ✅ obligatorio       |
| Toast aparece en < 1s tras captura S6       | alta      | aceptable degradado |
| OCR confianza promedio ≥ 0.70 en S3         | alta      | ✅ obligatorio       |
| Recommendation devuelve agente top válido   | alta      | ✅ obligatorio       |
| Upgrade S10 sincroniza valores en DB        | media     | aceptable diferido  |
| Hotkeys F8/F10 funcionan globalmente        | media     | aceptable diferido  |
| Sin memory leak tras 30 min idle            | baja      | informativo         |

---

## 5. Issues conocidos pre-QA

- ⚠️  Label del toast (EQUIPAR/MEJORAR/etc) puede aparecer visualmente solapado con el chevron de color en algunos sistemas. No es funcional, solo estético.
- ⚠️  Subwidget DiscThumb usa hexágono fallback porque aún no cargamos `set_logo` real desde `Documentacion\Interfaz\Sets_Logos\`. Implementar en Hito 2.7.
- ⚠️  El avatar del target agent no se renderiza (target_avatar=None). Implementar en Hito 2.7.
- ⚠️  Tras click en el toast, no abre el panel principal. Solo se cierra. Implementar wiring `clicked → mainwindow.show()` en Hito 2.7.
- ℹ️  Si el shortcut del escritorio queda roto: el `.exe` está en `app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe` (relativo al repo). Re-ejecutar `tools\create_shortcut.ps1`.

---

## 6. Si algo falla — diagnóstico rápido

```powershell
# Logs Python (correr la app desde terminal, no el .exe)
python -m app.main

# Verificar templates
ls app\resources\templates\
# Deben haber 9 archivos s*.png

# Verificar rois.toml
python -c "import tomllib; print(list(tomllib.load(open('app/config/rois.toml','rb')).keys()))"
# Debe listar: modal_detalle_s3, modal_detalle_s6, modal_detalle_s7, modal_upgrade_s10, ...

# Re-validar ROIs visualmente
python tools\annotate_rois.py

# Re-correr pipeline E2E con OCR
python tools\run_pipeline_on_screenshots.py

# Verificar conexión a DB
python -c "from app.db.connection import get_connection; c=get_connection(); print(c.execute('SELECT COUNT(*) FROM agents').fetchone()[0])"
# Debe imprimir 46
```

---

*Guía generada antes del QA del 2026-05-10. Después del QA, actualizar `project-context-IA.md` §4 con los RF que cierran y abrir Hito 2.7 con los issues conocidos diferidos.*

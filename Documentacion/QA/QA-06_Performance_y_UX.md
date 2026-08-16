# QA-06 — Performance y UX (RF-11 + transversal)

**Capa:** L2 (medición instrumentada) + L4 (percibida por Daniel jugando).
**RFs cubiertos:** RF-11 (UI standalone `.exe`) + presupuestos transversales de RNF-06.
**Cuándo consultar:** al implementar cualquier superficie con presupuesto de latencia, al instalar el `.exe` por primera vez, al medir RAM/CPU.

> **Principio rector:** RNF-06 dice que **si la app llega tarde, no tiene valor**. La UX se mide; no se opina. Cualquier superficie sensible debe exponer `latency_p50` y `latency_p99` consultables desde un panel de diagnóstico.

---

## 1. Presupuestos consolidados

Reproducción de la tabla del README §3.2 RNF-06 con la columna "test L2 derivado":

| Superficie | Latencia objetivo | Test |
|-----------|-------------------|------|
| Disco aparece en pantalla → toast visible | < 500 ms | `test_pipeline_full_latency` (§3) |
| Captura → OCR de disco → scoring → render | < 380 ms | `test_pipeline_internal_latency` (§3) |
| Optimizador build (332 discos) | < 500 ms | en QA-02 §3.4 |
| Optimizador build (1500 discos proyectado) | < 1 s | QA-02 §3.4 |
| Lookup runtime RF-12 (`team_synergies` + `team_compositions`) | < 50 ms | `test_team_lookup_latency` |
| Captura + OCR breakdown DMG (RF-13) | < 1.5 s | QA-05 |
| Recálculo full tier list (45 PJs × 3 contenidos) | < 3 s | QA-05 §3.3 |
| Snapshot Prydwen (scrape + parse + insert) | < 5 s background | `test_prydwen_scrape_latency` |
| Snapshot enemies/cycles | < 30 s background | `test_hakush_scrape_latency` |
| Score 1 arma para 1 PJ × 1 contenido (RF-14) | < 5 ms | QA-02 |
| Ranking 49 armas para 1 PJ × 1 contenido | < 100 ms | QA-02 |
| Build full RF-06+RF-14 (3 armas × 3 builds) | < 1.5 s | QA-02 |
| Recálculo full weapon_evaluations (45 × 49 × 4) | < 8 s background | QA-02 |
| Snapshot Prydwen weapons (45 PJs) | < 90 s background | `test_prydwen_weapons_latency` |

**Recursos en idle (RF-11):**
- RAM residente < 200 MB.
- Pico durante OCR < 400 MB.
- CPU polling < 3% single core idle, < 15% pico OCR.
- Arranque frío `.exe` < 2 s (double-click → tray visible).

---

### 1.bis Cómo medir (y con qué reloj) — leer antes de escribir un bench

Los presupuestos de arriba solo significan algo si el instrumento tiene resolución para medirlos.
En Windows **dos de los cuatro relojes de `time` avanzan de a 15.625 ms** (la tick del scheduler):

| reloj | implementación | granularidad REAL | sirve para |
|---|---|---|---|
| `perf_counter` | `QueryPerformanceCounter` | sub-µs | **todo bench**; es el único que usar |
| `thread_time` | `GetThreadTimes` | **15.625 ms** ⚠ | nada de este doc — y encima *declara* `1e-07` |
| `process_time` | `GetProcessTimes` | 15.625 ms | ídem |
| `monotonic` / `time` | `GetTickCount64` / FileTime | 15.625 ms (declarada) | timestamps, cadencias gruesas |

Reglas que salieron de tres flakes seguidos del bench del censo de desmontaje (2026-08-12, historia
completa en el docstring de `test_bench_censo_bajo_3ms` y en `Dev_IA/2026-07-25_IMPL_Bitacora…` §8):

1. **`perf_counter` siempre.** `thread_time` es la trampa: promete `resolution=1e-07` y entrega
   ticks de 15.625 ms, así que un bench de pocos ms devuelve un conteo de ticks disfrazado de
   milisegundos — y llegó a reportar `0.000 ms` para trabajo real.
2. **Mínimo de muchos lotes, y lotes CORTOS.** La contención solo puede sumar tiempo, así que el
   mínimo estima el costo propio; pero para que exista una muestra sin desalojar el lote tiene que
   caber entero en un quantum del scheduler (~15-30 ms). Un lote de ~16 ms casi siempre se come un
   cambio de contexto y ahí el mínimo no salva nada.
3. **Antes de creerle a un número, fijarse si es múltiplo de la granularidad del reloj.**
4. **Si la propiedad es estructural, medirla sin reloj.** "Cuántas llamadas a OpenCV cuesta" es
   determinista y no parpadea con la carga; el cronómetro queda solo para lo que de verdad es tiempo.
5. **Un presupuesto se mide donde el test corre.** El mismo censo cuesta 0.82 ms en un proceso
   limpio y ~1.5 ms dentro de la suite completa (estado de memoria con 357k objetos vivos, no el GC).

**Consecuencia conocida y asumida en el loop de captura:** `monitor.py` usa `time.monotonic()` para
decidir la cadencia de polling, así que toda cadencia se redondea al próximo múltiplo de 15.625 ms —
los 100 ms nominales disparan a ~109 ms (~9.1 fps en vez de 10). Medido el 2026-08-12 y **dejado
así**: el 9 % no justifica tocar el loop caliente. Si alguna cadencia tuviera que ser exacta, el
cambio es el reloj, no las constantes.

---

## 2. Instrumentación obligatoria

### 2.1 Decorator `@measure_latency`
Cada función con presupuesto registrado en §1 lleva el decorator. Implementación:

```python
# app/core/metrics.py
import time, functools
from contextlib import contextmanager
import sqlite3

_BUFFER = []   # in-memory; flush cada 60 s

def measure_latency(superficie):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                dt_ms = (time.perf_counter() - t0) * 1000
                _BUFFER.append({
                    'superficie': superficie,
                    'duration_ms': dt_ms,
                    'ts': time.time()
                })
                if len(_BUFFER) >= 100:
                    _flush()
        return wrapper
    return deco

@contextmanager
def measure_block(superficie):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000
        _BUFFER.append({'superficie': superficie, 'duration_ms': dt_ms,
                        'ts': time.time()})

def _flush():
    if not _BUFFER: return
    con = sqlite3.connect('db/danibod_zzz_v2.db')
    con.executemany(
        "INSERT INTO metrics_latency (superficie, duration_ms, ts) "
        "VALUES (?,?,?)",
        [(m['superficie'], m['duration_ms'], m['ts']) for m in _BUFFER]
    )
    con.commit() ; _BUFFER.clear()
```

### 2.2 Tabla `metrics_latency` (a crear en migración futura)
```sql
CREATE TABLE metrics_latency (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    superficie  TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ts          REAL NOT NULL  -- epoch float
);
CREATE INDEX idx_metrics_superficie_ts ON metrics_latency(superficie, ts);

-- Vista p50/p99 últimos 7 días por superficie
CREATE VIEW v_metrics_latency_7d AS
SELECT
  superficie,
  COUNT(*) AS n,
  ROUND(AVG(duration_ms),1) AS avg_ms,
  ROUND(MIN(duration_ms),1) AS min_ms,
  ROUND(MAX(duration_ms),1) AS max_ms
FROM metrics_latency
WHERE ts >= (strftime('%s','now') - 7*24*3600)
GROUP BY superficie;
```

> SQLite no tiene `PERCENTILE_CONT` nativo; el cálculo p50/p99 se hace en Python, por **rango más
> cercano**:
> ```python
> def percentile(values, p):
>     s = sorted(values)
>     if not s:
>         return None          # "no medí nada" ≠ "medí 0 ms"
>     k = max(0, math.ceil(len(s) * p / 100) - 1)
>     return s[min(k, len(s)-1)]
> ```
>
> ⚠ **Corregido 2026-08-15.** La versión anterior usaba `k = int(len(s) * p / 100)`, que está
> corrida en uno: con 100 muestras daba `k=99` para p99, o sea que **p99 salía siempre igual al
> máximo**. Un p99 que es el peor caso no sirve para lo único que se le pide — separar la cola de
> lo típico. Implementación real en `app/core/metrics.py`.

### 2.3 Test L2 — datos llegan a la tabla
```python
def test_metrics_persist():
    metrics._BUFFER.clear()
    @measure_latency('test_superficie')
    def f(): time.sleep(0.05)
    for _ in range(101): f()       # forza flush en 100
    rows = db.execute(
        "SELECT COUNT(*) FROM metrics_latency WHERE superficie='test_superficie'"
    ).fetchone()[0]
    assert rows >= 100
```

---

## 3. Pipeline crítico: disco → toast en <500 ms

El flujo más sensible. Test integrado:

```python
def test_pipeline_full_latency():
    img = 'fixtures/ocr_golden/001_polar_metal.png'
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        # 1) detector
        screen = detector.detect_screen(img)
        # 2) capturer
        crop = capturer.crop_for_screen(img, screen)
        # 3) OCR
        disco = analyzer.analyze_disc(crop)
        # 4) scoring
        score = scoring.evaluate(disco, agent='Ellen')
        # 5) recommender
        rec = recommender.decide(score)
        # 6) toast render (mock — sin Qt en CI)
        toast_payload = build_toast(rec)
        times.append((time.perf_counter() - t0) * 1000)

    p50 = percentile(times, 50)
    p99 = percentile(times, 99)
    assert p50 < 350     # margen al budget 380
    assert p99 < 500     # nunca exceder
```

### 3.1 Presupuesto interno (descomposición)
Diagnostico cuando se excede el target:

| Etapa | Budget | Cómo medir |
|-------|--------|-----------|
| Detector (template match) | 50 ms | `@measure_latency('detector')` |
| Capturer (mss + crop) | 50 ms | `@measure_latency('capturer')` |
| OCR (Tesseract+Paddle) | 180 ms | `@measure_latency('ocr')` |
| Scoring + recommender | 20 ms | `@measure_latency('scoring')` |
| Render toast (Qt) | 50 ms | `@measure_latency('toast_render')` |
| Margen para variabilidad | 50 ms | — |
| **Total budget** | **400 ms** (con margen 20%) | — |

### 3.2 Si p99 excede
1. Mirar `v_metrics_latency_7d` y encontrar la etapa que se disparó.
2. Si es OCR: ver QA-03 §9.
3. Si es detector: revisar tamaño de templates o threshold.
4. Si es Qt render: revisar si el toast bloquea el thread principal.

---

## 4. Toast lifecycle (RF-11)

Validar comportamiento del widget flotante:

| Caso | Acción | Esperado |
|------|--------|----------|
| Trigger tras score "Equipar" | nuevo disco con score>threshold_equip | toast aparece esquina inf-derecha, semi-transparente |
| Auto-fade | esperar 5 s sin interacción | toast desaparece con fade animado |
| Hover congela | mover mouse sobre toast | timer de fade se pausa |
| Click expande | click en toast | abre panel de detalle en pestaña "Captura en vivo" |
| Múltiples toasts en cola | 3 capturas seguidas | se apilan o se reemplazan según `user_config.toml::toast.cola_o_reemplazo` |
| Modo "silencioso" | configurar tray badge | sin toast, solo número en tray icon |
| Modo "todas" | configurar | dispara para Descartar y Reserva marginal también |

Test L2 con QtTest:
```python
from PySide6.QtTest import QTest

def test_toast_auto_fade():
    toast = ToastWidget(payload=...)
    toast.show()
    assert toast.isVisible()
    QTest.qWait(5500)
    assert not toast.isVisible()

def test_toast_hover_freezes_fade():
    toast = ToastWidget(payload=...)
    toast.show()
    QTest.mouseMove(toast, toast.rect().center())
    QTest.qWait(5500)
    assert toast.isVisible()  # pausado por hover
```

---

## 5. Hotkeys globales

`pynput` registra hotkeys que funcionan aunque ZZZ tenga foco. Tests L4 obligatorios (no se pueden simular en CI):

| Hotkey | Acción esperada |
|--------|-----------------|
| F8 | Captura manual (forzar análisis frame actual) |
| F9 | Toggle panel de detalle |
| F10 | Pausar/reanudar captura automática |
| F11 | Captura lategame (RF-13) |
| Ctrl+Shift+Z | Salida de emergencia desde cualquier estado |

Validación L4 con ZZZ corriendo:
1. Asignar foco a ZZZ (jugando combate activo).
2. Presionar F8 → toast aparece con análisis del frame actual.
3. F9 → panel se abre por encima de ZZZ (sin minimizar).
4. F10 → tray icon muestra "PAUSADO"; capturas no disparan.
5. Ctrl+Shift+Z → app cierra completamente; ZZZ continúa.

Edge cases:
- **Conflict con hotkey nativa de ZZZ:** ZZZ usa F1-F4 y otras. Validar que F8-F11 no estén usadas. Si lo están en patch futuro, permitir reasignación en `user_config.toml::hotkeys.*`.
- **Permisos en Windows:** algunas hotkeys globales requieren elevación. Documentar en wizard de primera ejecución si Daniel necesita ejecutar como admin.

---

## 6. Tray icon y ciclo de vida

| Caso | Esperado |
|------|---------|
| `.exe` doble-click | tray icon aparece + splash 1s + estado "Listo" |
| ZZZ no está corriendo | tray icon "Pausa (ZZZ no detectado)"; captura suspendida |
| ZZZ se inicia | tray cambia a "Activo"; captura arranca con polling adaptativo |
| Cerrar ventana panel | va al tray, no termina proceso |
| Salir desde tray menú | cierra completamente, persiste config + DB |
| Daniel matando proceso desde Task Manager | DB queda consistente (transacciones cortas) |

Test L4 obligatorio: **tras kill -9 forzado**, abrir DB y correr `PRAGMA integrity_check` — debe ser `ok`.

---

## 7. RAM y CPU

### 7.1 Targets
- RAM idle: < 200 MB.
- RAM pico OCR: < 400 MB.
- CPU idle polling: < 3% single core.
- CPU pico OCR: < 15%.

### 7.2 Test L4 con monitoreo (Daniel ejecuta)
Durante 30 min de gameplay con la app activa, abrir Task Manager y registrar:
- RAM media + pico.
- CPU medio + pico.
- Si la app excede budget en cualquier muestra → investigar.

### 7.3 Causas comunes de excedente
| Síntoma | Causa probable | Mitigación |
|---------|----------------|------------|
| RAM crece linealmente con tiempo | leak en cache de Qt o de `cv2.imread` sin liberación | usar `weakref` + profiler de Python |
| RAM pico OCR > 600 MB | PaddleOCR cargando modelo cada llamada | cargar 1 vez al inicio, reusar instancia |
| CPU 30%+ idle | polling demasiado frecuente | bajar a 2s en menús, 5s en pantalla principal |
| CPU pico 50%+ | template matching sin escalado | reducir tamaño de templates o usar pyramid scaling |

---

## 8. Arranque frío del `.exe`

`pyinstaller --onefile` produce binarios de ~60-80 MB que tardan en descomprimirse al primer arranque. Test L4:

| Sistema | Arranque frío esperado |
|---------|------------------------|
| SSD NVMe | < 2 s |
| SSD SATA | < 3 s |
| HDD | < 8 s (no es target principal) |

Mediación: usar `pyinstaller --onedir` si el arranque frío excede 3s en SSD; sacrifica portabilidad por arranque instantáneo (~300 ms).

---

## 9. Accesibilidad

RF-11 lista accesibilidad como criterio. QA L4:

| Caso | Validación |
|------|-----------|
| Tamaño de fuente en `user_config.toml` aplica a todos los widgets | sí |
| Atajos de teclado disponibles para todas las acciones (sin ratón) | tab navigation completa en panel |
| Feedback sonoro togglable | check en Configuración funciona |
| Tema oscuro (default) y claro | switch sin reiniciar |
| Contraste mínimo WCAG AA en toast y panel | revisión visual con plugin de browser o herramienta dedicada |

---

## 10. Edge cases UI

### 10.1 Multi-monitor
Daniel puede tener 2 monitores. El toast debe aparecer en el monitor donde está ZZZ.

```python
def test_toast_target_monitor():
    # ZZZ en monitor secundario
    set_zzz_window_to(monitor=1)
    toast = ToastWidget(payload=...)
    toast.show()
    assert toast.screen().geometry() == monitor_1.geometry()
```

### 10.2 Resolución de pantalla cambia
Daniel cambia resolución durante sesión:
- Detector debe reaccionar (recarga templates apropiados).
- Toast debe reposicionarse.

### 10.3 ZZZ minimizado / Alt+Tab
- Captura suspendida si ZZZ no es foreground.
- Hotkeys globales siguen funcionando.

### 10.4 Modo ventana vs fullscreen
Templates capturados en fullscreen pueden no matchear en modo ventana (UI difiere ligeramente). Validar ambos.

---

## 11. Wizard de primera ejecución

Caso L4 obligatorio: **instalación limpia desde cero** sin DB previa.

Pasos esperados:
1. Doble-click `.exe`.
2. Splash 1s.
3. Modal "Bienvenido — primera configuración" (3 pasos):
   - Paso 1: seleccionar carpeta para `db/danibod_zzz_v2.db` (default `%APPDATA%\Cowork_ZZZ\`).
   - Paso 2: calibrar ROIs OCR (capturar ejemplo de disco; el wizard guía).
   - Paso 3: registrar hotkeys (F8-F11 + Ctrl+Shift+Z); Daniel puede reasignar.
4. Tray icon aparece + DB inicializada con seed catálogos.
5. App pasa a "Listo (ZZZ no detectado)".

Test L4: en máquina sin DB previa, ejecutar `.exe`, validar que los 5 pasos terminan sin error y la DB resultante pasa `PRAGMA integrity_check`.

---

## 12. Cobertura mínima antes de cerrar Fase 2 (UI base)

- [ ] `metrics_latency` tabla creada y `@measure_latency` decorator aplicado a las superficies de §1.
- [ ] `test_pipeline_full_latency` p99 < 500 ms.
- [ ] L4 Daniel: 30 min de gameplay sin exceder RAM 200 MB / CPU 3% en idle.
- [ ] L4 Daniel: hotkeys F8/F9/F10 funcionan con ZZZ en foreground.
- [ ] L4 Daniel: kill -9 forzado deja DB íntegra.
- [ ] Wizard primera ejecución completo en máquina limpia.
- [ ] Toast aparece en monitor de ZZZ multi-monitor.

---

*La instrumentación es el costo de admisión. Sin números registrados de p50/p99, cualquier afirmación sobre "está rápido" es opinión. Y opiniones no cumplen RNF-06.*

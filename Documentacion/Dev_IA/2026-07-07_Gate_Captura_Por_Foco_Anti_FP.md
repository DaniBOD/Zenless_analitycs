# Gate de captura por foco de ventana (anti-FP Explorador) · 2026-07-07

> ## ⚠️ REVERTIDO COMO DEFAULT — 2026-07-30
>
> El gate **ya no viene activado**. `[monitor].solo_capturar_si_enfocado = false` y el fallback del
> helper también es `False`. Pedido de Daniel, repetido dos veces: **la captura no debe cortarse
> sola en segundo plano**. Este era el segundo de los dos mecanismos que la interrumpían; el otro
> —el auto-stop del watcher de ventana— se apagó el 2026-07-25.
>
> El gate no detenía el monitor, pero **pausaba la captura**, y desde afuera se ve igual de mudo.
>
> **Lo que se resigna es exactamente el FP que este documento describe:** con el juego tapado por
> otra ventana, `mss.grab()` toma los píxeles ajenos y el detector los clasifica. Se acepta a
> cambio de que la sesión no se interrumpa sola.
>
> **Para volver al comportamiento de acá:** `DANIBOD_FOCUS_GATE=1`, o `qa_launch.ps1 -FocusGate`,
> o poner `true` en `defaults.toml`. El código del gate sigue intacto — solo cambió su default.
> Fijado en `app/tests/unit/test_controller_focus_gate_off.py`.

**Estado:** CERRADO (commit local `fd7e1fe`, sin push). Falta verificación en vivo del usuario.
**Severidad:** menor (calidad de log) — elimina una clase de FP causada por ventanas ajenas superpuestas.
**Alcance:** cambio de comportamiento de **captura** únicamente. No toca DB, scoring, OCR ni parsers. RNF-03 OK.

## Síntoma

Con la app corriendo, a veces cae un **falso positivo** en el log al poner una ventana del
Explorador de archivos (u otra) **encima** de la ventana del juego.

## Causa raíz

[`capture_window()`](../../app/core/capturer.py) usa `mss.grab()` sobre la **región de pantalla**
donde está la ventana del ZZZ (`left/top/width/height`), **no** sobre la superficie propia de la
ventana. Si otra ventana tapa esa zona, `mss` captura esos píxeles ajenos → el detector los
clasifica → FP en el log. `find_zzz_window()` identificaba bien el juego (por `ZenlessZoneZero.exe`)
pero **descartaba el `hwnd`**, así que el loop no tenía con qué chequear el foco.

## Decisión de diseño

El usuario planteó la analogía de Discord ("transmitir una aplicación"). Se evaluaron dos caminos:

1. **Gating por foco (ELEGIDO).** Capturar solo cuando `ZenlessZoneZero.exe` es la ventana activa
   (foreground). Simple, robusto, 100% ToS-safe (RNF-03: solo lee píxeles en pantalla, y solo con
   el juego al frente). Ataca directo el escenario real (ventana ajena encima).
2. **Captura de app real (tipo Discord, DESCARTADO).** `PrintWindow`/`Windows.Graphics.Capture`
   de la superficie propia de la ventana aunque esté tapada. Problemas: ZZZ es DirectX → frames
   negros probables con `PrintWindow`; WGC funciona pero es dependencia pesada difícil de
   empaquetar en el `.exe` y roza RNF-03 (lee buffer fuera de pantalla). Más frágil y más riesgo.

Comportamiento acordado ante pérdida de foco: **pausar en silencio** con **un solo** diagnóstico
edge-triggered en el LivePanel; al recuperar el foco, reanudar con otro aviso único.

## Implementación

- **[`app/core/capturer.py`](../../app/core/capturer.py):**
  - `WindowBounds` ahora lleva `hwnd: int = 0`; `find_zzz_window()` lo propaga en sus **dos**
    returns (estrategia por exe + fallback por título).
  - `get_foreground_window() -> int` (`win32gui.GetForegroundWindow()`, con guardas → 0).
  - `is_zzz_focused(foreground_hwnd, zzz_hwnd) -> bool` — **pura y testeable**. True solo si
    `zzz_hwnd != 0 and foreground_hwnd == zzz_hwnd` (hwnd desconocido = 0 → no enfocado, conservador).
- **[`app/core/monitor.py`](../../app/core/monitor.py):** param `capture_only_focused=True` +
  estado edge-trigger `_focus_paused`. Gate en [`_get_frame()`]: si el juego no está al frente,
  emite el diagnóstico 1× y `return None` **sin anular `self._window`** (no forzar re-búsqueda de
  ventana cada frame) + `sleep(0.3)`. Al volver el foco, emite "reanudada" 1×. Complementa el hook
  `EVENT_SYSTEM_FOREGROUND` ya existente (que fuerza scan al volver el juego al frente).
- **[`app/config/defaults.toml`](../../app/config/defaults.toml):** toggle
  `[monitor].solo_capturar_si_enfocado = true`.
- **[`app/ui/controller.py`](../../app/ui/controller.py):** helper `_capture_only_focused()` lee el
  toggle (fallback True) y lo cablea al `Monitor`.

## Tests

`app/tests/unit/test_capturer_focus.py` — **8 tests, verdes**:
- `WindowBounds` acepta/expone `hwnd` (default 0).
- `is_zzz_focused` (tabla: 5/5→True, 5/9→False, 5/0→False, 0/0→False).
- Gate del monitor (monkeypatch de `find_zzz_window`/`get_foreground_window`/`capture_window`):
  sin foco → `_get_frame()` retorna None, no anula la ventana, diagnóstico de pausa 1× (edge);
  con foco → devuelve frame y emite "reanudada"; con `capture_only_focused=False` captura siempre.

Suite completa: **565 passed**, 4 failed **pre-existentes** (verificados con el working tree
stasheado): `test_stats_vocab::test_zero_unknowns_in_db`, `test_asset_resolver::test_full_coverage_against_db`,
`test_menu_agent` (2 frames OCR). Ninguno relacionado con este cambio.

## Notas / pendientes

- **Panel propio de la app:** si el usuario clickea el LivePanel/toast (proceso propio), el
  foreground deja de ser el ZZZ → la captura se pausa (inofensivo, no está farmeando). Refinamiento
  **opcional no implementado**: tratar "foreground pertenece a nuestro PID" como enfocado
  (comparar PID vía `win32process.GetWindowThreadProcessId`). Pendiente de decisión del usuario.
- **Verificación en vivo (paso del usuario):** con `.venv` activo + `qa_launch`, con el juego al
  frente la captura funciona igual; abrir el Explorador encima → "juego en segundo plano — captura
  en pausa" 1× y **cero FP**; volver al juego → "captura reanudada".
- **Sin push:** commit local `fd7e1fe`. `db/danibod_zzz_v2.db` (modificado por corridas de tests,
  ajeno a la feature) quedó **fuera** del commit.

## Referencias

- RNF-03 (CLAUDE.md §2): solo píxeles en pantalla; nada de lectura de memoria/inyección.
- Regresión FP de otra clase (frames del propio juego): `app/tests/unit/test_detector_fp_regression.py`.

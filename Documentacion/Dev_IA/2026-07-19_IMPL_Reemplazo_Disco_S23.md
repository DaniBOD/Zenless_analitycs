# IMPL — Reemplazo de disco entre PJs (S23 + confirmación por S17 + toast REEMPLAZADO)

**Fecha:** 2026-07-19 · **Estado:** implementado, pendiente QA en vivo · Toca la DB (RNF-01).

## Qué es

Mover un disco equipado de un PJ a otro. En el juego, al equipar en el PJ **destino** un disco
que otro PJ (**origen**) ya tiene, sale un diálogo: *"{origen} equipa actualmente {set} ({slot}).
¿Deseas sustituirlo?"* con Cancelar/Confirmar. Fixtures: `15_sustitucion_disco_confirmacion/`
(7 ejemplos, 1 o 2 líneas de texto).

Flujo: **S23 (diálogo) arma un swap pendiente** → la **confirmación llega en S17** cuando el disco
aparece equipado por el destino → **DB sync** (mover la fila del origen al destino) + **toast
REEMPLAZADO**. Ver el diálogo NO confirma nada (se puede cancelar); la confirmación es ver el
resultado en el flujo de equipamiento (mecanismo pedido por el usuario).

## 23.1 — Detección S23 (`detector.py`)
- Template `s23_sustitucion.png` = la fila **Cancelar/Confirmar** (invariante entre swaps): 0.996
  en los 7 fixtures vs 0.561 en los 37 negativos.
- Como esa fila es genérica de ZZZ (otros diálogos de confirmación la tienen), `_verify_s23`
  confirma por **OCR el texto exclusivo** "sustituirlo"/"equipa actualmente" (Tesseract lazy, corre
  solo cuando el template matchea). Umbral 0.85, NON_CAPTURE, cadencia 1000ms.
- Transiciones: entra desde S8/S17 (o la grilla de selección → S12), sale a S17/S8/S9.

## 23.2 — Parser (`parser_sustitucion.py`)
- OCR de la banda central (`_TEXT_ROI`), tokens unidos por posición (robusto al backend). Regex
  `(?P<pj>.+?) equipa actualmente (?P<set>.+?) (slot)`, con "(" opcional (el OCR lo come). PJ y set
  pueden tener espacios. Devuelve crudos (`origin_raw`, `set_raw`, `slot`) — resuelve el monitor.
- **PaddleOCR** (backend de la app) lee 7/7 con sets limpios; los nombres traen ruido ('7ixuan' por
  Yixuan) que absorbe el resolver fuzzy. (Tesseract vía `text_with_bboxes` no da cajas usables acá.)

## 23.3 — Puente PendingSwap + confirmación (`monitor.py`)
- **S23** (`_process_s23_sustitucion`): parsea, resuelve set (`DiscSetRepo.resolve_id`) y origen
  (`_resolve_agent_name`, fuzzy sobre el roster del `AgentIdentifier`), destino = `_last_agent_name`
  (latch). Guarda `_pending_swap` con TTL (`_S23_WINDOW_S=120s`) + log tentativo `(pendiente)`.
- **Latch:** S23 es modal y caería en el `else` de `_dispatch_state` (que resetea el latch a conf
  alta) → se le dio **rama propia** que preserva `_last_agent_name` (el destino). Bug evitado.
- **Confirmación** (`_maybe_confirm_swap`, llamado al inicio de `_emit_s17_disc`, ANTES del dedup):
  cuando S17 emite un disco cuyo (set, slot) coincide con el pending y está equipado por el
  **destino** → dispara `on_replacement` + log `✓`. TTL vencido → expira en silencio (sin toast).

## 23.4 — DB sync (`sync_equip.DiscSyncer.move_disc_between_agents`, RNF-01)
- **Hallazgo:** la persistencia S17 normal, al ver el disco equipado por el destino, **inserta una
  fila nueva** y **nunca toca al origen** → el disco quedaría DUPLICADO y el origen reclamándolo.
- **Fix (decisión del usuario):** `move_disc_between_agents` busca la fila EXISTENTE del disco del
  origen por `(origen, slot)` y le hace `update_assignment` → destino (una sola fila se mueve, sin
  duplicar), desequipando antes el disco desplazado del destino. Corre en el handler del controller
  **antes** que la persistencia S17 → cuando esta corre, ya encuentra el disco en el destino (set
  correcto) → va por el path de update, no inserta. Gate `is_readonly()`. Backup RNF-01 = el de
  sesión que hace el controller al arrancar.
- Limitación: si el disco del origen no estaba en la DB, no hay fila que mover (la persistencia S17
  lo dará de alta en el destino) → no-op con log.

## 23.5 — Toast REEMPLAZADO (`tokens.py`, `toast.py`, `controller.py`, `main.py`)
- `VARIANTS["reemplazado"]`: acento violeta (`PURPLE`), ícono swap, sin score/countdown.
- `DiscToast.show_replacement(data)` + body propio `_paint_body_replacement`: origen (DEJA,
  atenuado) → thumb del set (centrado) + set/slot → destino (EQUIPA, aro violeta). Header con badge
  estático "✓ SINCRONIZADO"; footer estático "EQUIPAMIENTO SINCRONIZADO". Auto-dismiss ~3s.
- `controller.disc_replaced` (Signal): `_on_replacement_from_monitor` hace el write + emite el
  payload (`_build_replacement_payload` resuelve logo del set + avatares -ico). `main.py` conecta
  `disc_replaced → _on_disc_show_replacement_toast`.

## Verificación
- Unit: `test_detector_sustitucion` (7→S23 + 37 negativos), `test_parser_sustitucion` (Paddle, 7/7),
  `test_monitor_sustitucion` (armado/confirmación/TTL/latch), `test_sync_swap` (move sin duplicar,
  readonly, edge), `test_toast_reemplazado` (variant + smoke offscreen).
- **QA en vivo pendiente** (`qa_launch -FromSource -NoFocusGate`, SIN `-ReadOnly` para el write, con
  backup): equipar en el PJ destino un disco de otro PJ → Confirmar → verificar log `[reemplazo]`,
  toast REEMPLAZADO, y que la DB movió `agente_asignado` sin duplicar.

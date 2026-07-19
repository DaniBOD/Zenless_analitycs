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

## 23.3 — S23 arma el pending (`monitor.py`, `_process_s23_sustitucion`)
- Parsea, resuelve set (`DiscSetRepo.resolve_id`) y origen (`_resolve_agent_name`, fuzzy sobre el
  roster del `AgentIdentifier`), destino = `_last_agent_name` (latch). Guarda `_pending_swap` con
  TTL (`_S23_WINDOW_S=120s`) + log tentativo `(pendiente)`.
- **Latch:** S23 es modal y caería en el `else` de `_dispatch_state` (que resetea el latch a conf
  alta) → tiene **rama propia** que preserva `_last_agent_name` (el destino). Bug evitado.

## Rediseño 2026-07-19 (v2) — corrección en la persistencia, no en la confirmación

**Por qué (QA en vivo 2026-07-18/19):** la v1 ataba la corrección de la DB a atrapar el diálogo S23
en la misma sesión/ventana. Dos fallas reales: (a) si el swap se confirma en el juego pero la app no
ve el S17 confirmatorio en esa ventana (se cerró, otra sesión, TTL vencido) → sin corrección; y peor
(b) la persistencia S17 normal, al ver un disco equipado por el destino con set distinto al del slot,
**INSERTABA una fila nueva** (nunca miraba al origen) → el disco quedaba **duplicado** (caso real:
Jazz de Jane → Velina dejó filas 368/369). El `move_disc_between_agents` (v1) que lo evitaba solo
corría en la confirmación, que no disparó.

**Decisión (con el usuario):** la **corrección vive en `persist_s17_disc`** (DB correcta SIEMPRE,
haya o no diálogo); el **toast** se dispara desde ahí y solo si el swap es **fresco**. El S23 se
conserva como **hint de origen** (cierto) cuando se vio; si no, respaldo por **identidad exacta
única**.

### 23.3b — Hint en S17 (`monitor._attach_swap_hint`)
- Reemplaza a `_maybe_confirm_swap`. Llamado al inicio de `_emit_s17_disc` (ANTES del dedup). Si un
  pending fresco matchea (set, slot) y el disco lo equipa el **destino** → adjunta
  `disc.swap_origin_hint = origen` + `disc.swap_fresh = True`, consume el pending y loguea `✓`. TTL
  vencido → expira en silencio. Ya NO dispara `on_replacement` (eliminado del monitor).

### 23.4 — DB: move-en-persistencia (`sync_equip.persist_s17_disc` + `_find_disc_to_move`, RNF-01)
- Cuando el destino muestra un disco distinto al del slot (o slot vacío), antes de insertar se busca
  la fila EXISTENTE a **mover/re-equipar**:
  1. **Hint S23** (`swap_origin_hint`): `find_equipped_by_agent_slot(origen, slot)` si su set
     concuerda → cross-PJ.
  2. **Respaldo por identidad exacta ÚNICA** (`InventoryDiscRepo.find_swap_candidates_by_identity`,
     nuevo): filas con misma (set, slot, nivel, main, {substat+rolls}) que estén **equipadas por
     OTRO PJ** (cross-PJ) **o desequipadas del propio destino** (re-equipar su disco desplazado).
     **1** → usar; **0** → nuevo (insert); **≥2** → ambiguo → insert + warning (**nunca robar/tocar
     el disco equivocado**, RNF-02). Deliberadamente NO mira discos sueltos de otros/sin dueño.
- Mover = `set_unequipped` del disco desplazado del destino + `update_assignment(fila, destino)`.
  Una sola fila cambia, sin duplicar. Solo el swap **entre PJs** cuenta como `moved`/`s17_move`
  (dispara el toast); **re-equipar** un disco propio desplazado es `s17_reequip` (corrige la DB en
  silencio, sin toast — se descubrió en QA 2026-07-19: sin esto, re-equipar un disco desplazado
  INSERTABA un duplicado). `move_disc_between_agents` (v1) **eliminado** (plegado acá). `SyncResult`
  gana `moved`, `moved_from_nombre`, `swap_fresh`, `set_id`. Gate `is_readonly()`. Backup RNF-01 =
  el de sesión del controller.

### 23.5 — Toast REEMPLAZADO (`tokens.py`, `toast.py`, `controller.py`, `main.py`)
- `VARIANTS["reemplazado"]`: acento violeta, ícono swap, sin score/countdown. `DiscToast.show_replacement`
  + body propio (origen DEJA atenuado → thumb set/slot → destino EQUIPA, aro violeta), header estático
  "✓ SINCRONIZADO", ~3s.
- `controller._on_disc_from_monitor`: tras `persist_s17_disc`, si `result.moved and result.swap_fresh`
  → arma el payload (`_build_replacement_payload` resuelve logo + avatares -ico) y emite
  `disc_replaced` → toast. **Correcciones tardías** (moved sin fresco) mueven la fila **en silencio**.
  `_on_replacement_from_monitor` eliminado; `main.py` sigue conectando `disc_replaced`.

## Verificación
- Unit: `test_detector_sustitucion` (7→S23 + 37 negativos), `test_parser_sustitucion` (Paddle, 7/7),
  `test_monitor_sustitucion` (armado/hint/TTL/latch), `test_sync_swap` (move por hint / por identidad
  única / ambiguo-no-roba / distinto-nivel-no-roba / re-ver-no-duplica / readonly / **regresión del
  caso Jane→Velina sin duplicar**), `test_toast_reemplazado` (variant + smoke offscreen).
- **QA en vivo pendiente** (`qa_launch -FromSource -NoFocusGate`, SIN `-ReadOnly`, con backup):
  equipar en el destino un disco de otro PJ → verificar log `s17_move ... (movido, sin duplicar)`,
  toast REEMPLAZADO, y que la DB movió `agente_asignado` **sin** filas nuevas.

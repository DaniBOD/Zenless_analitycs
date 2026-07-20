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

## QA en vivo 2026-07-20 — la DB pasó, el toast no; frescura sin reloj

**Resultado:** el swap (Jazz caótico slot 1 · Jane → Velina) persistió `s17_move id=25`, **367
discos, cero duplicados**, integrity/fk ok. El rediseño v2 cumplió su promesa central: la DB queda
correcta. **Pero el toast no saltó**, y el log explicó por qué: `(movido, sin duplicar; corrección
tardía)` — el pending había expirado.

**Causa raíz (dos capas):**
1. **El handler S17 se trabó 8m42s sin emitir** (16:41:35 → 16:50:17). Reentrar a la pantalla lo
   destrabó al instante. El log no decía NADA en ese lapso porque
   `_process_disc_s17_continuous` tiene **dos returns tempranos mudos**: firma no calculable
   (`sig is None`) y `confianza_global < 0.7`. Desde afuera eran indistinguibles.
2. Con la emisión llegando ~10 min tarde, el **TTL de 120s** del pending ya había vencido → el
   movimiento se hizo por el respaldo de identidad, en silencio, sin toast.

**Fixes:**
- **`_note_s17_stall` / `_clear_s17_stall`** (`monitor.py`): instrumentan los dos returns mudos.
  Logueo por **flanco** (al trabarse y al destrabarse, con el conteo de ciclos), no por ciclo —
  RNF-06. Sin esto, el próximo trabe vuelve a ser invisible.
- **FRESCURA = "no superado todavía", NO "dentro de N segundos"** (decisión del usuario): se
  eliminó `_S23_WINDOW_S`. El pending vive hasta consumirse, hasta que otro S23 lo reemplace, o
  hasta cerrar la app. Es seguro porque `_attach_swap_hint` exige que el disco esté equipado por
  el **DESTINO**: si cancelaste el swap, eso nunca ocurre.
- **Endurecimiento del hint (RNF-02)** — el riesgo que abre un pending inmortal: cancelás y
  después equipás al destino OTRO disco del mismo set+slot; el hint diría "origen = Jane" y se
  movería la fila de Jane, que es la equivocada. Ahora el hint solo se usa si la fila del origen
  coincide por **identidad COMPLETA** (`InventoryDiscRepo.row_matches_parsed_identity`, extraído
  de `find_swap_candidates_by_identity` para compartir criterio); si no calza, cae al respaldo.

## Rediseño 2026-07-20 (v3) — el toast es OBSERVACIONAL, no depende de la DB

**Por qué.** La v2 puso la corrección en la persistencia (bien) pero dejó el **toast** colgado de
su resultado (`result.moved and result.swap_fresh`, `controller.py:657`). Eso trajo dos costos que
el QA del 2026-07-20 hizo evidentes en cuatro intentos fallidos seguidos:
- **En read-only el toast no podía salir NUNCA**: `persist_s17_disc` corta en `sync_equip.py:375`
  y devuelve `moved=False`. El feature era intesteable sin escribir la DB.
- **Cualquier desincronización DB↔juego se comía un swap real.** Si la DB creía que el disco era
  de otro dueño, el respaldo por identidad lo clasificaba como `s17_reequip` (re-equipar propio) y
  el toast desaparecía, aunque el reemplazo hubiera ocurrido delante de la cámara.

El error era conceptual: **el toast afirma lo que se VIO en pantalla**; lo hicimos depender de lo
que la DB logró escribir. La observación es la fuente de verdad; la DB es una consecuencia.

**Decisión del usuario (3 preguntas):** persistencia **conservada pero desacoplada**; el check
acepta el dueño **certero + observado**; y corre **apenas se sepan slot+set+dueño**, sin esperar
a que el disco madure.

### 23.6 — `monitor._check_swap_owner` (reemplaza a `_attach_swap_hint`)
Cambia de nombre porque cambia de trabajo: ya no "adjunta un hint en silencio", **chequea y
loguea siempre**. Cuando el disco en pantalla es el del pending (mismo set+slot), clasifica en
**cuatro desenlaces** y loguea el resultado por FLANCO (RNF-06, el ciclo repite muchas veces/s):

| Desenlace | Condición | Acción |
|---|---|---|
| `CAMBIÓ ✓` | el dueño es el **destino** | hint + `swap_fresh` + `on_replacement` (toast) |
| `sin cambio` | sigue siendo el **origen** → canceló | nada; **no** consume el pending |
| `incierto` | equipado sin nombre / libre | nada; **no** consume (RNF-02) |
| `otro` | ni origen ni destino | nada; **no** consume (RNF-02) |

Dueño = `agente_asignado_nombre` **o** `equip_pj_visual`. El observado cubre el caso real de los
logs (`[badge] ancla decía X pero el badge dice Y`): ahí el badge tiene razón y exigir solo el
certero perdía el swap. El pending lleva un `seq` propio para el flanco del log (no `id()`, que
Python reutiliza tras el gc).

### 23.7 — El check corre en el ciclo continuo, no en la emisión
Se movió de `_emit_s17_disc` a `_process_disc_s17_continuous` (tras el merge del aggregator y en
el path de warmup). Mismo patrón —y mismo motivo— que la confirmación de upgrade, que ya se había
desacoplado por quedar en warming eterno: `_emit_s17_disc` exige madurez (`conf>=0.70`) y en QA
hubo **trabes de 8m42s sin emitir** con un swap real perdido en el medio. El chequeo solo necesita
(set, slot, dueño), que ya están en el merge parcial.

### 23.8 — `on_replacement` vuelve, ahora sin DB
El callback que la v2 había eliminado regresa con la semántica correcta: **notifica una
observación, no ejecuta un write**. `controller._on_replacement_from_monitor` resuelve el `set_id`
con `_lookup_set_id` (lectura) y arma el payload con `asset_resolver` — mismo estilo que el toast
de recomendación, que ya salía en read-only. Se quitó la rama del toast de `_on_disc_from_monitor`
para que no dispare dos veces.

### 23.9 — Persistencia: el diálogo le gana a la atribución vieja
`_find_disc_to_move`: si el respaldo por identidad halla fila única que la DB atribuía al destino,
pero **hay un hint del S23 nombrando otro origen**, gana el diálogo — es evidencia directa del
juego contra una creencia que la app nunca vio cambiar. Convierte un `s17_reequip` falso en el
`s17_move` correcto.

### 23.10 — Rescate del slot en el diálogo (causa raíz de los fallos "aleatorios")
`parser_sustitucion.py`: PaddleOCR leía **`(1)` como `(i)`** → la regex exigía `[1-6]`, no
matcheaba, y `parse_sustitucion` devolvía `None` en un `return` mudo. **Sin pending → sin toast.**
Por eso el diálogo del **slot 1** fallaba "al azar" y los slots 2-6 no. Segunda pasada de rescate
(`i/l/|`→1, `s`→5, `b`→6, `z`→2) que **solo corre si la estricta falla** y **exige el paréntesis
de apertura** (sin él, un set terminado en 's' podría colarse como slot 5).

### 23.11 — Instrumentación de trabes (`_note_stall` / `_clear_stall`)
Los returns tempranos mudos de `_process_disc_s17_continuous` (`sig is None`, `conf<0.70`) y de
`_process_s23_sustitucion` (parser devolvió None) ahora loguean por flanco, con el conteo de
ciclos. Además `_dump_s23_fallo` guarda el frame en `audit/s23_parse_fallo/` la primera vez que
el parser falla — fue lo que permitió encontrar el `(i)`.

### 23.12 — El avatar de Jane salía con el cuadrado de HoYoLAB
Detectado en el QA visual del toast (2026-07-20). `agent_avatar_path(nombre, variant="ico")`
tenía como **último recurso** un fallback al jpeg de `Pj_stats` (`asset_resolver.py:225`), que es
el cuadrado del perfil de HoYoLAB —con marco y fondo—, estéticamente incompatible con el `-ico`
(cara redonda limpia). La DB llama a la agente **`Jane`** y su archivo es **`Jane-Doe-ico.webp`**,
así que el nombre no matcheaba, caía al fallback y el toast la mostraba con el estilo equivocado.
Era el **único** caso: 48/49 resolvían bien, y por eso nunca se notó.

Dos correcciones:
- Override `"Jane" → "Jane-Doe"` en `_AGENT_SPLASH_OVERRIDES` → **49/49 con ico limpio**.
- **El `-ico` ya no cae a `Pj_stats`**: devuelve `None` + `log.warning`. El toast degrada a
  placeholder (ya lo soporta, ver `test_show_replacement_sin_avatares_ni_logo`), que es honesto;
  el fallback silencioso disimulaba el asset faltante en vez de exponerlo. Seguro de cortar
  porque `variant="ico"` lo usa **solo** el toast de reemplazo (`controller.py:710`); `extend`
  y `pj_stats` conservan su fallback.
- `test_full_coverage_against_db` ahora **también valida el `-ico`** de todo el roster — sin eso
  Jane pasó desapercibida.

## Verificación
- Unit: `test_detector_sustitucion` (7→S23 + 37 negativos), `test_parser_sustitucion` (Paddle, 7/7),
  `test_monitor_sustitucion` (armado/hint/TTL/latch), `test_sync_swap` (move por hint / por identidad
  única / ambiguo-no-roba / distinto-nivel-no-roba / re-ver-no-duplica / readonly / **regresión del
  caso Jane→Velina sin duplicar**), `test_toast_reemplazado` (variant + smoke offscreen).
- Unit nuevos (2026-07-20): `test_monitor_sustitucion::test_el_pending_no_expira_por_reloj` +
  `::test_un_s23_nuevo_reemplaza_al_pending_anterior`;
  `test_sync_swap::test_hint_desactualizado_no_mueve_la_fila_equivocada`.
- **DB verificada en vivo 2026-07-20** (367 discos, `id=25` → Velina, sin duplicar, integrity ok).
- Unit v3 (2026-07-20): `test_monitor_sustitucion` (4 desenlaces del check + dueño observado +
  log por flanco + independencia de la emisión), `test_reemplazo_readonly` (**el toast sale con
  `DANIBOD_READONLY=1`**, la persistencia no reporta movimiento, y la vía de emisión ya no
  emite el toast → anti-doble-disparo), `test_parser_sustitucion` (rescate `(i)`→slot 1).
- ✅ **QA EN VIVO VERDE — 2026-07-20 19:39-19:41, en READ-ONLY.** Tres checks, tres desenlaces
  correctos, **toast violeta confirmado en pantalla**, cero errores, cierre limpio:

  | Hora | Disco | Resultado | Realidad |
  |---|---|---|---|
  | 19:39:22 | Jazz Caótico slot 1 | `Jane → Velina · CAMBIÓ ✓` | reemplazo real |
  | 19:40:22 | Salón huracanado slot 1 | `Jane → Jane · sin cambio` | cancelado |
  | 19:41:27 | Salón huracanado slot 1 | `Jane → Velina · CAMBIÓ ✓` | confirmado |

  **La DB quedó byte-a-byte idéntica** (mismo sha256 al inicio y al final, 367 discos) — la
  prueba de que el toast ya no depende de escribir. Los casos 2→3 son la mejor evidencia de que
  el check LEE la pantalla y no acierta por inercia: mismo disco y mismo par de PJs, desenlaces
  distintos según lo que el usuario realmente hizo. El `seq` del pending fue lo que permitió que
  el 3ro logueara (si no, el flanco se lo comía). Ambos `CAMBIÓ` fueron en **slot 1**, así que el
  rescate `(i)`→1 quedó validado en vivo de paso. Secuencia final: el ancla
  (`[S17] asignado a 'Velina' (latch)`) y el check en el **mismo segundo**.

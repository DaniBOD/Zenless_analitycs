# IMPL — Mejora de disco (modal upgrade S10): detección + parser + tracking PRE→POST

**Fecha:** 2026-07-10 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only (no escribe DB) · **RF:** RF-05 (§7.4).

Cierra la captura del **modal de mejora de disco** (estado `S10`): reconocer la pantalla, parsear
el disco (nivel + main + substats con rolls) y **trackear PRE→POST** (qué substat gana roll al
subir de nivel). Todo display-only, sin persistencia (RNF-01 no aplica).

## Contexto y hallazgos (capturas reales 2559×1439, folders 05/06/07)

Los 3 folders contienen **dos pantallas distintas**:

- **Modal S10 de upgrade** (`05_…nivel0`, `06_…nivel3_6_9_12`, `07_…detallado`): modal centrado.
  Título "Set (slot)" arriba-izq; panel de detalle **a la derecha** (xn∈[0.44,0.90]); main + **grilla
  2×2** de substats con badges `+N` naranjas; **barra de nivel chevron** (`N | exp/exp | N` en PRE,
  `15 | MAX | 15` verde en MAX); botones "Añadir todo | Mejorar". **Sin** "Efecto de conjunto".
- **Detalle familia S17** (`07_…general` → S17 equipado; `07_…tienda_musica` → S7 ciudad): **con**
  "Efecto de conjunto". No son el objetivo — ya se parsean por sus propios paths.

Diagnóstico inicial: el detector caía **todos** los modales a **S12** (el template viejo
`s10_modal_upgrade.png` apuntaba a una barra EXP verde central inexistente en este layout; y
`_verify_s10` exigía verde → fallaba a nivel 0).

## 1. Detección (`detector.py`)

- **Template nuevo** = barra de botones **"Añadir todo | Mejorar"** (ROI `[0.60,0.82,0.32,0.09]`,
  fuente `07/Ejemplo_1(detallado).png`). Es la región **estable entre niveles** (0/3/6/9/12/MAX) y
  **única de S10**: matchea los S10 reales ≥0.85 y los NON-S10 (S17/S7/S13) ≤0.50. Regenerado con
  `tools/build_templates.py`.
- **Umbral** S10 bajado 0.85→**0.80** (gap enorme a los NON → margen para la deriva de captura viva
  mss 2560×1440).
- **`_verify_s10`** reescrito **nivel-independiente**: confirma la franja clara de la barra de nivel
  (gris a nivel 0, verde si >0); nunca bloquea por color. El template ya es autoritativo.
- Verificado: 05/06/07-detallado → **S10** (0.86–1.00); 07-general→S17, tienda_musica→S7 **sin
  regresión**. La `StateMachine` es no-estricta → no hace falta tocar transiciones.

## 2. Parser (`parser_disc_s10.py`, nuevo)

`parse_disc_s10(frame, ocr) → DiscParsed`. Reusa los **helpers de bajo nivel** de `parser_disc_s17`
(`_Line`, `_split_rolls`, `_coalesce_rolls_fragments`, `_rescue_roll`, `_rescue_missing_value`,
`_canon_with_unit`) pero con **lógica espacial propia** por dos diferencias con S17:

1. Panel a la **derecha** (no la franja central).
2. Substats en **grilla 2×2** (dos columnas nombre/valor), no una columna → se parsea cada columna
   con su propio split (`_SUB_COL_L` split 0.58, `_SUB_COL_R` split 0.80).

Nivel de la **barra chevron** (`_read_level_bar`): pill izq = nivel actual; centro = "N/M" (PRE) o
"MAX" (maxeado → nota `s10_max`). Título tolerante al `)` de cierre que el OCR dropea
(`Fábula Yunkui(1` → slot 1). Set se canoniza en el caller.

## 3. Tracking PRE→POST (`sync_upgrade.py`, reescrito display-only)

`UpgradeSyncer` — el viejo usaba `parse_modal_detalle` (per-ROI sin calibrar) y **escribía DB**; se
reescribió sobre `parse_disc_s10`, **sin DB**, emitiendo diagnósticos:

- `on_s10_enter`: parsea el PRE, emite `[mejora] <set> slot N · nivel M · main … · subs …`.
- `on_s10_update`: **parse-on-change** — re-parsea apenas la **firma de la barra de nivel** cambia
  (gate RNF-06: idle si no cambió). Al subir nivel emite `[mejora] nivel M→M2 · +K en <substat>`.
- `on_s10_exit`: **difiere** el resumen (ver abajo) → guarda un "pendiente".
- `on_post_upgrade_disc(disc)`: la **S17 posterior** confirma el estado final.

### Decisión clave: el estado final lo da la S17, no S10

En vivo (QA 2026-07-10) se vio que al **maxear**, el juego auto-cierra el modal S10 en <1 ciclo de
poll → el frame MAX (con el **último roll** asentado) casi nunca se puede leer dentro de S10 (se
perdía el `Perforación +3`). La pantalla de **inventario del PJ (S17)** que sigue muestra el disco
con **todos los rolls asentados de golpe**. Por eso el **resumen se difiere** hasta que la S17
posterior confirme (`on_post_upgrade_disc`, matcheo por set+slot, ventana 30 s):

```
[mejora] resumen: nivel 0→15 · MÁXIMO · Perforación: +3, DEF%: +1, …
```

Fallback: si no aparece la S17, cierra con lo visto en S10 al abrir el próximo modal.

### Refuerzo (2026-07-13): nivel PROYECTADO desde el preview "pre-15-max"

Hallazgo del usuario (capturas `07/Ejemplo_{1,2,3}(pre-15-max).png`): tras cargar los materiales de
EXP ("Añadir todo") pero **antes** de tocar "Mejorar", la barra chevron muestra `pill_izq = nivel
ACTUAL` y `pill_der = nivel PROYECTADO` (0│48700/7200│**15**). Es un frame **estable** (a diferencia
del MAX real, que auto-cierra) → sirve de "antes→después" para **cualquier salto** (0→15, 5→10, …),
no solo el maxeo. Verificado por OCR: pill der en xn≈[0.809,0.825], separada limpiamente del centro.

- **Parser** (`_read_level_bar`): ahora lee la **pill derecha** (banda `_LEVEL_RIGHT_X=(0.76,0.90)`) y
  devuelve `proyectado`. Si `proyectado > nivel`, agrega nota **`s10_target:N`** (patrón de
  `s10_max`/`s10_pre`). El `nivel` del disco sigue siendo el ACTUAL — el target es solo la intención.
- **Sync** (`sync_upgrade`): `_target_from_notas` extrae el destino; `on_s10_enter`/`on_s10_update` lo
  capturan en `self._target` y lo anuncian una vez (`materiales cargados · nivel N → proyectado M`);
  el pendiente pasa a 4-tuple `(pre, last, target, ts)`. Doble beneficio:
  1. **Nivel-0 confiable:** la pill izquierda del preview es el PRE real aunque se haya entrado rápido.
  2. **Maxeo instantáneo:** conocemos el destino ANTES del auto-cierre → el `_flush_pending` de
     fallback resume con el proyectado (marcado "sin confirmar") si la S17 nunca llega. La S17 sigue
     siendo la fuente autoritativa de los rolls finales.

### Robustez (2026-07-13): el popup "Materiales recuperados" (S20)

QA en vivo reveló que al MAXEAR el flujo real **no** es S10→S17 directo, sino:

```
S10 (Mejorar) → popup "Materiales recuperados" (vuelto de sobrantes, Confirmar) → S17
```

Ese popup exige un click manual → el salto a S17 tardó **~47 s** en el QA. Tres consecuencias y sus fixes:

1. **El pendiente expiraba (TTL 30 s).** Cuando la S17 llegaba, el pendiente ya estaba muerto → no
   salía el resumen de substats/main. **Fix:** TTL `_PENDING_TTL_S` 30→**120 s** (seguro: la
   confirmación exige match set+slot y el pendiente se limpia al abrir el próximo modal).
2. **El popup caía a S12 ("no reconocida").** **Fix:** nuevo estado **S20** (template del título
   centrado "Materiales recuperados", umbral 0.78; target 1.00 vs NON-S20 ≤0.63). NON_CAPTURE +
   CONTINUO. `_read_level_bar` no lo toca — es su propio template en el detector.
3. **Sin ancla durante la espera.** **Fix:** `UpgradeSyncer.on_material_refund()` (llamado desde el
   monitor cuando `state==S20`) **refresca el timer** del pendiente cada ciclo mientras el popup se
   muestra (así no expira ni con esperas largas) y loguea una vez `vuelto de materiales confirmado ·
   esperando inventario`. La S17 sigue dando los rolls finales.

Bug cosmético colateral arreglado: el menú de PJ (S15) reusaba el callback de detalle de agente
(hardcode "Equipamiento") → salía el confuso `S15 — Equipamiento reconocida` + origen mal
("heredado de Atributos base"). Ahora `controller._on_agent_detail_from_monitor` maneja
`source="menu"` → una línea correcta `[reconocido] <PJ> (del menú de personajes)`.

### Fix crítico (2026-07-14): confirmación DESACOPLADA de la identidad del dueño

Tras los fixes de S20/TTL, la S17 posterior **seguía sin emitir el resumen**. Diagnóstico (evidencia):
descartada la confianza (fixtures S17 parsean 0.80–0.99) y el dedup (la sesión se resetea al salir
de S17), la causa raíz fue **arquitectural**: la confirmación (`on_post_upgrade_disc`) colgaba de
`_emit_s17_disc`, que está **gateado por el warming de identificación del dueño**. Al volver del popup
S20 el disco viene **sin latch** y su badge vota **INCIERTO** → el disco entra en *warming* esperando
resolver quién lo equipa y **nunca emite** (QA: 2 min en S17 sin `Disco detectado`) → nunca confirma.

Saber quién equipa el disco es **ortogonal** a confirmar sus cambios de stats. **Fix:** mover
`on_post_upgrade_disc(merged)` en `_process_disc_s17_continuous` al punto donde el disco **MADURA**
(`mature or ceiling`), **antes** del gate de warming del dueño. Así el resumen sale apenas los rolls
asientan, con dueño resuelto o no. La emisión normal (log/on_disc/dueño) sigue su curso aparte.
Regresión: `test_s17_confirma_upgrade_aunque_dueno_incierto` (dueño incierto → emisión diferida pero
confirmación SÍ dispara). QA en vivo 2026-07-14: `resumen: nivel 0→15 · MÁXIMO · DEF: +1, ATK%: +1,
DEF%: +2` ✅.

### Wiring
- `monitor._handle_upgrade(frame, state, prev_code)` — **fix de bug latente**: leía `prev_code` de
  `self._last_state`, ya pisado por `_notify_state_change` antes del dispatch → el "enter" nunca
  disparaba. Ahora recibe el `prev_code` real de `_dispatch_state`.
- **S10 agregado a los estados CONTINUOS** del loop (línea ~736): sin esto, tras entrar al modal
  (que dispara el PRE por transición) el "Mejorar" no cambia de pantalla → `on_s10_update` nunca
  corría. Bug encontrado en vivo.
- `_process_disc_s17_continuous` llama `on_post_upgrade_disc(merged)` tras emitir cada disco S17.
- `controller._init_dependencies` construye e inyecta el `UpgradeSyncer` (mismo sink de diagnósticos).

## Verificación

- **Detección:** 113 tests de detector verdes (regresión FP incluida).
- **Parser:** `test_parser_disc_s10.py` — 3 estados reales (nivel 0/12/MAX) con set/slot/nivel/main/
  substats+rolls correctos + `s10_target:15` en los 3 `pre-15-max` y ausencia de target en los
  fixtures sin materiales.
- **Sync:** `test_sync_upgrade.py` — `_roll_diff`/`_same_disc`/`_target_from_notas` puros +
  confirmación S17 (el último roll de Perforación se recupera del disco asentado) + fallback con
  proyectado + integración OCR real (secuencia Fábula Yunkui 0→12, resumen 0→15 confirmado por S17;
  `on_s10_enter` sobre preview real emite "proyectado 15").
- **Suite:** 822/822 (812 previos + 10 nuevos del refuerzo pre-max).
- **QA en vivo (2026-07-10):** PRE OK; histórico incremental OK (3→6→9→12, cada `+1` bien atribuido);
  el salto final a MAX se recupera vía S17.

## Pendiente (QA / follow-up)

- **QA del usuario:** upgrade 0→15 **de golpe** (sin histórico incremental) → validar que el resumen
  sale de la S17 posterior con todos los rolls, y que el preview loguea `→ proyectado 15`. **Sin
  commit hasta validar en vivo.** (El refuerzo pre-max apunta justo a esto y al nivel-0/latencia.)
- Múltiples entradas al modal (tienda de música además de inventario) — la detección por template no
  depende del origen, pero confirmar en vivo la entrada desde tienda.

Doc gemelo en memoria: `project_s10_upgrade_next` (actualizar a "implementado, QA pendiente").

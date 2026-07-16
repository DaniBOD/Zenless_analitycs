# IMPL — Mejora de disco desde la TIENDA DE MÚSICA: confirmación por S5 (no S17)

**Fecha:** 2026-07-16 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only · **RF:** RF-05 (§7.4).

Cierra el pendiente que había quedado anotado en el doc de S10 (*"confirmar en vivo la entrada
al modal desde tienda de música"*). Resulta que la entrada desde la tienda **no es una variante
cosmética**: es un **flujo distinto** que rompía el resumen PRE→POST.

## El hallazgo: la tienda nunca pasa por el inventario

El diseño de S10 (2026-07-10) asumía que el estado final lo confirma **la S17 posterior**
(inventario del PJ), porque al maxear el modal se auto-cierra antes de que se lean los rolls.
Pero mejorar desde la afinación es:

```
S5 (resultado de afinación) → S10 (modal mejora) → [S20 vuelto] → S5   ← NUNCA hay S17
```

`on_post_upgrade_disc` colgaba **solo** del path de S17 (`_process_disc_s17_continuous`) → en
este flujo **nunca se llamaba** → a los 120 s caía el fallback sólo-S10:

```
[mejora] resumen: nivel 0→2 · sin cambios de roll (sin confirmar en inventario)
```

…cuando el usuario había maxeado el disco. **Pero el dato correcto estaba a la vista:** la S5
posterior muestra el disco ya mejorado y `parse_disc_s5` **lee el nivel real y los rolls
asentados** (QA: `slot=2 main=ATK nivel=15`, `HP 224 (+1)`, `Maestría de Anomalía 36 (+3)`).

**→ En este flujo, la S5 ES el equivalente de la S17.**

## 1. La S5 confirma el upgrade (`monitor._process_disc_s5_continuous`)

Se llama `on_post_upgrade_disc(merged)` al madurar el disco S5, **DESACOPLADO de
`_emit_s5_disc`** — misma lección que el fix del 2026-07-14 en S17: la confirmación no debe
colgar de la emisión. Acá importa doble, porque el dedup por identidad (`_disc_identity`
incluye los rolls) **bloquearía** la emisión de un upgrade sin cambio de roll, y aun así el
resumen debe salir.

`on_post_upgrade_disc` ya elegía el POST autoritativo por nivel (`disc.nivel >= last.nivel`) →
con la S5 dando `nivel=15` gana sobre lo que S10 alcanzó a ver. Solo se amplió el docstring:
dos flujos (S17 inventario / S5 tienda), misma función.

## 2. Matcheo PRE↔POST tolerante al ruido OCR del set (`sync_upgrade._same_disc_canon`)

**Necesario, no cosmético.** El OCR lee el nombre del set de forma inestable — confusión
clásica **I mayúscula vs l minúscula**:

```
Firmamento llameante   /   Firmamento Ilameante   /   Firmamento Illameante
```

`_same_disc` comparaba nombres **crudos** normalizados. En S17 zafaba porque el disco se re-lee
en varios ciclos y alguno sale limpio; **en S5 hay UNA sola pasada de confirmación** (el dedup
corta el re-procesamiento) → una lectura ruidosa perdía el resumen para siempre.

`_same_disc_canon` resuelve **ambos** sets al canónico vía `_set_name()` (que ya usaba
`DiscSetRepo.resolve_id`, difuso con cutoff 0.86) antes de comparar. Sin `set_repo` cae al
comportamiento de `_same_disc` (crudo) → compatible hacia atrás.

> **Evidencia del QA:** a las 12:44:07 la S5 leyó `Firmamento Illameante` mientras el PRE había
> leído `llameante` — comparando crudo NO matcheaba. El resumen salió gracias a esta resolución.

## 3. Sin preview redundante al volver del modal (`monitor._dispatch_state`)

Al re-entrar a S5 se hacía `_s5_grid_slots = ()` → `_s5_batch_is_new` devuelve True cuando no
hay slots previos → re-emitía **las 10 líneas** del preview de la grilla. Volver del modal de
mejora **es** re-entrar → spam por cada disco mejorado (el usuario lo reportó como redundante).

Fix: si `prev_code in ("S10", "S20")` **no** se resetean los slots — es la MISMA tanda, solo que
el disco quedó mejorado. Re-entrar desde cualquier otra pantalla sí re-previsualiza, y re-afinar
de verdad (multiset ≠, `_S5_BATCH_MIN_DIFF`) sigue funcionando igual.

## Verificación

- **Unit:** `test_s5_confirma_upgrade_de_la_tienda_de_musica` (la S5 llama a la confirmación) ·
  `test_s5_vuelta_del_modal_de_mejora_no_reemite_preview` (S10/S20 → conserva; otra pantalla →
  re-previsualiza) · `test_confirmacion_tolera_ruido_ocr_del_nombre_del_set` ·
  `test_confirmacion_sin_set_repo_cae_a_comparacion_cruda`.
- **Suite:** **845 passed**.
- **QA en vivo 2026-07-16** (2 discos maxeados desde la tienda):
  ```
  12:44:07  [mejora] resumen: nivel 0→15 · MÁXIMO · ATK%: +2, DEF%: +1, HP%: +1
  12:49:39  [mejora] resumen: nivel 0→15 · MÁXIMO · ATK: +3, Prob. Crítica: +1
  ```
  Preview de grilla emitido **1 sola vez** al entrar (12:04:39), sin repetirse tras las mejoras.

## Pendiente / follow-up

- **Lecturas intermedias ruidosas del modal abierto DESDE LA TIENDA:** `materiales cargados ·
  nivel 0 → proyectado 12` seguido de `→ proyectado 15`, y `nivel 0→4 · sin cambio de roll`
  cuando el salto real fue 0→15. El **resumen final es correcto** (la S5 manda), así que es
  cosmético en los diagnósticos intermedios — pero sugiere que la barra de nivel se lee peor en
  el modal de la tienda que en el del inventario. Mirar si vuelve a molestar.
- Relacionado: el "caso 1" de responsividad (proyectado stale) — ver
  `2026-07-10_Futuro_Latencia_GPU_Distribucion.md` §10.

Doc previo del flujo: `2026-07-10_IMPL_Mejora_Disco_S10.md`. Memoria: `project_s10_upgrade_next`.

# Inventario global de discos — vía alternativa de cosecha de badges + mapa disco→dueño

**Fecha:** 2026-06-13 · **Estado:** IDEA DE DISEÑO (diferida — depende del fix RNF-06).
**Relacionado:** Fase 5R (identidad de dueño por badge), bug RNF-06, swap de discos.

## Problema que resuelve

La cosecha actual de badges/owner-map es **per-PJ**: navegar 47 PJs × 6 slots
(`Pj_stats → Equipamiento → Slots 1-6`). Es **larga** → es exactamente lo que dispara la fuga
RNF-06 (la app llega a ~12 GB y se cuelga; hay que reiniciar cada ~10-15 PJs). Y para C.5
(~200 discos) eso es muchísima navegación.

## La observación

El **inventario global de discos** (`Documentacion/Screenshots_Triggers/Discos_Triggers/
09_Inventario_discos_general/`) muestra **TODOS los discos en una sola grilla scrolleable**
("Pistas de disco [339/3000]", ~8 columnas), y **cada disco equipado lleva su badge de dueño en
la esquina superior derecha del tile** — el MISMO avatar que ya identificamos en el grid per-PJ
(`16_discos_pj_grilla/`).

→ En vez de entrar PJ por PJ, **una sola pasada de scroll por el inventario** expone todos los
badges de dueño a la vez.

## Qué se reusa (y qué no)

| Componente | ¿Reusa? |
|---|---|
| Descriptor (HSV hist + NCC Lab) + reject-set + abstención + **voto por firma** | ✅ tal cual |
| **Librería `avatar_badge_v2.npz`** (grid-tile badge, 47/47) | ✅ **probablemente directo** — el badge del tile del inventario global es el mismo componente UI que el del grid per-PJ. **A CONFIRMAR**: el inventario global es más denso (8 cols vs 4) → el badge es **más chico** → puede necesitar matching tolerante a escala o un refuerzo de refs a esa escala (mismo riesgo que vimos con el detalle-badge). |
| Localizador | ❌ **nuevo**: `crop_grid_selected_badge` recorta solo el tile SELECCIONADO. Acá hace falta **enumerar TODOS los badges de la grilla** por frame. |
| Detección de pantalla | ❌ **nuevo estado** (Sxx) para el inventario global. |

## Dos usos posibles

1. **Cosecha rápida de refs de badge** — muchos badges visibles por frame → la librería de
   avatares crece mucho más rápido, sin navegación larga.
2. **Mapa disco→dueño desde una pasada** — localizar el badge de cada tile + leer la identidad
   del disco → armar el `equip_map` completo de un scroll. **Esquiva las pasadas largas** que
   revientan la RAM.

## Preguntas abiertas (a resolver cuando se trabaje)

- **Identidad del disco por tile.** El tile muestra ícono de set + nivel + (a veces) main, pero
  **NO los 4 substats** → el `_disc_identity` actual (set, slot, 4 substats) no se puede leer del
  tile sin abrir el detalle (lento, 1 disco a la vez). Opciones: (a) clave de dedup más liviana a
  nivel tile (set+slot+main+posición — frágil al scroll); (b) usar el inventario solo para
  **cosechar refs de badge** (uso #1) y mantener el owner-map por el flujo-ancla per-PJ; (c)
  abrir detalle por disco igual, pero con el scroll como índice. **Decisión pendiente.**
- **Equipado vs no equipado.** Solo los equipados tienen badge → saltar los sin badge (sin dueño).
- **Escala del badge.** Más chico que el del grid per-PJ → validar discriminación a esa escala.

## Validación incorporada (ventaja grande)

Ya tenemos **verdad de tierra 47/47** (`audit/equip_map_20260612.json`, 287 discos) del flujo per-PJ.
Cuando se pruebe el inventario global, **cruzar sus owners contra ese equip_map** mide el acuerdo
directo — no hace falta re-etiquetar a mano.

## Reuso hermano: pantalla de sustitución

`15_sustitucion_disco_confirmacion/` — al mover un disco entre PJs, identificar quién da/recibe
con el mismo badge → blinda contra swap equivocado. Mismo descriptor, su propio localizador.
Ver [[project_disc_equip_swap_next]].

## Orden de trabajo

**Prerrequisito: cerrar el fix RNF-06.** Incluso el scroll del inventario global dispararía OCR
continuo per-frame → leak — así que el fix de RAM va primero. Después: QA de los badges (¿rinden
en vivo?), y recién ahí evaluar este inventario global como vía de cosecha alternativa.

## Refs

- Screenshots: `Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general/`
  (global), `16_discos_pj_grilla/` (per-PJ, comparación de encuadre), `15_sustitucion_disco_confirmacion/`.
- Maquinaria: `app/core/avatar_descriptor.py`, `app/core/detector.py` (`crop_grid_selected_badge`,
  `crop_detail_badge`), `app/core/agent_identifier.py` (matchers `_badge`/`_detbadge`).
- Verdad de tierra: `audit/equip_map_20260612.json`.

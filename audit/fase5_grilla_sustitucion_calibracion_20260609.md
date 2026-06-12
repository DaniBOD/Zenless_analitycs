# Fase 5 — Hito 5.0: Caracterización del flujo grilla/sustitución (read-only)

> **Fecha:** 2026-06-09 · **Modo:** display-only (decisión del usuario, sin escritura DB)
> **Herramienta:** `tools/characterize_grid_substitution.py` (read-only; clasifica con el detector
> actual + mide señales geométricas sobre los screenshots de ejemplo).

## Resultados de la medición

| etiqueta | raw | classify | L-grid | dark-band | esperado |
|----------|-----|----------|--------|-----------|----------|
| grid/Nangong Blues(1) | S17 | S17 | 0.123 | 0.557 | grilla, candidato NO equipado |
| grid/Nangong Voz(5) | S17 | S17 | 0.121 | 0.667 | grilla, candidato equipado x otro |
| grid/Lucia 13 | S17 | S17 | 0.089 | 0.949 | grilla (con celdas EMPTY) |
| grid/Lucia 14 | S17 | S17 | 0.090 | 0.886 | grilla |
| inv/Ejemplo_1,8,9,10 | S17 | S17 | ~0.122 | 0.57–0.67 | inventario individual |
| subst/Ejemplo_1..7 | **S12** | **S12** | ~0.003 | 0.916 | modal sustitución |
| ref/Slot1_1, Slot4_1 | S17 | S17 | ~0.122 | 0.42–0.57 | (era "S17 puro" — ver abajo) |

## Conclusiones (cambian el plan)

1. **El detalle S17 "Personalización de pistas" YA ES la vista de grilla de candidatos.** Lo que
   creíamos "S17 puro por hexágono" (`14_Slots_equipamiento/Slot1_1`) tiene la **misma** estructura
   que los candidatos de `04_Inventario`: columna de thumbnails a la izquierda + panel de detalle al
   centro + hexágono a la derecha + botones `Comparar / Desequipar rápido / Desequipar|Reemplazar /
   Mejorar`. **No hay un "modo grilla" separado que detectar** → el Hito 5.1 original (detectar modo
   grilla) **se elimina**. El modelo continuo + firma del disco ya re-captura cada candidato al
   navegar la grilla.

2. **Mi discriminador "grilla izquierda" (L-grid) NO separa nada** (todos ~0.09–0.12), justamente
   porque todas las vistas S17 tienen la grilla. Descartado como señal.

3. **El CENTRO del hexágono es el W-Engine (arma), NO un retrato de PJ.** (Corrección del usuario,
   2026-06-09.) Es un feature aparte a capturar más adelante — tiene su propio RF (RF-14, W-Engines).
   **No** confundirlo con la identidad del PJ ni con el descriptor de avatar.

   Sobre el descriptor S17 (`crop_s17_assigned_avatar`, ancla cx≈0.503 a la altura de la línea
   "Nivel X/15"): empíricamente su best-match resultó **no discriminativo** ("imán Yixuan", QA
   2026-06-09) — ese hecho se mantiene y es la razón por la que en Fase 4 se adoptó trust-latch. Pero
   **NO** está verificado qué recorta exactamente en la vista de grilla: al recortar la región
   anclada sobre los screenshots estáticos (`Slot1_1`, `Ejemplo_12`) sale **fondo rayado, sin avatar
   visible**, mientras que en el QA en vivo `face` SÍ venía presente (logs con `sim`). Esa
   discrepancia (¿el avatar aparece solo para el disco equipado del latch y no para candidatos de
   grilla? ¿a otro Y?) queda **pendiente de verificar** antes de apoyarse en esa señal. No se afirma
   nada más sobre ella aquí.

4. **El indicador de "equipado-por" de un candidato** (si existe en la grilla) serían los **badges de
   retrato minúsculos** en la esquina de cada thumbnail de la grilla izquierda (visibles en Lucia
   13). Son demasiado chicos para identificación visual confiable → **no** es la vía. La fuente
   confiable del dueño es el modal de sustitución (#5).

5. **El modal de sustitución es la fuente EXPLÍCITA y confiable del dueño.** El juego declara
   textualmente *"\<PJ\> equipa actualmente \<set\> (N). ¿Deseas sustituirlo?"*. Hoy el detector lo
   da **S12** (ningún template matchea) en los 7 ejemplos. **dark-band sola NO sirve** para
   detectarlo (0.916 en modales, pero las grillas con celdas EMPTY como Lucia llegan a 0.89–0.95 →
   se solapan). Hay que detectarlo por su firma propia: la **barra de botones `Cancelar` / `Confirmar`**
   (template) y/o el **OCR del banner** (que además extrae PJ origen + set + slot).

## Plan revisado de Fase 5 (display-only)

- **~~5.1 Detectar modo grilla~~** — ELIMINADO (S17 ya es la grilla).
- **5.1 (nuevo) — Estado S20: modal de sustitución.** Template de la barra `Cancelar/Confirmar` +
  `_verify_s20` + transiciones (S17↔S20, S8↔S20). Es la pieza central: fuente confiable del dueño.
- **5.2 — Parseo del banner de sustitución.** OCR del banner → `(PJ_origen, set, slot)`. Reusa
  `_norm_key` + el resolutor de set fuzzy. Log `[sustitución] <set> (slot N) equipado por <PJ_origen>`.
- **5.3 — Tracking de candidato en grilla (display-only).** El continuo ya re-captura candidatos por
  firma; agregar log `[grilla]` y, opcional, anotación de dueño por **cruce con DB**
  (set+slot+main+substats → `agente_asignado`) mientras se navega (no autoritativo; el modal manda).
  Cuidado: NO asignar candidatos al latch a ciegas (hoy `_assign_s17_pj` lo haría) — en navegación de
  grilla eso corrompería; como es display-only/readonly no persiste, pero el log no debe mentir.

## Riesgos / notas

- **Falso "asignado al latch" en grilla:** `_assign_s17_pj` confía en el latch. Mientras se navega la
  grilla, un candidato de otro PJ se loguearía como "asignado a \<latch\>". En display-only no
  persiste, pero el log debe diferenciar *equipado del latch* vs *candidato navegado*. La señal
  honesta del dueño es el modal (5.1/5.2), no el latch.
- **Template S20 a recortar** de `15_sustitucion_disco_confirmacion/` (barra de botones, zona estable
  y de alto contraste); validar contra los 7 ejemplos + negativos (grillas Lucia con dark-band alto).

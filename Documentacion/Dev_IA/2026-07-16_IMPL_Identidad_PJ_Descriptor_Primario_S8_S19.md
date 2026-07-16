# IMPL — Identidad del PJ en Equipamiento (S8) y Habilidades (S19): descriptor PRIMARIO

**Fecha:** 2026-07-16 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only · **RF:** RF-04 §4.1 (identificación por avatar).

Elimina la dependencia de *Atributos base* (S18) para nombrar al PJ en las dos pantallas que
no muestran su nombre. El PJ ahora se reconoce **directo desde la barra deslizante superior**
con el descriptor de Fase 5R. Cierra el reclamo del usuario: *"me salta que debo ir a agent
stats cuando ese agente ya había pasado"*.

## Contexto y diagnóstico

**S8 (Equipamiento/hexágono)** y **S19 (Habilidades)** no muestran el nombre del PJ. La
identidad salía del **latch de S18** (nombre por OCR en Atributos base, arrastrado por
carry-forward); el matcher de avatar era solo un detector-de-cambio secundario. Sin latch
(o tras resetearlo al pasar por una pantalla no-detalle confirmada) → *"PJ sin identificar
(entrá a Atributos base para registrarlo)"*.

**La causa NO era falta de datos** (hallazgo del diagnóstico, contra la hipótesis inicial):

- La librería de fila (`_row` de `AgentIdentifier`, sobre `avatar_descriptor.AvatarMatcher`)
  **ya cubre los 49 PJs del roster** (355 descriptores, 4–10 refs c/u; verificado cargando
  `avatar_row_v2.npz`). Es "100% leave-one-out" y `crop_selected_avatar` separa limpio
  (mismo PJ ~0.995 / otro ≤0.72).
- El problema era de **lógica**: `_update_detail_identity` *prefería el latch* y solo corría
  el matcher al cambiar la posición del avatar; con crops pobres (esquina del slider,
  animación) el matcher se abstenía (gate RNF-02) y, sin latch, caía a "sin identificar".

> **Nota de rumbo:** `AgentIdentifier` NO es el descriptor viejo. Desde Fase 5R envuelve al
> `AvatarMatcher` robusto en **dos matchers especializados** (`_row` para el avatar de fila
> S8/S18/S19, `_badge` para el badge de dueño de la grilla S17) — comparar *like-with-like*
> es lo que da robustez. El `_badge` va sembrado con los `-ico` día-1; el `_row` se llena
> por cosecha vía latch, y ya está completo.

## 1. Descriptor primario con votación multi-frame (`monitor._update_detail_identity`)

Reescrito. El descriptor decide la identidad; el latch de S18 pasa a **opcional**.

- **Votación multi-frame:** con el avatar visible se corre el matcher en cada pasada del loop
  rápido (10 fps) y se **acumula confianza por PJ**; la identidad se fija al juntar
  `_DETAIL_MIN_SAMPLES = 2` matches confiables → gana el **argmax**. Antes se commiteaba el
  **primer** match y el early-return lo dejaba **clavado**: un frame malo quedaba fijo.
  (2 muestras ≈ 0.2 s al loop rápido → robusto y responsivo.) Espejo del warmup del dueño S17.
- **Latch de S18 honrado** si existe en la ranura confirmada (etiqueta `heredado`), pero ya
  no es requisito.

## 2. Dos anclas: identidad confirmada vs votación (fix del QA en vivo)

**Hallazgo del QA (caso 3, barra auto-oculta):** al ocultarse, la barra **no** devuelve
"oculto" (`None`) sino una **posición ESPURIA** del highlight desvaneciéndose. Con una sola
ancla eso se leía como *"el avatar se movió → cambió el PJ"* → se descartaba la identidad y
el matcher ya no podía leer el avatar borroso → `PJ=?`.

**Fix:** dos anclas separadas —
- `_agent_anchor_x` = dónde se **confirmó** la identidad,
- `_detail_vote_x` = dónde se está **votando**.

Así un parpadeo del highlight no se confunde con un cambio real de PJ. Y cuando el matcher
no puede confirmar, **se SOSTIENE al último reconocido** (`source="sostenido"` → el log dice
*"sostenido del último reconocido"*) en vez de perderlo — nunca se borra un PJ ya logrado
(RNF-02: preferir sostener a mentir). `_detail_confirmed_source` recuerda la etiqueta real
("avatar"/"heredado") para **restaurarla** al re-confirmar la ranura (no queda pegada en
"sostenido").

## 3. Mensaje (`controller._on_agent_detail_from_monitor`)

S18 ya no es la fuente → el aviso de no-identificado deja de mandar ahí:
`PJ sin identificar (entrá a Atributos base para registrarlo)` →
`PJ sin identificar (esperá a que la barra de personajes esté visible)`.

## Verificación

- **Unit** (`test_detail_identity.py`, nuevo): fresh-entry identifica por avatar · la votación
  ignora un 1er frame malo (red→green: el bug real) · barra oculta sostiene · switch a otro PJ
  re-identifica · **auto-hide con posición espuria sostiene al último reconocido** ·
  re-confirmar la ranura restaura la etiqueta "avatar" · abstención sin latch → sin identificar.
- **Regresión:** `test_monitor_s18_dispatch.py` / `test_s17_avatar_assignment.py` /
  `test_agent_identifier.py` verdes, incluidos `hereda_identidad_si_mismo_avatar`,
  `sostiene_latch_si_cambio_avatar_y_matcher_falla` y `retroceso_s17_a_s8_hereda_pj` (el caso
  histórico de mis-ID al volver). `nombra_pj_via_matcher_de_avatar` ajustado: la votación pide
  2 muestras, que el loop rápido provee (se simula una pasada antes del dispatch de cadencia).
- **Suite:** **841 passed**.
- **QA en vivo 2026-07-16:** identificó sin pasar por S18 a Velina, Zhao, Lucía, Evelyn,
  Pan Yinhu, Ju Fufu, Yanagi, Zhu Yuan, Qingyi, Jane, N.º 11, César, Burnice, N.º 0: Anby —
  todos "por avatar". Switch entre PJs, vuelta S17→S8 y auto-hide: OK. **Los 4 casos pasan.**

## Riesgo asumido (y por qué es aceptable)

Re-identificar por avatar en S8/S19 ya se había intentado y "mis-identificaba al volver" (de
ahí la preferencia por el latch). Se reabre a propósito, mitigado con: votación multi-frame +
gate de abstención del descriptor + el caso especial S17→S8 (mismo PJ, se hereda) preservado
en el dispatch. Validado en vivo sin mis-ID.

## Pendiente / follow-up

- La barra **auto-oculta**: si nunca se hace visible durante la visita, el PJ queda "sin
  identificar" (mensaje suavizado). No se puede forzar la UI (RNF-03) — es el límite honesto.

Doc gemelo en memoria: `project_menu_personajes_recon` / `project_fase5R_identidad_grilla`.

# L.1 — Diagnóstico del imán del detalle-badge (2×2) · 2026-06-17 · PRE-FIX

> Read-only. Aísla si el imán del detail-matcher viene de la LIBRERÍA runtime o del
> CROP de query en vivo. Métrica de imán: pocos PJs predichos distintos y top-1 bajo con
> concentración en uno. GT de ejemplos en vivo = etiqueta del GRID-matcher (0-wrong verificado).
> **Este reporte fija el ESTADO PRE-FIX** (crop fijo). La validación post-fix (Hough) está en
> `audit/detbadge_refine_validation_20260617.md`. Reproducir el pre-fix: `git stash` del cambio a
> `crop_detail_badge` + librería backup `avatar_detbadge_v2.backup_preL2b_20260617.npz`.

## Composición de la librería runtime PRE-FIX (`avatar_detbadge_v2.npz`)
- refs totales: **316** · PJs: **47**
- refs/PJ: 1ref×1PJ, 3ref×2PJ, 6ref×2PJ, 7ref×41PJ, 10ref×1PJ
- Nangong Yu: **7 refs** (no sobre-representado) → el imán **no** es por desbalance de conteo.

## Resultados 2×2 PRE-FIX (crop fijo `_DET_R_F=0.019·W`, guard naming = 0.80)

| Caso | Librería | Query | top-1 | WRONG | distintos | dominante |
|---|---|---|---|---|---|---|
| **A** | limpia (harvest) | harvest LOO | 91% (156/171) | 2% (3) | 42 | soukaku 3% |
| **B** | RUNTIME | harvest limpio (GT) | 79% (135/171) | 6% (11) | 41 | Alice 3% |
| **C** | limpia (harvest) | EN VIVO (16_ejemplos) | **20% (2/10)** | **30% (3)** | **3** | **gatillo 50% ⚠️** |
| **D** | RUNTIME | EN VIVO (control QA) | **20% (2/10)** | **40% (4)** | **3** | **Nangong Yu 50% ⚠️** |

- A/B wrongs aleatorios ×1 (varios falsos por encoding: `n.º11`↔`N.º 11`, `billy`↔`Billy Estelar`).
- C wrongs: Vivian→nangongyu, Orfia y Magas→gatillo, Sporos→gatillo.
- D wrongs: Vivian→Nangong Yu, Yuzuha→Nangong Yu, Orfia y Magas→Gatillo, Sporos→Gatillo.

## Veredicto
**El imán es del CROP DE QUERY EN VIVO, no de la librería:** A/B (query limpio) sanos con
cualquier librería (41–42 PJs distintos); C/D (query en vivo) colapsan a 3 PJs con cualquier
librería. ⇒ no es librería sucia ni desbalance.

- imán en B (lib runtime, crop limpio): no
- imán en C (lib limpia, crop vivo): **SÍ** ⚠️
- imán en D (runtime+vivo, control): **SÍ** ⚠️

## Mecanismo (confirmado visualmente)

Inspección de `Ejemplo1_14` (GT grid = **Vivian**, det predijo **Nangong Yu** @0.81), ver
`audit/detbadge_magnet_diag/CMP_ex1_14.png` (`[grid, det, Nangong-Yu-ico, Vivian-ico, Trigger-ico]`):
- El crop del detail **está bien localizado**: es la cara de **Vivian** (pelo plateado, ojos rojos),
  idéntica al grid-crop y al `Vivian-ico`. **NO** es el agente de la página, **NO** es basura, **NO**
  está descentrado.
- ⇒ El imán es una **falla de discriminación del descriptor sobre el avatar chico**, con wrongs a
  **conf 0.81–0.94** → **pasan el guard 0.80** → violan RNF-02 (lo más peligroso).

**Driver = fondo compartido por página.** El crop fijo (96 px) deja al avatar (~55 px) rodeado de
**fondo oscuro a rayas idéntico en todos los discos de la misma página**. El descriptor (40% hist
HSV + plantilla Lab) se **diluye con ese fondo común** → los crops de una página se agrupan → matchean
al ref **cosechado en esa misma página** (mismo fondo). Por eso el imán **se correlaciona con la
página**: `Ejemplo1_*` (página Nangong Yu) → "Nangong Yu"; `Ejemplo2_*` (página Gatillo) → "Gatillo".
A/B no lo expusieron porque en el harvest la página == el dueño (disco equipado) → agarrar el fondo
daba la respuesta trivialmente correcta.

## Implicación (corrige el plan)
- **L.2a (re-cosechar por librería sucia) DESCARTADO** — la librería discrimina bien (caso B).
- **L.2b = refine del crop a la cara, excluyendo el fondo.** NO usar el bbox del blob saturado
  (mergea avatar+fondo, ~202 px). Localizar el **círculo real del avatar** (Hough) y recortar ajustado.
  Reconstruir refs con el mismo encuadre (cambio de dominio, no de etiquetas). → **validado en
  `detbadge_refine_validation_20260617.md`.**

## Reproducir
`tools/diag_detbadge_magnet.py` (read-only). Artefactos visuales en `audit/detbadge_magnet_diag/`.

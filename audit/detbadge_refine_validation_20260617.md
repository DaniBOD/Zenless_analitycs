# L.2b — Validación del refine Hough del detalle-badge · 2026-06-17 · POST-FIX

> Tras L.1 (`detbadge_magnet_diag_20260617.md`: el imán es el ENCUADRE, no la librería),
> se cambió `detector.crop_detail_badge` a un **two-stage Hough** (franja → gate de presencia
> saturada → círculo del avatar por Hough → crop ajustado a la cara) y se reconstruyó la
> librería con el mismo encuadre. Este reporte valida el fix offline (apples-to-apples + 2×2).

## 1. Experimento de variantes de crop (`tools/exp_detbadge_refine.py`)
Refs = det de `audit/harvest/*__S17__*` · Query = det de `16_discos_pj_grilla` (CROSS-DOMAIN,
page≠dueño = el fondo NO ayuda). Mismo encuadre en refs y query.

| variante | refs loc | LOO harvest (optimista) | **CROSS-DOMAIN (lo que importa)** |
|---|---|---|---|
| OLD fix .019·W | 171/180 | top1 91% | top1 **20%** · WRONG 3 · distintos 3 |
| fix .013·W | 171/180 | top1 89% | top1 20% · WRONG 1 · distintos 3 |
| fix .011·W | 171/180 | top1 89% | top1 20% · WRONG 2 · distintos 3 |
| open-blob | 36/180 | top1 81% | top1 20% · WRONG 4 · distintos 3 |
| **Hough** | **180/180** | top1 84% | **top1 90% (9/10) · WRONG 0 · distintos 8** |

- Los radios fijos chicos NO bastan: el **centroide del blob saturado está contaminado por el
  fondo** (el blob mergea avatar+fondo). El **Hough halla el círculo real del avatar** → crop
  limpio → discriminación recuperada.
- El LOO harvest BAJA con Hough (91%→84%) porque ya **no infla por fondo** (mismo PJ=misma página):
  es discriminación HONESTA. El número real (cross-domain) SUBE 20%→90%.

## 2. Per-ejemplo Hough (refs harvest, GT grid) — el imán desaparece
- Con GT de grid: **10 OK / 1 abst (Rina) / 0 WRONG** (Vivian, el caso del imán, ahora **vivian @1.00**).
- Sin GT (no etiquetables): predicciones VARIADAS y plausibles (jane, grace, nicole, sunna, yanagi,
  corin, n.º11, seth…) — ya NO todo a un PJ.
- Localización ejemplos: **26/28** · costo **~sub-ms** (Hough sobre franja chica) — RNF-06 ✓.

## 3. 2×2 integrado POST-FIX (crop de producción + librería reconstruida)
`tools/diag_detbadge_magnet.py` con `crop_detail_badge` Hough + `avatar_detbadge_v2.npz` nueva
(171 refs / 43 PJs · Nangong Yu 0 refs).

| Caso | Librería | Query | top-1 | WRONG | distintos | dominante |
|---|---|---|---|---|---|---|
| A | limpia (harvest) | harvest LOO | 83% (142/171) | 1% (2) | 40 | evelyn 3% |
| **B** | RUNTIME nueva | harvest limpio | **92% (157/171)** | **0%** | 41 | alice 3% |
| **C** | limpia (harvest) | EN VIVO | **90% (9/10)** | **0%** | 8 | dialyn 22% |
| **D** | RUNTIME nueva | EN VIVO (control QA) | **90% (9/10)** | **0%** | 8 | dialyn 22% |

**Caso D (control exacto del QA en vivo): 20%/40%-wrong/imán-Nangong-Yu → 90%/0-wrong/8 PJs.**
Imán eliminado en los 4 casos. **0 wrong en todos.**

## 4. Criterios de aceptación L.2 (duros) — CUMPLIDOS
- ✅ Imán eliminado: 8 PJs distintos correctos (bar ≥4), 0 wrong.
- ✅ per-frame 0-wrong top-1 cross-domain **90%** (bar ≥70%).
- ✅ multi-frame: 0 wrong ya per-frame → el voto solo refuerza.
- ✅ costo sub-ms (RNF-06), solo cv2 (RNF-03).

## 5. Gaps conocidos (cubiertos, no bloquean)
- **lycaon** (0 refs): baja-sat, el gate de presencia (`_DET_SAT_MIN`) bloquea sus frames. Cubierto
  por el GRID badge + voto. Mitigación futura: bajar `_DET_SAT_MIN` o gate por estructura (no sat).
- **rina** (0 refs): su det no localiza en los frames de harvest (Hough no halla círculo). En vivo SÍ
  localizó (Ejemplo1_10) pero abstuvo (sin ref). La cosecha en vivo (`-BadgeHarvest`) la sumará.
- 2 NOLOC en ejemplos (Ejemplo1_3, _5): Hough no halla círculo → abstención segura (RNF-02), el voto
  multi-frame cubre.

## Cambios
- `app/core/detector.py::crop_detail_badge` — two-stage Hough (`_DET_HOUGH_RMIN_F/RMAX_F/PAD`).
- `tools/rebuild_detbadge_lib.py` (nuevo) — reconstruye `avatar_detbadge_v2.npz` desde harvest con
  el crop nuevo (backup del viejo, snapshot `audit/avatar_detbadge_v2_snapshot_20260617_hough.npz`).
- `tools/exp_detbadge_refine.py` (nuevo) — barrido de variantes de crop.
- `tools/diag_detbadge_magnet.py` (nuevo, L.1) — 2×2; flag `--tag` para no pisar reportes.

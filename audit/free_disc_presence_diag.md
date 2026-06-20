# L.7.1 — Diagnóstico presencia de badge: libres vs equipados (2026-06-20)

## Objetivo
Encontrar una métrica HSV/geométrica que separe "hay avatar de dueño" (disco EQUIPADO) de
"esquina sin avatar / arte / candado" (disco LIBRE) en el crop de esquina del tile seleccionado
del grid S17, para gate-ear `crop_grid_selected_badge` (L.7.2) y dejar de votar fantasmas (el falso
"Cissia" en un disco libre, QA 2026-06-20).

## Datos
- **Equipados (GT):** 176 frames `audit/harvest/*__S17__*` + 30 `14_Slots_equipamiento` + 12 `04_Inventario` = **218 frames con tile**, todos con avatar de dueño.
- **Crops pre-recortados:** `audit/grid_diag` (841 esquinas volcadas en QA). Inspección: los `badge_none_*` (matcher abstenido) **también son avatares reales** (p.ej. `0341da15_..._none_0.92` = cara rubia nítida) — NO son discos libres. El matcher abstuvo por margen/reject, no por ausencia de cara.
- **Libres:** ❌ **cero frames offline.** Todas las capturas S17 existentes son de discos equipados (el tile seleccionado siempre tiene dueño). Es lo que se screenshotea.

## Resultados — distribución sobre equipados (218 con tile)

| métrica | min | mediana | max | cobertura |
|---|--:|--:|--:|--|
| `hough_circle` (anillo avatar, r 0.30–0.60·h) | — | — | — | **218/218 ≥ 1** |
| `sat_blob_area` (blob sat>50) | 245 | ~2100 | 3495 | 218/218 ≥ 245 |
| `sat_mean` | 25 | ~65 | 111 | — |
| `detail_notnone` (crop_detail_badge ≠ None) | — | — | — | 209/218 (~96%) |

**Hallazgo:** el **anillo del avatar (Hough)** está presente en el **100%** de los equipados, junto con
un blob saturado ≥ 245 px. Es la señal universal de "hay avatar".

## Conclusiones para el diseño
1. **Gate del grid (L.7.2):** declarar "badge presente" sólo si el crop de esquina tiene
   `hough_circle ≥ 1` **Y** `sat_blob_area ≥ _GRID_BADGE_MIN_AREA`. Umbral `_GRID_BADGE_MIN_AREA = 150`
   (margen bajo el piso equipado de 245 → **0 regresión**: 218/218 equipados pasan). Una esquina sin
   avatar (arte/candado/oscuro) no tiene anillo + blob simultáneos.
2. **Lado LIBRE no validable offline** (sin frames). El gate del grid es **conservador + defensa en
   profundidad**; la corrección de fondo es el **árbitro del detail** (`crop_detail_badge` ya abstiene
   en libres por su gate de presencia, L.2b). RNF-02 se garantiza por el árbitro aunque el gate del
   grid dejara pasar algún borde → validar el lado libre en QA en vivo (`DANIBOD_GRID_DIAG`) y ajustar.
3. **El detail es el árbitro libre/equipado** (96% loc en este set, ~100% en QA), desacoplado de la
   identidad: detail-ausente consistente ⇒ LIBRE; detail-presente ⇒ equipado → identificar.

## Próximo
L.7.2 (gate grid) + L.7.3 (árbitro detail) + L.7.4 (latencia). Validación del lado libre: QA en vivo.

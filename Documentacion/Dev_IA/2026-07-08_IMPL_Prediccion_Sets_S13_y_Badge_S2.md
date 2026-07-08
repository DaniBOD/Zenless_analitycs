# IMPL — Predicción de sets (S13) + captura slot/set por badge (S2)

**Fecha:** 2026-07-08 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only (no persiste, no puntúa).
**Plan de origen:** [`2026-07-08_PLAN_Prediccion_Sets_S13_y_Badge_S2.md`](2026-07-08_PLAN_Prediccion_Sets_S13_y_Badge_S2.md).
**Estado:** implementado + verificado OFFLINE (704 tests verdes). QA EN VIVO pendiente (requiere el juego).

---

## Qué se hizo

Se cerró el loop **predecir → confirmar** del farmeo, en dos fases, ambas con TDD:

### Fase A — S13 (predicción por OCR)
- **`app/resources/farm_nodes.toml`** (nuevo): mapa de los 14 nodos → 2 sets por `nombre_en`.
- **`app/core/farm_nodes.py`** (nuevo): `FarmNodeCatalog` — matchea el título del nodo (OCR)
  insensible a tildes/ñ/mayúsculas (exact → substring → difflib con guarda de ambigüedad, mismo
  criterio que `sync_equip._resolve_set_id`) y resuelve `nombre_en → set_id` vía `DiscSetRepo`.
- **`app/core/farm_session.py`** (extendido): `set_prediction` / `predicted` — guarda la
  predicción (nodo + sets) con la misma ventana temporal del gate de farmeo.
- **`app/core/monitor.py`**: handler `_process_s13_node_title` (OCR del título → predicción →
  guarda en `FarmSession` → diagnóstico). Latch armado **solo al predecir con éxito** (más
  robusto que el patrón de `_s2_reported`: el detector puede confirmar S13 en un frame de
  transición sin título renderizado).
- **`app/ui/controller.py`**: instancia y cablea el catálogo.

### Fase B — S2 (captura slot + set por badge)
- **`app/core/asset_resolver.py`** (extendido): `set_package_badge_paths(nombre_en)` +
  `SET_BADGES_DIR` (los 3 tiers S/A/B en `Set-Discos_Package_Logo/`).
- **`app/core/set_badge_matcher.py`** (nuevo): `SetBadgeMatcher` — wrapper sobre `AvatarMatcher`.
  `crop_package_disc` aísla el disco central (descarta rareza/marca de agua/marco → invariante al
  tier); los 3 tiers = multi-ref de la misma clase. `identify(disc, candidatos)` restringe a los
  2 sets predichos + abstención por conf/margen.
- **`app/core/parser_s2.py`** (extendido, sin tocar conteo/verificación): `tile_boxes` (grilla
  4×2, tiles con franja de rareza), `crop_tile_center`, `crop_tile_slot`, `read_tile_slot`
  (OCR del dígito con upscale ×3). Geometría calibrada contra los franjas de rareza de los 7
  fixtures S2 (todos exponen los 8 tiles: cols cx≈0.722/0.787/0.852/0.917, filas cy≈0.494/0.640).
- **`app/core/monitor.py`**: `_process_s2_tiles` — por tile emite `[disco] slot N · <set> (conf)`
  restringido a la predicción de S13; sin S13 previo → abstención.
- **`app/ui/controller.py`**: instancia y cablea el matcher (carga ~1.3 s al arranque).

---

## Verificación

- **Offline: 704 passed** (suite completa, ~6 min). Tests nuevos:
  `test_farm_nodes.py` (14 títulos + ruido tildes/ñ + resuelve 28 EN), `test_farm_session.py`
  (+predicción), `test_monitor_s13.py`, `test_asset_resolver.py` (+package badges),
  `test_set_badge_matcher.py` (**leave-one-out sobre los 81 badges: separa los 2 sets de cada
  nodo ≥90%** tratando S/A/B como misma clase), `test_parser_s2_tiles.py` (8 tiles en los 7
  fixtures), `test_monitor_s2_tiles.py`.
- **DB viva**: los 28 `nombre_en` resuelven a `set_id` (0 unresolved). La copia de `build/dist`
  estaba vieja (26 sets) — se ignoró.

## Pendiente / riesgos (a validar en vivo)

1. **QA EN VIVO** (`tools/qa_launch.ps1 -FromSource -IdDiag -ReadOnly`): S13 → log
   `[farmeo] nodo: … → predice A / B`; S2 → `[disco] slot N · <set> (conf)`; confirmar
   detectados ⊆ predichos. Diagnóstico extra con `[s13_diag]` / `[s2_diag]` (`-IdDiag`).
2. **Calibración de ROIs** (probable, solo se validan en vivo):
   - `_S13_TITLE_ROI` (monitor) = `(0.43, 0.18, 0.35, 0.06)` — tentativo, ajustar contra el título real.
   - `crop_tile_center` (parser_s2): el arte del disco in-game es chico y con overlays (hexágono
     de slot + badge RARITY) → el gap render-package vs tile puede degradar el matcher.
3. **Fallback aceptado (§8.1 del plan)**: si el matcher falla en vivo → cosechar tiles reales de
   S2 como refs `.npz` (patrón `AvatarMatcher.save/load_merge`).
4. **Branch & Blade Song sin package badge** → nodo "Dueto monstruoso" degrada a 1 set + candidato.
5. **Latencia (RNF-06)**: el pase por disco es 1× por entrada a S2 (no por frame); ~8 OCR de slot
   → medir en vivo si se acerca a 500 ms.

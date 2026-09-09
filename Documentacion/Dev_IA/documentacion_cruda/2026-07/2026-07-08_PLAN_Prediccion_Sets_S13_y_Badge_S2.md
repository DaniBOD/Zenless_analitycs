# PLAN — Predicción de sets a farmear (S13) + captura slot/set por badge (S2)

**Fecha:** 2026-07-08 · **Estado:** DISEÑO CERRADO, sin implementar · **Branch:** `feature/5R-detbadge-matcher`
**Modo:** display-only (no persiste, no puntúa) — coherente con la fase de farmeo actual.

> Doc autocontenido para retomar en sesión nueva. No requiere re-explorar: tiene paths, líneas de
> código reusable, el mapeo completo, y los folders de assets/screenshots para calibrar.

---

## 1. Contexto / por qué

En el flujo de farmeo, **hoy**:
- **S13** (selección de nodo a farmear) se detecta (`s13_seleccion_set_farmeo.png`, umbral 0.70) pero
  es `NON_CAPTURE`: cae al `else` de `_dispatch_state`, no se lee nada.
- **S2** ("Resultados del desafío") solo cuenta discos S por color (`parse_s2_resultado`, display-only
  gate); **no captura slot ni set**.

**Objetivo:** cerrar el loop **predecir→confirmar**:
1. En **S13**, OCR del título del nodo → predecir los **2 sets** que dropea ese nodo (mapa fijo, §4).
2. En **S2**, por cada tile: leer el **slot** (número arriba-izq.) y reconocer el **set** por su
   **badge/render** (NO por texto), **restringido a los 2 sets predichos en S13** → decisión binaria
   + rechazo. Mucho más robusto que open-set contra 28 sets ("enfoque C": el flujo da contexto, el
   contenido confirma — mismo criterio del farmeo, ver [[project_farmeo_captura]]).

---

## 2. Decisiones cerradas (con el usuario, 2026-07-08)

| Tema | Decisión |
|---|---|
| Storage del mapa título→2 sets | **Archivo de datos** `app/resources/farm_nodes.toml` (no DB; feature display-only, iterable sin migración; RNF-01 no aplica). |
| Estrategia matcher S2 | **Restringido a los 2 sets predichos por S13**. Si no hubo S13 (nodo desconocido / re-farmeo) → abstención o open-set best-effort. |
| Referencias de badge | **Package renders** provistos por el usuario (§5). Son el arte del disco tal cual en el tile, tiers S/A/B. Objetivo = reconocer **set, no rareza** → 3 tiers como multi-ref de la MISMA clase; descriptor enfocado en el **disco central** (recorta tier-badge / marca de agua / marco). |

---

## 3. Diseño (6 piezas)

### Pieza 1 — Catálogo de nodos (S13)
- **`app/resources/farm_nodes.toml`** (nuevo): los 14 nodos de §4, cada uno título ES + 2 sets por
  `nombre_en` (estable para resolver a `set_id`).
- **`app/core/farm_nodes.py`** (nuevo) — `FarmNodeCatalog`:
  - Índice por **título normalizado** (lower + sin tildes + `ñ→n`). Reusar `_norm_key` de
    `app/core/sync_equip.py:525`.
  - `match_title(ocr_text) -> FarmNode | None`: exacto → substring → `difflib.get_close_matches`
    con guarda de ambigüedad (mismo patrón que `_resolve_set_id`, `sync_equip.py:509-558`).
    **CUIDADO tildes/Ñ** (títulos: "La torre y el cañón", "Puños y balas", "Engaños y baluartes").
  - Resuelve cada set EN → `set_id` vía `DiscSetRepo.get_all()` (`app/db/repositories.py:166`, match
    por `nombre_en`). **Warn** al cargar si algún EN no resuelve (RNF-02).

### Pieza 2 — Matcher de badges (reusa infra 5R)
- **`app/core/set_badge_matcher.py`** (nuevo) — `SetBadgeMatcher`, wrapper fino sobre `AvatarMatcher`
  (`app/core/avatar_descriptor.py`; su docstring ya dice "reusable a íconos de discos").
  - **Refs** desde `Documentacion/Interfaz/Set-Discos_Package_Logo/` (§5): filename → `nombre_en`
    (quitar sufijo `_S/_A/_B`, url-decode `%27→'`, `_→espacio`). Clase = set; 3 tiers como
    multi-ref (`AvatarMatcher.add_reference`, distancia = min sobre refs → invariante a rareza).
  - **Center-crop** helper: recorta el disco central (descarta el badge "RARITY S/A/B" abajo-der.,
    la marca de agua a la izquierda, y el marco). Aplicar el MISMO center-crop al tile de query.
  - `identify(tile_bgr, candidate_set_ids) -> MatchResult`: restringe a las clases candidatas +
    reject-set; usa la abstención existente (`_MIN_CONF`, `_MIN_MARGIN` en `avatar_descriptor.py`).
  - Persistencia `.npz` (patrón `save`/`load_merge`) solo si luego se cosechan tiles reales; v1
    construye refs en memoria al arrancar.
  - **AvatarMatcher API relevante** (`app/core/avatar_descriptor.py`): `build_descriptor` (l.136),
    `descriptor_distance` (l.186, pesos `_W_HIST/_W_NCC/_W_REG=0.40/0.45/0.15`), `class AvatarMatcher`
    (l.207), `add_reference` (l.258), `match` (l.332), `MatchResult` (l.112).

### Pieza 3 — Geometría de tiles S2
- **`app/core/parser_s2.py`** (extender; NO tocar conteo/verificación actuales):
  - `tile_boxes(frame) -> list[TileBox]`: subdividir la región WIDE (`_GRID_X_WIDE=0.685-0.997`,
    `_GRID_Y_WIDE=0.40-0.62`, ya en el archivo l.29-30) en **grid 2×4**; quedarse con tiles con
    **franja de rareza** (reusar la lógica de `count_reward_rarity_strips` l.92 por tile).
  - `crop_tile_center(frame, box)` (→ matcher) y `crop_tile_slot(frame, box)` (→ dígito de slot,
    esquina sup-izq.).
  - Intactos: `count_gold_disc_strips` (l.67), `count_reward_rarity_strips` (l.92), `_grid_region`
    (l.59), regiones NARROW/WIDE, `_verify_s2` (en detector).

### Pieza 4 — Contexto compartido S13→S2
- **`app/core/farm_session.py`** (extender, 40 líneas hoy): agregar `predicted_sets:
  list[(set_id,nombre)]` y `predicted_node`. Set en el handler S13; leído en S2; limpiar al expirar
  la ventana (`_FARM_WINDOW_S=600`, l.22). No rompe el gate temporal actual (`on_state` l.32,
  `is_armed` l.37).

### Pieza 5 — Handlers en el monitor
- **`app/core/monitor.py`** (`_dispatch_state`, `if/elif` por `state.code`, l.767):
  - **Nuevo `elif state.code == "S13"` → `_process_s13_node_title`**: one-shot (flag `_s13_reported`,
    patrón de `_s2_reported` l.888-890). OCR del título (ROI ~`x[0.43,0.78] y[0.18,0.24]`,
    `self._ocr.text(crop, psm=7, lang="spa")`; patrón `_extract_slot_from_roi` en `detector.py:1074`)
    → `catalog.match_title` → guardar `predicted_sets` en FarmSession → diagnóstico vía
    `self._on_diagnostic(msg)` (l.907) + `log.info`.
  - **Extender `_process_s2_resultado`** (l.883-911): además del resumen actual, iterar `tile_boxes`;
    por tile → slot (OCR dígito, upscale ×3 como `_rescue_slot_s3` en `parser_disc_s3.py:71-95`) +
    set (`SetBadgeMatcher.identify(center, predicted_set_ids)`); emitir línea display-only por disco:
    `slot N · <set> (conf)`, `contexto=flujo|tentativo` según `FarmSession.is_armed` (l.902). **No
    persiste ni puntúa.**
- **`app/ui/controller.py`**: instanciar `FarmNodeCatalog` + `SetBadgeMatcher` una vez e inyectarlos
  al `Monitor` (patrón de `farm_session=` l.141, `owner_tiebreaker=`).

### Pieza 6 — Asset resolver
- **`app/core/asset_resolver.py`**: agregar `set_package_badge_paths(nombre_en) -> list[Path]` (los 3
  tiers en `Set-Discos_Package_Logo/`, misma convención url-encode `%27` que `set_logo_path` l.124).

---

## 4. Mapa nodo → 2 sets (14 nodos) — para `farm_nodes.toml`

| Título nodo (ES) | Set A (ES / EN badge) | Set B (ES / EN badge) |
|---|---|---|
| El piloto y el meca rebelde | Salón huracanado / Wuthering Salon | Firmamento llameante / The Sky Ablaze |
| Cuadriga sometedragones | Conejo en el país de las maravillas / Bunny in Wonderland | Diario de una prisionera / Notes From the Chained |
| Engaños y baluartes | Balada de aguas blancas / White Water Ballad | Aria radiante / Shining Aria |
| La ley de hierro y los rebeldes | Floración del alba / Dawn's Bloom | Nana a la luz cenicienta / Moonlight Lullaby |
| De boca y espada | Fábula yunkui / Yunkui Tales | Monarca del pináculo / King of the Summit |
| Hidalgo y escudero | Armonía umbría / Shadow Harmony | Melodía de Faetón / Phaethon's Melody |
| Dueto monstruoso | Balada de la rama y la espada / Branch & Blade Song **(sin badge)** | Voz astral / Astral Voice |
| El cazador y la bestia | Jazz caótico / Chaos Jazz | Punk primitivo / Proto Punk |
| Colmillo y hacha | Blues libre / Freedom Blues | Metal Polar / Polar Metal |
| El loco y el adepto | Tecno tetraodóntido / Puffer Electro | Metal infernal / Inferno Metal |
| La torre y el cañón | Tecno pícido / Woodpecker Electro | Rock espiritual / Soul Rock |
| Cazador y sabueso | Disco sacudeestrellas / Shockstar Disco | Metal eléctrico / Thunder Metal |
| Puños y balas | Punk hormonal / Hormone Punk | Metal colmilludo / Fanged Metal |
| Un monstruo y un visitante | Jazz oscilante / Swing Jazz | Metal caótico / Chaotic Metal |

*(28 sets, 2 por nodo. El EN es la clave para resolver `set_id` y para matchear el filename del badge.)*

---

## 5. Assets de referencia (badges)

**Folder:** `Documentacion/Interfaz/Set-Discos_Package_Logo/` — **81 `.webp` = 27 sets × 3 tiers** (S/A/B).
Convención de filename: `Drive_Disc_<Nombre_EN>_<S|A|B>.webp`, con url-encode (`'`→`%27`, espacio→`_`).
Ej.: `Drive_Disc_Dawn%27s_Bloom_S.webp`, `Drive_Disc_Phaethon%27s_Melody_A.webp`.

**Naturaleza:** son el **render del disco** (el arte que aparece en el tile de S2), NO el emblema
redondo. Cada uno tiene: disco central (diseño del set, invariante a rareza), badge "RARITY S/A/B"
abajo-der. (varía por tier → descartar), y una marca de agua a la izquierda (descartar). Por eso el
descriptor debe enfocar el **centro**.

**Falta 1 set:** *Balada de la rama y la espada* (Branch & Blade Song) — endpoint caído al descargar.
→ Nodo "Dueto monstruoso" degrada a 1 set conocido (Astral Voice) + candidato sin badge. Re-descargar
cuando el endpoint se reponga.

> NO confundir con `Documentacion/Interfaz/Set_Discos_Logo/` (emblemas redondos, para display en
> toast/panel vía `asset_resolver.set_logo_path`). Ese folder NO sirve para el matcher de S2.

---

## 6. Infra reusable (paths + líneas exactas)

| Qué | Dónde | Uso |
|---|---|---|
| Descriptor/matcher 5R | `app/core/avatar_descriptor.py` (`AvatarMatcher` l.207) | base de `SetBadgeMatcher` |
| Resolver set fuzzy + `_norm_key` | `app/core/sync_equip.py:509-558`, `:525` | resolver EN→id, normalizar títulos |
| Repos sets | `app/db/repositories.py` (`DiscSetRepo` l.123, `get_all` l.166) | id ↔ nombre_en |
| OCR de ROI | `app/core/detector.py:1074` (`_extract_slot_from_roi`), ROIs norm. l.31-32 | título S13 |
| Backend OCR | `app/core/ocr_backend.py` (`text(img, psm, lang)`), instancia `self._ocr` en monitor | — |
| Upscale de slot | `app/core/parser_disc_s3.py:71-95` (`_rescue_slot_s3`, resize ×3 INTER_CUBIC) | dígito slot S2 |
| Geometría grid S2 | `app/core/parser_s2.py` (`_grid_region` l.59, WIDE l.29-30, strips l.92) | tile_boxes |
| Gate de flujo | `app/core/farm_session.py` (`FarmSession`) | contexto S13→S2 |
| Logo path (convención %27) | `app/core/asset_resolver.py:111,124` | `set_package_badge_paths` |
| Dispatch handlers | `app/core/monitor.py:767` (`_dispatch_state`), `_process_s2_resultado` l.883 | handlers S13/S2 |

---

## 7. Screenshots para calibrar (ya en el repo)

- **S13** (título + card de nodo con 2 emblemas): `Documentacion/Screenshots_Triggers/Discos_Triggers/13_Seleccion_set_farmeo/Ejemplo_1..5.png` → calibrar ROI del título.
- **S2** (grid 2×4, slot arriba-izq. por tile, franja de rareza): `Documentacion/Screenshots_Triggers/Discos_Triggers/01_Pantalla_Resultado_Desafio/Ejemplo_1..7.png` → calibrar geometría de tiles + slot-OCR + validar matcher offline.

---

## 8. Riesgos

1. **Render package vs tile in-game**: distinta resolución/compresión + marca de agua en los `.webp`.
   Mitiga: center-crop + restricción a 2 candidatos. Si falla en vivo → **cosechar tiles reales de S2**
   como refs (patrón avatar, `.npz`). *(Camino aceptado por el usuario.)*
2. **Branch & Blade Song sin ref** → nodo "Dueto monstruoso" con 1 set + candidato.
3. **S2 parcial**: el grid colapsa (▼) + desmontaje automático → lote incompleto; slot en dígitos
   chicos → upscale.
4. **Latencia RNF-06 (<500 ms)**: hasta 8 tiles × (OCR dígito + match 2-cand). Match barato; medir con
   `@measure_latency`.
5. **Tildes/Ñ** en títulos → normalización accent/ñ-insensitive OBLIGATORIA en `match_title`.

---

## 9. Verificación

- **Tests offline (nuevos):**
  - `test_farm_nodes.py`: matchea los 14 títulos incl. ruido de tildes/Ñ; resuelve los 28 EN a `set_id`.
  - `test_set_badge_matcher.py`: clasifica cada uno de los 81 badges a su set (S/A/B → misma clase) y
    separa los 2 sets de cada nodo.
  - `test_parser_s2_tiles.py`: `tile_boxes` sobre los 7 fixtures S2 da las cajas + slot-OCR correctos.
  - `test_monitor_s13.py`: handler S13 emite la predicción.
- **Suite completa** verde (recordar: 2 rojos PRE-EXISTENTES conocidos de Velina — NO regresión, ver
  [[project_velina_onboarding]]).
- **En vivo** (`qa_launch.ps1 -FromSource -IdDiag -ReadOnly`; el `.exe` está viejo, se corre desde
  fuente): entrar a S13 → log "Nodo: <título> → predice <A> / <B>"; farmear → S2 → log por disco
  "slot N · <set> (conf)"; confirmar detectados ⊆ predichos.

---

## 10. Orden de implementación

1. **Fase A — S13** (menor riesgo, solo OCR): `farm_nodes.toml` + `FarmNodeCatalog` + handler
   `_process_s13_node_title` + tests. Cierra con QA en vivo del log de predicción.
2. **Fase B — S2** (mayor riesgo, descriptor): `set_badge_matcher.py` + geometría `tile_boxes` +
   slot-OCR + extender `_process_s2_resultado` + `asset_resolver` + tests. Cierra con QA en vivo del
   log por-disco y, si el matcher falla, cosecha de tiles reales.

Ambas fases: **display-only**, sin tocar DB. Commits directos a main (`git push origin HEAD:main`,
ver [[feedback_git_main]]). Al cerrar cada fase: doc en `Dev_IA/` + actualizar
[[project_farmeo_captura]].

---

## 11. Referencias

- **Dev_IA (hoy):** `2026-07-07_QA_En_Vivo_Farmeo_S2_S3.md` (los 7 fixes que dejaron el flujo estable),
  `2026-07-07_Confiabilidad_Detector_Anti_FP.md` (endurecimiento anti-FP previo),
  `2026-07-07_Gate_Captura_Por_Foco_Anti_FP.md` (gate por foco).
- **Dev_IA (5R, para el descriptor):** `2026-06-10_Hito_2.8_Fase5R_Descriptor_Robusto.md`,
  `2026-06-11_Hito_2.8_Fase5R_Grilla_Voto_Cosecha_Validacion.md`, `2026-06-13_PLAN_Embedding_Badges_Fase5R.md`
  (spike embedding DESCARTADO → ganó el descriptor).
- **RF:** `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` (S13/S14 §, layout tile S2 l.42,46).
- **Memoria:** [[project_farmeo_captura]] (fase de farmeo + pendientes), [[project_fase5R_identidad_grilla]]
  (descriptor gana embedding), [[feedback_git_main]], [[reference_windows_tooling_gotchas]].
- **CLAUDE.md:** RNF-02 (no inventar), RNF-03 (solo pixels/OCR), RNF-06 (<500 ms).

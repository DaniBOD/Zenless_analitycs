# PLAN — Extracción tienda de música de Orphie: S4 (selector) + S5 (afinación)

**Fecha:** 2026-07-09 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only (no persiste, no puntúa DB) · **Fases:** A (S4) → B (S5), en ese orden.

## Contexto / por qué

La **tienda de música de Orphie** ("Plan de entrenamiento") es una **segunda fuente de discos** en paralelo al flujo de desafío (S13→S2→S3) que ya endurecimos. El mecanismo:

1. **Selección (folder `18_`, estado `S4`):** elegís el **género a evocar** (= el **set** de discos) vía "Preferencia de género", y opcionalmente **preseleccionás un slot** en el hexágono "DRIVER". Luego "Afinás" (×01 / ×10) gastando fichas → se generan discos de grado S de ese set.
2. **Resultado (folder `11_`, estado `S5`):** "Resultado de afinación" muestra una grilla de hasta 10 discos generados; al **seleccionar** uno, su **ficha completa** (main + substats + efecto de conjunto) aparece a la izquierda, **estructuralmente idéntica a S3**.

**Objetivo:** cerrar el loop **predecir→confirmar** también para esta fuente, reusando la maquinaria existente:
- **S4 ≈ S13** → predice set (+ slot) → alimenta `FarmSession`.
- **S5 ≈ S3** → extracción real del disco enfocado (el usuario clickea cada disco, se re-extrae; igual que en resultado del desafío).

Todo **display-only** (RNF-01 no aplica; feature iterable).

## Estado verificado (2026-07-09)

- **Los "géneros" SON los sets de la DB** (columna `disc_sets.nombre`), no etiquetas de flavor. Confirmado: *Salón huracanado*→52 (Wuthering Salon), *Tecno tetraodóntido*→40 (Puffer Electro), *Fábula Yunkui*→49 (Yunkui Tales), *Punk Hormonal*→32, *Metal Colmilludo*→30, *Nana a la luz cenicienta*→35. ⇒ **Cero data nueva**: el género se resuelve a set con el `_lookup_set_id`/`norm_key` existente.
- **Los estados YA están reservados** en `detector.py` (`STATE_DESCRIPTIONS`): `S4`="Tienda música — selector", `S5`="Resultado de afinación". Ambos hoy en `NON_CAPTURE_STATES` (se detectan pero no extraen).
- **Detección actual (corrida sobre las capturas):**
  - `18_` (selector, 9 capturas) → **todas `S15`** (conf 0.96), NO `S4`. Colisiona con "Menú de personajes (plan de entrenamiento)" por fondo de Orphie + título compartido. **`S4` no tiene template registrado** (`s4_*.png` no existe; sí existen s5/s6/s7).
  - `11_` (afinación, 2 capturas) → `Tienda_musica_afinacion.png`=**S5 conf 1.00** ✓; `_2.png`=**S12 conf 0.65** (se escapa). Template S5 frágil.
- **Anclajes de código:**
  - `FarmSession.set_prediction(node_titulo, sets: list[(set_id, nombre_en)], ts)` — mismo contrato que S13.
  - Handler modelo: `Monitor._process_s13_node_title` (l.1063): edge-triggered, gate de re-OCR por firma del ROI (RNF-06), dedup por último nodo. **S4 lo espeja.**
  - `parser_disc_s3.parse_disc_s3_full(frame, ocr)` con `_S3_MODAL_ROI=(0.30,0.18,0.42,0.58)` (x,y,w,h). **S5 reusa la maquinaria** apuntando a un ROI propio (la card de S5 está más a la izquierda y más alta que el modal S3 → calibrar `_S5_CARD_ROI`).

## Fase A — S4 (selector, folder 18): detección + contexto

**A1. Desambiguar S4 de S15.** S15 (menú de personajes) y S4 comparten fondo+título. S4 tiene chrome único que S15 no: header *"Pulsa los números para seleccionar la partición de las pistas de disco"*, el hexágono **DRIVER**, y los botones **Afinar ×01 / ×10** (abajo-derecha). Plan:
- Crear template `app/resources/templates/s4_tienda_selector.png` recortado de una captura (zona derecha estable: header + hexágono).
- Registrar `{"code":"S4", "template":"s4_tienda_selector.png", ...}` en la lista de templates.
- Añadir un **verify/override** que promueva S4 sobre S15 cuando el chrome de S4 esté presente (patrón del tab-override / `_verify_s2`): p.ej. presencia del texto "Afinar" en el ROI abajo-derecha, o firma del hexágono en `x∈[0.62,0.87] y∈[0.30,0.65]`. Calibrar contra las 9 capturas (deben dar S4; y S15 real — menú de PJ sin hexágono — debe seguir S15).

**A2. Handler `Monitor._process_s4_music_selector`** (espeja `_process_s13_node_title`):
- **Gate de re-OCR** por firma del ROI del género (RNF-06): solo re-leer si cambió la selección en pantalla.
- **OCR del género:** ROI del nombre bajo "Preferencia de género" (abajo-izq, `x≈[0.47,0.58] y≈[0.86,0.92]`, `psm=7`) → resolver **set** con el lookup existente (`_lookup_set_id` / `norm_key` contra `disc_sets.nombre`). Warn/abstención si no resuelve (RNF-02).
- **Slot preseleccionado (opcional):** las 6 posiciones del hexágono son **fijas** (TL=1, TR=6, ML=2, MR=5, BL=3, BR=4). El slot elegido se muestra como **"+" resaltado en amarillo**; leer por **geometría + máscara amarilla** (no por dígito — la posición ya da el slot). Si ninguna resaltada (centro X) → sin preferencia de slot (aleatorio). *Observación a calibrar:* confirmar si se puede seleccionar más de un slot (header dice "los números"); v1 reporta el/los slot(s) resaltado(s) o None.
- **Emisión display-only:** `FarmSession.set_prediction(<género/set>, [(set_id, nombre_en)], ts)` + diagnóstico `[tienda] evoca: <set> · slot <N|aleatorio>`. Edge-triggered por (género, slot); dedup como S13.

**A3. Wiring (`controller.py`):** el handler reusa `_farm_session` y el resolvedor de sets ya inyectados; no requiere catálogo nuevo (a diferencia de S13, acá el set sale por OCR directo del género, no por un mapa nodo→sets).

**Tests A (`app/tests/unit/`):**
- `test_detector_music_shop.py`: las 9 capturas de `18_` → `S4`; la(s) capturas de S15 real (menú PJ) siguen `S4`≠ → `S15` (no regresión).
- `test_monitor_s4.py`: sobre 2-3 capturas, el handler emite la predicción con el set correcto (Salón huracanado→52, Punk Hormonal→32, …) y el slot resaltado (Ejemplo_5→5, Ejemplo_7→6).

**Checkpoint A (QA en vivo):** entrar a la tienda de música → log "[tienda] evoca: <set> · slot <N>".

## Fase B — S5 (afinación, folder 11): robustez + extracción

**B1. Endurecer detección S5** (que agarre las 2 capturas, hoy 1/2):
- El template ancho del top (`s5_resultado_afinacion.png`) cambiaba con el disco seleccionado
  (`_2` con disco (4) → 0.648 < umbral 0.80 → S12). Fix aplicado: 2º template **TIGHT del header
  "Resultado de afinación:"** (`s5_resultado_afinacion_header.png`, 58×447), idéntico ante la
  selección → matchea ambas capturas a 1.000; negativos (S2/S3/S4/S15) ≤0.623.
- Test: ambas capturas → S5.

**B2. Extracción del disco enfocado (S3-style continuo):**
- **CORRECCIÓN de implementación (2026-07-09):** el plan preveía reusar la *familia S17* (por ser
  single-column). En la práctica la ficha de S5 es **angosta** y los nombres largos (título,
  "Probabilidad de Crítico", "Maestría de Anomalía") se **envuelven a 2 líneas** — exactamente el
  problema que resuelve el motor de **S3** (`_coalesce_wrapped_names` + rescate de valor), NO S17
  (que no coalesce nombres). ⇒ S5 reusa el motor de **S3 a 1 columna**.
- Se parametrizó `_parse_s3_from_lines(..., band, cols)` (default = 2 columnas de S3, sin cambio);
  `parse_disc_s5` (en `parser_disc_s3.py`) llama con `band=_S5_BAND`, `cols=(_S5_COL,)`. OCR
  full-frame + filtro de banda (como S3). Slot del "(N)"; rareza='S' (la tienda solo da grado S).
- **Continuo** (como S3): `S5` en la lista de dispatch continuo + `_process_disc_s5_continuous`
  (espejo de `_process_disc_s3_continuous`) con `_s5_aggregator`/`_s5_emitted_ids`/`_s5_disc_signature`.
  Ruteo vía `_NEW_DISC_STATES` → `_maybe_process_disc`. `DiscAggregator` + `disc_is_mature` igual que S3.
- Emisión: `[disco] <set> · slot N · main …` display-only + checklist "ya capturado" por identidad.

**Tests B:**
- `test_detector_music_shop.py`: ambas capturas de `11_` → S5.
- `test_parser_disc_s5.py`: sobre `Tienda_musica_afinacion.png`, extrae *Nana a la luz cenicienta (3)*, S, main Defensa 46, subs {Defensa 4.8%, PV 112, Crit 2.4%}.

**Cierre B (QA en vivo):** afinar → clickear cada disco del resultado → log por disco con set/slot/main/substats.

## QA en vivo 2026-07-09 (fixes durables sobre S4/S5)

Sesión de QA en vivo tras implementar A+B. **S4 ✅ validado** (género→set incl. Firmamento llameante→53, Tecno tetraodóntido→40; slot del hexágono 1/2/5/6/aleatorio OK). **S5 ✅ validado** con estos fixes:

1. **Preview de grilla (pedido del usuario):** al entrar a "Resultado de afinación", emitir `[disco] slot N · <set>` por CADA disco evocado (antes de abrir detalles), como el resumen por-disco de S2. `parse_s5_grid` lee el label `<set> (N)` de cada tile (grilla 2 filas × 5 cols; cantidad variable 4/6/10 según la moneda). Handler `_emit_s5_grid_preview`.
2. **Set por consenso:** todos los discos de UNA afinación son del mismo género evocado → resolver el set por el más votado entre los tiles que resuelven, aplicado a todos (robusto al ruido OCR de un label suelto, p.ej. `llameante`→`Ilameante`).
3. **Nombre de set completo + ICO:** el título/efecto de S5 se envuelve a 2 líneas → `set_name_efecto` tomaba solo `Firmamento` y pisaba al título completo → el logo/ICO no salía. Fix: coalescer TODAS las líneas del efecto antes del 1er `N pistas:` → `Firmamento llameante`. **Además** `_lookup_set_id` (controller, resolvía el logo) hacía match EXACTO → frágil al ruido OCR (`Firmamento Ilameante`) → sin ICO en la mayoría. Ahora delega en `DiscSetRepo.resolve_id` (exact→substring→difflib) → ICO consistente.
4. **Re-afinación desde la misma pantalla:** el botón "Afinar ×N" está en la propia pantalla de resultados → se re-afina sin salir de S5, con grilla nueva. El preview one-shot no re-disparaba. Fix: usar la **secuencia de slots** de la grilla como identidad de tanda (una firma de imagen NO sirve: el highlight de selección la arruina — within-batch 2.78 > between-batch 0.49). Al cambiar el disco enfocado se re-chequea la grilla; si los slots cambiaron → nueva tanda → re-preview + limpiar dedup. `_maybe_new_s5_batch` + `_s5_grid_slots`.
5. **Slot 1 (cosecha de badges):** el `(1)` fino del label/título se cae en el OCR → `?` en la grilla y `slot=0` en el focado. Fix doble: (a) **grilla** → leer el BADGE del tile con un `SlotDigitMatcher` propio de S5 (24 refs cosechadas de los 4 screenshots → `app/resources/slot_digits_s5/`; el matcher de S2 abstenía 0/10 por framing/fondo distinto; el de S5 lee 10/10). (b) **focado** → slot 1/2/3 por MAIN plano (HP/ATK/DEF flat, regla fija ZZZ). Geometría de badges 2×5 calibrada contra el fixture de 10 discos.

Fixtures agregados: `11_Tienda_Musica_Afinacion/Tienda_musica_afinacion_{3,4}.png` (10 discos, slots 1-6).

## Riesgos

1. **S4↔S15** por chrome compartido → mitiga discriminador por hexágono/"Afinar"; validar que S15 real no se degrada.
2. **ROI de la card S5** distinta a S3 → calibrar contra las 2 capturas antes de confiar en el parser.
3. **Slot múltiple en S4** (¿se puede elegir >1?) → v1 reporta lo resaltado; confirmar en vivo.
4. **Latencia RNF-06:** S4 = 1 OCR gateado (barato); S5 = 1 parse por frame continuo (como S3, ya dentro de presupuesto).
5. **OCR del género** con nombres largos/tildes → reusar `norm_key` (insensible a tildes) + fuzzy si hace falta (patrón `best_predicted_set_id`).

## Verificación final

- Suite completa verde (2 rojos PRE-EXISTENTES de Velina, no regresión).
- QA en vivo por fase. `.exe` viejo → correr desde fuente (`qa_launch -FromSource -IdDiag -ReadOnly -NoFocusGate`).

## Cierre (post-implementación)

- Commits directos a main (`git push origin HEAD:main`), commit por fase.
- Actualizar `STATE_DESCRIPTIONS`/`CAPTURE_DISC_STATES` (S5 pasa a capturar; S4 sale de NON_CAPTURE si emite contexto).
- Doc de cierre en `Documentacion/Dev_IA/` + actualizar memoria `project_farmeo_captura`.
- RNF aplicables: RNF-02 (no inventar / warn al no resolver), RNF-03 (solo pixels+OCR), RNF-06 (<500 ms).

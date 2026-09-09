# IMPL — Matcher del dígito de slot S2 por template (NCC)

**Fecha:** 2026-07-09 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only.

## Problema

El dígito de slot (1-6) del hexágono arriba-izquierda de cada tile de disco en la pantalla de
resultados (S2) es un glifo **estilizado metálico y chico**. PaddleOCR lo lee mal de forma
crónica — familia de errores vista en vivo: `5`↔`S`, `6`→`5`, `4`→`2`. El slot definitivo igual
sale de S3, pero el preview de S2 quedaba poco fiable. Barrido de preprocesado OCR (crop
ajustado, thresholds, psm): sin arreglo limpio.

## Solución

Como los glifos son un **conjunto FIJO de 6**, se reemplaza el OCR por **template matching (NCC)**
contra recortes reales, como camino primario (OCR queda de fallback).

### Descubrimiento clave (descriptor)

El **hexágono de fondo es idéntico** en todos los slots y domina la correlación → todos los
dígitos correlan ~0.99 y el margen entre el correcto y el resto es <0.05 (inservible). Se resta
el **template promedio** de todas las referencias para aislar el **residuo del dígito** → el
margen medio pasa de ~0.12 a ~0.5. Se recorta además el centro del badge (donde está el dígito).

- `app/core/slot_digit_matcher.py` — `SlotDigitMatcher`:
  - `_raw_vec(crop)`: gris → recorte central (`_CENTRAL`) → resize fijo (40×48).
  - Al construir: promedio de todos los raw → residuo por ref (`raw − promedio`, media 0/norma 1).
  - `identify(crop) → (slot|None, score)`: NCC del residuo contra cada dígito (máx por dígito),
    abstención por `_MIN_SCORE=0.65` (aciertos ≥0.88; cruces/crops mal encuadrados ≤0.42).
- **Referencias:** 30 recortes reales de tiles S2 (`app/resources/slot_digits/<digito>_<origen>_<i>.png`),
  etiquetados por inspección visual (cobertura 1:5 2:4 3:6 4:8 5:4 6:3). No hizo falta cosecha en
  vivo: los 10 screenshots de `01_Pantalla_Resultado_Desafio` cubrían 1-6.
- **Integración:** `parser_s2.read_tile_slot(frame, box, ocr, slot_matcher=None)` — matcher primario
  (singleton lazy `_get_slot_matcher`), OCR de fallback si abstiene. Sin cablear por monitor/
  controller (helper display-only).

## Verificación

- **Leave-one-out sobre las 30 refs (promedio recomputado sin el crop):** 29/30 al dígito correcto,
  **0 confusiones entre dígitos**, 1 abstención (un `6` mal encuadrado de Ejemplo_2 → cae al OCR).
- **Regresión Woodpecker:** `read_tile_slot(Ejemplo_10, ocr=None)` → `[6, 4]` (antes el `6` se leía
  `5`). Prueba que el matcher es primario (funciona sin OCR).
- Tests S2 existentes siguen verdes (el `5` estilizado ahora se lee 5 por template, no por el hack
  `S→5` del OCR, que queda solo en el fallback).

## Notas / follow-ups

- El `_SLOT_CONFUSION` (`S→5`) se conserva en el **fallback OCR** (aún útil si el matcher abstiene).
- Si aparecen framings nuevos que abstienen seguido, agregar esos crops como refs (crecer el set).
- El slot AUTORITATIVO sigue siendo S3; esto robustece el **preview** de S2.

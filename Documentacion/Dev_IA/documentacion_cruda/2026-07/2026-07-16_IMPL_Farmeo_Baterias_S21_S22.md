# IMPL — Farmeo por BATERÍAS: previa de usos (S21) + drops del modal "Obtenido" (S22)

**Fecha:** 2026-07-16 · **Branch:** `feature/5R-detbadge-matcher` · **Modo:** display-only · **RF:** RF-04.

Farmear gastando baterías (auto-combate) era **invisible de punta a punta**: los 8 frames de
sus dos modales caían a `S12 / dark_frame_filter` porque ningún template matcheaba.

```
S13 (nodo, ya soportada) → S21 (modal de usos) → auto-combate → S22 ("Obtenido") → S13
                                                  ↑ NO hay S14, ni S2, ni S3
```

## Por qué el "Obtenido" vale más que una previa

El docstring de `parser_s2.py` ya declaraba que **el conteo de S2 no es confiable**: la grilla
se colapsa con "▼" y el auto-desmontaje convierte varios drops en materiales. El modal
"Obtenido" no tiene ese problema — lista todo, desglosado por corrida. Y como el auto-combate
no pasa por S2 ni S3, **es la única ventana donde estos drops existen**.

## Alcance: solo tier S, y ahora con un invariante detrás

Igual que `parser_s2`. Pero acá el recorte dejó de ser una simplificación: el usuario confirmó
que **el juego solo puede auto-desmontar tier A; los S nunca**. Los discos A que aparecen con
badge "C" fueron auto-desmontados y **nunca entraron al inventario** → reportarlos sería
mentir. "Dorado ⇒ conservado" es un invariante del juego, no un supuesto nuestro.

## Hito A — S21 (previa)

Template del título "Selecciona el número de usos" (0.85, NON_CAPTURE, cadencia 1000 ms). Los
4 fixtures matchean a **conf 1.000** y la S13 plana sigue siendo S13.

**Sin riesgo de eclipse, por construcción:** el `dark_frame_filter` solo corre si el frame ya
quedó S12 (`detector.py:1461`), así que un template propio lo esquiva. Y el desenfoque del
fondo tumba el match de S13 (umbral 0.70) → los modales no le roban la pantalla que los hospeda.

**`_process_s21_usos`:** OCR de `Cantidad consumida × N` → previa cruzada con el nodo predicho
en S13. Edge-triggered **por valor** (mover el slider re-emite), gate de firma 32×32 anti-re-OCR.

> **El regex ancla en `consumida` a propósito.** El modal tiene otro `× 8` (el stock) en el
> mismo eje vertical y un `1 … 4` de slider debajo: un `×\s*(\d)` suelto leería el número
> equivocado si el ROI se corre. Y el `×` (U+00D7) sale del OCR como `x` o `*` → la clase
> `[x×*]` no es opcional.

**`FarmSession.set_usos/usos` + `"S21"` en `_FARM_ARMING_STATES`** — load-bearing: con baterías
no hay S14, así que sin re-armar en S21 la ventana de 600 s podría vencer durante un
auto-combate ×4 y el "Obtenido" llegaría sin predicción de sets. Los usos **no** se persisten
en el breadcrumb (son del momento); son el denominador del `uso 2/4` del hito B.

## Hito B — S22 ("Obtenido")

### Geometría (medida, no estimada)

- **6 columnas FIJAS**: `cx = 0.2359, 0.2917, 0.3476, 0.4035, 0.4594, 0.5152` (paso 0.05586).
- **Filas DETECTADAS** por clustering del `cy` de las franjas de rareza: el scroll corre el `y`.
  Paso real: **0.123** intra-corrida, **0.171** cuando en el medio va el header de la siguiente.
- Caja del tile: `half=0.021, **above=0.076**, below=0.005` (iconos al ~64% de los de S2).

> **La caja fue el todo.** Mi primera estimación (`above=0.062`) recortaba el dígito por la
> mitad y hacía leer 1 de 4 fixtures — y el `4,4,4` que "acertaba" era **casualidad**. Con
> `0.076` los usos 1, 2 y 4 salen perfectos. Toda conclusión sobre "el matcher no transfiere"
> sacada con la caja mal está envenenada.

### Agrupación en secciones: el header es la única fuente

Se **descartó** cortar por el gap vertical (0.123 vs 0.171 → margen chico y frágil). Se OCRea
la banda de header sobre cada fila detectada (≤4 OCRs/frame, coste comparable al de S13, ya en
producción). No tiene filo: sobre una fila que **no** encabeza sección, el ROI cae en los
labels de cantidad de la fila de arriba (`"600 1 1"`) y el regex los rechaza solo.

Las filas anteriores al primer header visible son **huérfanas** (su encabezado quedó scrolleado
fuera) → se descartan, nunca se fusionan con la sección anterior.

> **Bug atrapado por un test, no por el QA:** el primer regex era `uso\s*n\D{0,4}(\d)`. Si el
> OCR mutila el `º` en un **dígito** (`n.9 3`), `\D{0,4}` consume solo el `.` y el `(\d)` se
> come el **9** → "corrida 9". Un error silencioso, no una abstención. El patrón final exige
> **espacio antes del dígito** (`uso\s*n\S{0,3}\s+(\d)`): la basura del `º` queda pegada a
> `n.` sin espacio, el número real siempre viene separado.

### `completa` y el marcador `≥`

`completa` = hay otra sección agrupada debajo **o** ya asoma el header de la siguiente
(`next_section_header`, +0.077 bajo la última fila) **o** no hay ▼ (fondo de la lista; medido:
flecha presente ≈0.34 de píxeles claros, ausente 0.000 → `Resultados_discos_4` es el fondo).

> **Por qué `next_section_header` no es un lujo.** El header de la próxima corrida puede estar
> en pantalla cuando su primera FILA todavía no (queda bajo el viewport). Sin buscarlo aparte,
> el uso 3 **no cerraría nunca**: al scrollear un poco más sus filas pasan a ser huérfanas y se
> descartan, así que la evidencia de cierre no vuelve a aparecer — quedaría en `≥3` para
> siempre. Una regla puramente geométrica tampoco servía: el viewport mide 0.53 y una sección
> de 3 filas ocupa ≈0.43, así que exigir un paso libre debajo no se cumpliría jamás.

El dedup es **convergente** (`_s22_seen`): una sección se re-emite solo si creció o si ahora
cierra; una vez cerrada, nunca más. En el caso típico son 1–2 líneas por corrida.

## El slot: matcher NCC detrás de un gate de completitud

**Actualizado 2026-07-16 (2ª pasada).** La 1ª pasada descartó el matcher y dejó solo OCR. Al
volver sobre el reporte del usuario ("problemas con el slot 4 y el 6") se midió más fino y la
conclusión cambió: el matcher es la vía correcta, lo que falta son **datos**, no diseño.

### El OCR es estructuralmente malo con esta fuente

No es que falle "a veces": pasando las refs etiquetadas de `slot_digits*/` por el camino OCR se
ve el comportamiento **por clase** de Tesseract (`psm=10`, thr150 + fallback Otsu):

| Clase | Qué devuelve | Sirve |
|---|---|---|
| 1 | `'LV:'`, `'IV:'`, `'y.'`, `'‘T:'` | **nunca** un dígito |
| 2 | `'2:'` (Otsu: `'(a,'`) | sí |
| 3 | `'3.'` | sí |
| 4 | `'a'` **siempre** (conf 0.75-0.89) | **no** |
| 5 | `'Ss'` → `_SLOT_CONFUSION['S']=5` | sí |
| 6 | `'(7'`, `'(FF'`, `'e:'` | casi nunca |

Esto explica el reporte: el `4` y el `6` son justo las dos clases que el OCR no puede.

**Y `'a' → 4` NO se puede mapear**, aunque el `4` la devuelva siempre: un `2` por la pasada Otsu
devuelve `'(a,'` y un `3` de las refs de S5 devuelve `'a'` en ambas pasadas. Mapearla convertiría
2s y 3s en 4s **en silencio** — exactamente lo que RNF-02 prohíbe, y por eso `_SLOT_CONFUSION`
tiene solo `S→5`.

### El matcher sí resuelve este badge — pero necesita las 6 clases

Sobre los 11 tiles dorados (`_raw_vec` + NCC del residuo):

| Experimento | Resultado |
|---|---|
| leave-one-**sample**-out (in-class) | **9/9 aciertos**, los tres `4` en score **0.999** |
| leave-one-**class**-out (dígito desconocido) | **6/11 INVENTAN**, score hasta **0.799** |
| ¿umbral separador? | **NO**: aciertos ≥0.755 vs invenciones ≤0.799 → **se solapan** |

Con clases faltantes el matcher no abstiene, **inventa con confianza**. De ahí el gate.

### Las refs de otras pantallas no transfieren (y son peores que nada)

El matcher resta el template **promedio de su propio set**, así que un badge de otro estilo deja
un residuo dominado por la diferencia de estilo:

| Base de refs | Contra los 11 tiles | Simulación slot-1 (clase solo en la base) |
|---|---|---|
| `slot_digits/` (S2) | abstiene en los 11 | **0 ok / 11 WRONG / 0 abst** (score hasta 0.946) |
| `slot_digits_s5/` (S5) | abstiene en los 11 | ídem |

Sumarlas como base no solo no ayuda: contesta **equivocado y confiado**, y hasta rompe un caso
in-class que hoy funciona (`3 → 2` a 0.898). Por eso ya hay **un set por pantalla**, y este
modal necesita el suyo.

### Estado: matcher ACTIVO (completado 2026-07-18)

`app/resources/slot_digits_extraccion/` tiene el set completo `{1:1, 2:3, 3:2, 4:3, 5:2, 6:3}`
= **6 clases** ⇒ el gate (`_get_slot_matcher_extraccion`) lo mantiene **encendido**. El slot 1
que faltaba se cosechó de `Ejemplo_12.png` (una captura nueva del "Obtenido" que trajo un slot 1;
la OCR lo leyó mal como "5" → verificado a ojo y renombrado a `1_`).

| Set de refs | Resultado sobre los 5 fixtures (14 tiles dorados) |
|---|---|
| 5 clases (sin el 1) | matcher apagado → solo OCR: **8/11, 0 errores, 3 abstenciones** (los tres `4`) |
| **6 clases (hoy)** | **matcher activo → 14/14, 0 errores, 0 abstenciones** |

Los tres `4,4,4` que el OCR no puede leer ahora salen (score 0.999). **Confirmado EN VIVO
2026-07-18**: la grilla del "Obtenido" leyó slot 1 y slot 4 correctamente.

Se completa con `tools/harvest_extraccion_slot_digits.py --glob "Ejemplo_12.png" --write`. Si
alguna vez se pierde una clase, el matcher se apaga en silencio → lo cubre el test
`test_las_refs_cosechadas_cubren_las_6_clases_y_encienden_el_matcher`.

### Toast en el panel DETAIL (2026-07-18)

El panel DETAIL de S22 era el **único** camino de detalle que no toastaba: solo emitía la línea
`[disco]` de log. Ahora `_process_s22_detail` llama a `self._on_disc(d, state)` como S3/S5 (el
controller enruta S22 al recommender, no a persistencia → display-only; `d.rareza="S"` por el
invariante del "Obtenido"). Al mirar el detalle de un disco salta el toast con la recomendación,
deduplicado por identidad. **Caveat esperado:** el disco preseleccionado al abrir el modal toasta
al abrir (no al clickearlo); re-clickearlo avisa `ya capturado` sin re-toast.

### Bug del `(` comido en el título del DETAIL (2026-07-18)

`Ejemplo_12` destapó que cuando PaddleOCR se come el paréntesis de apertura del slot (devuelve
`'1)'` en vez de `'(1)'`), el título no matcheaba y el disco **no se detectaba** (intermitente).
Fix en `_RE_DETAIL_TITULO`: `(` opcional, `)` obligatorio (distingue el slot de la cantidad `×N`
de un material → sin FP en `detail_has_disc`); `search` en vez de `match` anclado.

### Bug abierto: denominador `/N` del S21

QA 2026-07-18: el usuario puso 1 uso, luego lo subió a 4 con el slider, y el S21 **no releyó** el
cambio → el "Obtenido" mostró `uso 4/1` (headers 1→4 pero denominador pegado en 1). El re-read
edge-triggered de `_process_s21_usos` no se disparó al mover el slider. No rompe la captura de
discos. Pendiente de investigar (la firma del ROI de usos no detectó el cambio del slider).

## El set: sí transfiere

Con la caja corregida, `SetBadgeMatcher.identify(crop_art(...), cand_en)` da **conf 0.64-0.68,
margen 0.10-0.21** (S2 da ~0.88). Dos oráculos, sin ground-truth de sets:

- **Open-set** contra los **27** sets del catálogo: **11/11 caen dentro del par predicho por el
  nodo**. Ruido puro daría ~2/27.
- **Autoconsistencia con el arte**: el uso 2 da `Wuthering, Wuthering, Sky Ablaze` para los
  slots 2/3/6 — exactamente lo que se ve (2 y 3 comparten arte, 6 difiere).

**Límite:** 11 tiles, 1 nodo, 2 sets. Confirmar con un 2º nodo en QA.

## Formato

Cada disco reporta **lo que se sabe de él y nada más** (RNF-02): sin `slot ?`, sin set
adivinado. El conteo siempre se afirma (la franja dorada es evidencia directa).

```
[extracción] 4 uso(s) de batería · nodo: El piloto y el meca rebelde → predice Wuthering Salon / The Sky Ablaze · stock 8
[extracción] uso 1/4 · ≥2 discos S: slot 2 Wuthering Salon, slot 6 The Sky Ablaze
[extracción] uso 2/4 · ≥3 discos S: slot 2 Wuthering Salon, slot 3 Wuthering Salon, slot 6 The Sky Ablaze
[extracción] uso 3/4 · 3 discos S: Wuthering Salon, The Sky Ablaze, The Sky Ablaze
[extracción] uso 4/4 · 3 discos S: slot 2 The Sky Ablaze, slot 5 The Sky Ablaze, slot 5 The Sky Ablaze
```

> **Bug que solo apareció corriendo el pipeline entero:** el uso 3 son tres discos slot 4 — el
> único dígito que el OCR no lee. El set **sí** estaba identificado, pero el formato lo mostraba
> únicamente pegado al slot ⇒ la línea salía como `3 discos S` pelada, tirando a la basura un
> dato que el sistema tenía. Ningún unit test lo veía. Ahora cada disco se renderiza con lo que
> tenga: `slot N Set` / `slot N` / `Set`; si ninguno tiene set, se enumera el par predicho.

## Verificación

- **Anti-FP:** `_verify_s22` (≥6 franjas de rareza en el viewport; los fixtures dan 12-14).
  Necesario: "Obtenido" es un título genérico de ZZZ (correo, login, pase). Los **33 negativos**
  de `test_detector_fp_negative_qa.py` siguen verdes con S21 y S22 registrados.
- **Suite:** 926 passed (845 baseline + 81).
- **Pipeline end-to-end** sobre los 6 fixtures reales, sin stubs: clasificación
  `S13 → S21 → S22×4` y las 6 líneas de arriba, contrastadas contra el ground-truth
  (uso1=`2,6` · uso2=`2,3,6` · uso3=`4,4,4` · uso4=`2,5,5`).

**Pendiente: QA en vivo.** Las baterías son un recurso limitado → aprovechar la corrida. Mover
el slider 1→4, lanzar, y scrollear el "Obtenido" **despacio hasta el fondo** (verificar la
convergencia del `≥`). Idealmente con un **2º nodo** para el límite del set.

Docs relacionados: `2026-07-16_IMPL_Mejora_Disco_desde_Tienda_Musica_S5.md`.
Memoria: `project_farmeo_baterias`.

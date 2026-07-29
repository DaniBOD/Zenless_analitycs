# RF-15 · S26 — separar el detalle de W-Engine del detalle de disco

**Fecha:** 2026-07-28 · **Hitos:** H0 (contrato de abstención) + H1 (estado S26)
**Modo:** observación pura — cero escrituras a la DB.

---

## El problema

La pantalla de detalle de un W-Engine y la de un disco son **la misma pantalla** con otro panel
central. Las dos matchean `s17_personalizacion_pistas.png` a **1.000**. Y no es el único cruce:

| Pantalla de arma | Cae hoy en | Nota |
|---|---|---|
| Detalle del W-Engine (40 fixtures) | **S17 @ 1.000** | mismo template, `slot=None` |
| Inventario de armas (6) | **S9 @ 0.855–0.864** | |
| Diálogo de reemplazo (4) | **S23 @ 0.999** | ⚠️ **pasa `_verify_s23`** (`txt=sustituir`) |
| Mejora (6) · Refinar (5) | S12 `dark_frame_filter` | nada matchea ⇒ estados nuevos, tramo posterior |

S23 es el estado que **escribe la DB** (mueve un disco entre PJs) y S17 es donde se confirma ese
swap.

## Lo que descubrió H0

Los tres parsers de disco se abstienen sobre frames de arma. Pero al escribir los tests se cayó
la premisa con la que se había planificado:

> Se creía que la abstención la sostenía `set_name_canon` (el nombre del arma no matchea contra
> `disc_sets`). **Falso**: los discos reales maduran con `set_name_canon=None` — el gate acepta
> `set_name_raw`, y el arma lo llena con `'Petrazufre Nivel 60/60'`.

De las cuatro condiciones de `disc_is_mature`, **un arma ya cumple dos**: el nombre crudo y
`main_valor` (que llena con el "Ataque Base", 684). Tampoco protege la confianza:
`confianza_global` da **0.969–0.994** sobre frames de arma.

Lo único que frena la contaminación:

- en S17/S9 → el panel del arma **no tiene slot ni substats**;
- en S23 → `_RE_SUSTITUCION` exige el `(N)` del slot, que el texto del arma no trae.

El margen es más fino de lo que parecía, y ninguna de las dos condiciones fue diseñada para
rechazar armas. `app/tests/unit/test_armas_no_contaminan_discos.py` las fija como contrato (54
casos), con las dos condiciones load-bearing afirmadas **por separado** para que al caer se sepa
cuál se perdió, y con controles positivos para que los asserts no pasen por estar roto el parser.

## Los discriminantes baratos que NO funcionan

Todos medidos, ninguno supuesto:

| Candidato | Resultado |
|---|---|
| Fila de 5 estrellas, fracción de blanco (V>200) | armas min 0.0229 · discos max 0.0609 — **se solapa** |
| Ídem, gris+blanco (V>80) | separación **0.58×** |
| `_detect_s17_slot_by_hexagon` | da `None` también para los 30 discos de `14_Slots_equipamiento` |
| `read_s17_action_button` | `'reemplazar'`/`'desequipar'` en las dos |

**Por qué falla el de las estrellas, que era el candidato obvio:** un arma P1 tiene 1 estrella
blanca y 4 grises. El llenado de esa banda **es la señal de refinamiento**, no una constante. No
puede hacer los dos trabajos a la vez.

Lo que sí separa es el texto del panel, que la ruta S17 ya OCRea igual:

| | disco | arma |
|---|---|---|
| Sección 2 | "Atributos **secundarios**" | "Atributos **avanzados**" |
| Sección 3 | "Efecto de **conjunto**" | "Efecto de **amplificador**" |

Medido: **40/40 armas y 0/42 discos**, tanto con Paddle como con Tesseract.

## El diseño

**S26 comparte el template de S17 y va ANTES en `_STATE_TEMPLATES`.** `passing.sort` es estable,
así que ante el empate a 1.000 el primer turno de verificación le toca al que aparece primero, y
acá el estricto es S26. Si S17 fuera primero, su verify genérico (Hough de líneas en el panel)
pasaría sobre un frame de arma y S26 no llegaría a probarse.

Es el mecanismo de S23/S25 **con los roles invertidos**: allá el primer turno es del que escribe
la DB; acá el que escribe la DB es el fallback, y el que se adelanta es el que se niega a sí
mismo cuando no está seguro.

`_verify_s26` **falla cerrado**. Sin OCR devuelve `False`, el arma vuelve a caer en S17 y todo
queda como antes del hito — que era seguro, porque los parsers se abstienen. Degradar no puede
empeorar nada. `_verify_s17` **no se tocó**: endurecerlo obligaría a re-validar los 42 fixtures
de disco a cambio de nada.

## Latencia — lo que el plan subestimó

El plan presupuestaba **< 60 ms**. La primera medición lo desmintió por 9×:

| Backend, banda del panel | Tiempo | Acierto |
|---|---|---|
| Tesseract (el que usan los otros verifies) | **533 ms** | 40/40 · 0/42 |
| Tesseract, banda de una sola línea | ~450 ms | **25/40** ⇠ peor en las dos |
| Paddle | 124–235 ms | 40/40 · 0/42 |

Achicar el ROI **no baja el tiempo** (el costo es overhead fijo por llamada, no píxeles) y sí
baja la precisión: el header **no está a un `y` fijo** porque los nombres largos envuelven y
corren el panel. Es la lección de siempre en este repo — el layout no es estable por fila.

La respuesta fue estructural, en dos capas:

**1 · Cache por firma del panel.** El panel está quieto mientras el usuario lo mira, así que el
OCR corre una vez por *cambio*, no por ciclo.

| | cache miss | **cache hit** |
|---|---|---|
| arma | 167.6 ms | **0.31 ms** |
| disco | 333.7 ms | **0.34 ms** |

La firma cubre la **unión** del ROI del OCR y de la banda de estrellas, no solo el primero: el
veredicto depende de los dos, y cachearlo bajo una firma que ignore una de sus entradas dejaría
al cache devolviendo veredictos que sus propias entradas ya no justifican.

**2 · Pre-gate de una sola dirección.** Este verify corre sobre *toda* pantalla que matchee el
template de S17, discos incluidos: sin gate le agregaría ~334 ms por cambio de panel a un flujo
que hoy ya funciona. La fila de estrellas no sirve para afirmar "es un arma", pero sí para
descartar barato:

```
armas    min 0.0229
discos   0.0000 (×32) · 0.0006 · 0.0609 (×10)
corte    0.010  →  2.3× de margen contra el arma más floja, 16× contra el grupo denso
```

**32/42 frames de disco evitan el OCR entero.** Y si el gate fallara alguna vez para un arma, esa
pantalla vuelve a caer en S17 — el comportamiento previo, que es seguro.

## Un test que estaba mal escrito

La primera versión del test de regresión exigía `S17` en los 42 frames de disco. Falló en uno de
`04_Inventario_Disco_Vista_Individual`, que legítimamente clasifica **S7** (la vista de tienda de
música tiene su propio template) — o sea, habría reportado como "S26 rompió algo" un
comportamiento anterior y correcto.

Se reescribió como **invarianza**: cada frame de disco se clasifica dos veces, una con S26 activo
y otra con su verify forzado a `False` (que reproduce el pipeline anterior), y los dos resultados
deben coincidir. Es más fuerte que esperar un código concreto, y no miente.

## Estado

| | |
|---|---|
| `test_armas_no_contaminan_discos.py` | 54 casos |
| `test_detector_weapon_detail.py` | 98 casos |
| Regresión (`fp_negative_qa`, `sustitucion`, `desmontaje`) | verde |

**Falta:** el parser del panel (H2), rareza y refinamiento por píxeles (H3), dueño por badge
(H4), cableado y toast (H5). Y en tramos posteriores, una pantalla por vez: inventario de armas
(S9), diálogo de reemplazo (S23), Mejora y Refinar.

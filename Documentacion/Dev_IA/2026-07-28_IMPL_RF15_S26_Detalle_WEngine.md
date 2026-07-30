# RF-15 · S26 — el detalle de W-Engine

**Fecha:** 2026-07-28/29 · **Hitos:** H0 (contrato de abstención) · H1 (estado S26) ·
H2 (parser del panel) · H3 (rareza y refinamiento)
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

---

# H2 — el parser del panel

`app/core/parser_weapon_s26.py`, módulo puro que reusa la maquinaria del panel de una columna de
`parser_disc_s17`. El catálogo se **inyecta por parámetro** en vez de consultarse: mantiene el
módulo testeable sin DB y deja la decisión en el llamador.

## Tres cosas salieron mal

### 1 · El ATK base no se puede leer por ORDEN de líneas

Rompía **20 de los 40 fixtures**. PaddleOCR devuelve la línea del número con un `y1` unos píxeles
**menor** que la de su etiqueta:

```
y1= 448  xn=0.479  '594'          ← el valor
y1= 451  xn=0.329  'Ataque Base'  ← la etiqueta
```

Al ordenar por `y1` el número cae **antes**, el texto unido queda `"594 Ataque Base"` y una regex
direccional (`ataque base \D{0,6}(\d+)`) no matchea. Y si el orden se da vuelta o no depende de
tres píxeles, así que fallaba en aproximadamente la mitad de los casos.

Se lee por **columna** (`xn >= col_split`), que es estable, con fallback bidireccional para cuando
el OCR funde etiqueta y valor en una línea. **El atributo avanzado nunca falló** porque ya
separaba por columna — la misma trampa del fix v3.0 de S18.

### 2 · El fuzzy cruzaba los Modelos de Repercusión

Encontrado revisando en frío, no corriendo. El OCR lee `III` como `lll`, y normalizado:

```
"...modelo lll" vs "...modelo ii"   → 0.8837   ← gana el EQUIVOCADO
"...modelo lll" vs "...modelo iii"  → 0.8636
```

Dos armas distintas se habrían reportado como la misma. Las dos superan el corte de 0.84, así que
subir el umbral no arregla nada. Se colapsan a `i` los tokens compuestos **solo** por caracteres
que el OCR confunde (`i`, `l`, `1`, `|`), aplicado a tokens **enteros** para no tocar palabras
reales: en "Llanto mielgo" ningún token califica.

### 3 · La sección del atributo avanzado se tragaba la pasiva

Si el OCR no lee el header "Efecto de amplificador", el piso queda en infinito y entra el texto de
la pasiva — que está lleno de números ("aumenta el Ataque en un 3.5 % durante 8 s") y habría
producido un stat inventado. Las dos secciones se acotan ahora a su **primera fila**, con
tolerancia en Y porque "misma fila" no significa "mismo `y1`".

---

# H3 — rareza y refinamiento por píxeles

## El recorte fijo no sirve, y el primer intento lo escondía

La fila de estrellas **se corre verticalmente ~42 px** entre un arma de nombre corto y una de
nombre largo, porque el nombre envuelve a dos líneas y empuja el panel entero:

| | pill de nivel `y1` |
|---|---|
| nombre de 1 línea (Petrazufre) | 251 |
| nombre de 2 líneas (Templo a la granizada estelífera) | 293 |

Con una banda fija, los valores mezclaban **cuántas estrellas están blancas** con **cuánto de la
fila entró en la banda**: un arma de nombre largo daba ~30 % de lo que daba una corta. Las celdas
1 y 5 salían siempre en 0.0000, que fue la pista.

**Tampoco se hardcodean los centros de las 5 estrellas.** Los offsets se corren ~12 px entre los
dos regímenes de nivel, porque el bbox del OCR arranca en la "N" y "Nivel 60/60" es más ancho que
"Nivel 0/10". Se **detectan los blobs** por frame: 5/5 en los 40 fixtures, espaciado ~42.5 px,
ancho 24-28 px.

## Separación de las estrellas: absoluta

| | fracción de blanco (V>200, S<60) |
|---|---|
| llenas | 0.342 – 0.363 |
| **vacías** | **exactamente 0.000** |

Las grises no tienen **un solo píxel** sobre V=200. La convención del proyecto pide ≥2× de
margen; acá no hay margen finito que medir. El test lo afirma igual, para que un cambio de
calibración se vea antes de traducirse en un refinamiento equivocado.

Verificado a ojo contra las capturas en los dos casos que más importaban: Petrazufre (1 blanca +
4 grises) y Cúter (4 blancas + 1 gris, el único refinamiento 4 del set).

## Rareza: hue del badge, varianza cero

| rareza | hue medido | n |
|---|---|---|
| S | **22.0** | 10 |
| A | **155.0** | 23 |
| B | **98.0** | 7 |

Ni un solo frame se desvía: son colores planos de UI, así que la mediana del hue es exacta. Los
rangos aceptados son ±10 y no se solapan ni de cerca.

**Doble señal.** En las 32 armas que están a nivel máximo, el ATK base determina la rareza de
forma independiente (S ∈ {684,713,743}, A ∈ {594,624} — auditoría del catálogo). Las dos
coinciden en las 32. Una discrepancia se **anota** en `notas` en vez de resolverse: el badge es
una lectura directa y el ATK una inferencia, así que no hay motivo para que la inferencia gane;
pero callarla sería perder la única verificación cruzada que hay.

## Un test propio que estaba mal (otro)

Asumí que `read_rareza` debía **abstenerse** sobre un frame de disco. Falla: devuelve `'S'`. Y
está bien que lo haga — el badge circular a la izquierda del pill es **el mismo widget en las dos
pantallas**, con el mismo código de color; en el detalle de un disco informa la rareza *del
disco*. Leerlo correctamente ahí no produce ningún dato de arma.

El lector que sí discrimina es el del refinamiento, y ese devuelve `None` sobre discos porque no
hay fila de estrellas. El test quedó partido en dos: la abstención se le exige al que discrimina,
y del otro se documenta que es un widget compartido.

---

# H4 — el dueño por el badge del avatar

**No hizo falta código nuevo de recorte.** El avatar del PJ que tiene el arma equipada está en el
mismo lugar de la pantalla que el del detalle de disco, y `crop_detail_badge` lo localiza con una
región fija + Hough, **sin depender del texto del nivel**. S26 reusa la superficie `detail` tal
cual: mismo crop, mismo matcher, misma librería `avatar_detbadge_v2`.

Lo que **no** se pudo reusar es `crop_s17_assigned_avatar`, que el plan nombraba: exige
literalmente `"/15"` en el texto del nivel —el denominador de un disco— así que devuelve `None`
para un arma, que dice `60/60` o `0/10`.

## La cobertura no llega a lo que pedía el plan, y el techo no lo pone el arma

El plan pedía **≥35/40** con dueño resuelto. Medido:

| | crops localizados | nombrados |
|---|---|---|
| armas (40 fixtures) | **26/40** | **13/40** |
| discos (10 de control) | 10/10 | 6/10 |

La tasa de nombrado *entre los que tienen crop* es 13/26 = **50 %** en armas y 6/10 = **60 %** en
discos. El matcher no anda peor con armas. Los dos límites son preexistentes y compartidos:

1. **La librería está parcialmente entrenada:** 39 labels para un roster de 50 PJs. Y en la ruta de
   runtime (`%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\avatar_detbadge_v2.npz`) **el archivo no
   existe** — sin el snapshot de `audit/`, el matcher tiene 0 referencias y nombra 0/40, igual que
   0/10 en discos. Una instalación nueva no tiene dueños en ninguna pantalla.
2. **La localización falla en 14 de 40:** verificado a ojo que en `Ejemplo_34` el avatar **sí
   está**, así que son misses de Hough, no abstenciones correctas.

No se forzó el número. Lo que sí se garantiza es lo que importa: **nunca un dueño equivocado**.

## Un defecto preexistente que apareció al testear

La librería devuelve `'n.Âº11'` para **N.º 11** — el nombre guardado con UTF-8 leído como latin-1
en algún punto de la cosecha. Es un defecto **compartido con la ruta de discos**, no algo que traiga
S26, pero sin filtro ese texto corrupto llegaría al log y al toast como si fuera el nombre del PJ.

El handler ahora **canonicaliza contra el roster** antes de reportar (`_canonical_name`), y un
nombre que no resuelve se descarta: preferimos "incierto" antes que basura. Queda un test que
afirma la existencia del mojibake, para que si alguien re-cosecha la librería y lo arregla, el test
caiga y se pueda borrar.

---

# H5 — cableado y toast

Cadena completa, calcada de la del desmontaje:
`monitor._process_s26_weapon_detail` → `on_weapon_seen` → `controller.weapon_seen` →
`main._on_show_weapon_toast` → `toast.show_weapon`.

- **Gate de firma (RNF-06):** el OCR del panel cuesta ~500 ms y la cadencia de S26 es 1000 ms. Sin
  gate, mirar un arma diez segundos serían diez OCRs idénticos. El handler solo parsea cuando la
  firma del panel cambió.
- **Los dos scopes de `_note_stall`** (`S26` y `S26/detalle`): requisito no negociable del
  proyecto — hubo dos trabes de 6-8 minutos por handlers mudos. Ojo la distinción: el panel
  *quieto* es el camino normal y **no** declara trabe; el que lo declara es el panel ilegible o el
  arma ya reportada.
- **Reset al salir de S26**, así volver a la misma arma re-emite en vez de quedar mudo.
- **Catálogo cacheado:** un solo `SELECT nombre FROM weapons`. Si la DB no está disponible, el
  parser sigue y devuelve el nombre crudo — canonizar es una mejora, no un requisito.
- **Variante `arma_vista`**, violeta como sus hermanas pasivas. El label dice **VISTO**, no
  "REGISTRADO": el hito no escribe la DB y un toast que insinuara lo contrario haría creer que el
  arma ya quedó sincronizada. Hay un test que prohíbe las palabras `REGISTRAD/SINCRONIZ/GUARDAD/
  IMPORTAD` en ese label.
- El refinamiento se pinta con estrellas y no como "P4": es lo que el usuario ve en la pantalla. Si
  no se pudo leer (0) **no se dibuja ninguna**, porque cinco vacías se leerían como refinamiento 0,
  que no existe (el mínimo es 1).

**El test que importa:** `test_el_handler_no_toca_la_db` compara el sha256 de la DB real antes y
después de correr el handler. Si alguien agrega un INSERT, cae.

---

## Estado

| | |
|---|---|
| `test_armas_no_contaminan_discos.py` | 54 casos |
| `test_detector_weapon_detail.py` | 98 casos |
| `test_parser_weapon_s26.py` | 264 casos |
| `test_monitor_weapon_s26.py` | 13 casos |
| `test_weapon_owner_badge.py` | 5 casos |
| `test_toast_arma_vista.py` | 6 casos |

**Falta:** QA en vivo. Y en tramos posteriores, una pantalla por vez: inventario de armas (S9),
diálogo de reemplazo (S23), Mejora y Refinar, desmontaje/reciclaje de armas, completar el catálogo,
y el sync a la DB atado al censo inicial.

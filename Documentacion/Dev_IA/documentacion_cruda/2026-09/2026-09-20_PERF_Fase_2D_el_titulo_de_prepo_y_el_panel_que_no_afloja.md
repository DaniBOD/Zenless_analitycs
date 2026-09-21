# Fase 2D: el título que se leía de prepo, y el panel que no afloja

**2026-09-20 · PERF** · sigue a la
[Fase 2C](2026-09-20_PERF_Fase_2C_el_detector_lanzaba_tesseract_en_cada_vuelta.md), que dejó la
espera en 2766 ms y al OCR del panel como "el tramo grande que queda".

## 1. La espera se desarma sin hacer una pasada nueva

`metrics.db` guarda, por muestra, **cuándo se cerró** y cuánto duró. O sea que cada medición ocupa
el intervalo `[ts − dur, ts]` y se puede saber qué llamadas cayeron adentro de qué tramo. La pasada
del 20/09 (72 discos) ya tenía todo lo necesario:

| en una espera click→log (p50 **2766 ms**) | |
|---|---|
| `ocr_bboxes` — **el panel** | **1976 ms** en 1,56 llamadas |
| `ocr_text` — **la franja del título** (el slot) | **552 ms** en 2,31 llamadas |
| `capturer` | 51 ms |
| `detector` | ~0 (0,31 llamadas caen dentro de la espera) |
| el resto del despacho, sin OCR | 46 ms |

**El 92 % de la espera es OCR**, y son **dos** cosas, no una. La Fase 2C dejó dicho "el panel es el
tramo grande" y es cierto, pero al lado había 552 ms de otra cosa que nadie había mirado.

## 2. Lo barato primero: el título no hacía falta leerlo antes

`extract_s9_slot` OCRiza una franja del título para sacar el "(N)" del slot: ~286 ms por llamada,
dos llamadas por disco. Pero lo peor no era eso:

> De las **479** lecturas del título de la pasada, **378 (79 %) las hizo el LOOP**, sobre frames
> que nadie iba a parsear.

El loop la hacía en **cada vuelta** que caía en S9 para dejar `raw_state.slot`, y ese campo lo
consumía una sola cosa: el sufijo `slot=N` de la línea `[pantalla]` — que además repite lo que ya
dice la línea `Disco S9 detectado`. S17 había salido de ese mismo bloque hacía rato, cuando su
handler pasó a continuo; S9 era el que quedaba.

**Medido antes de tocar**, sobre las 19 capturas del corpus:

| | |
|---|---|
| el panel llega al MISMO slot por su cuenta | **18 de 19** |
| el panel dice algo **distinto** | **0** |
| el panel no sabe y hace falta el título | **1** (Ejemplo_6) |

Lo que había que descartar no era que el panel "no supiera" —para eso está el respaldo— sino que
dijera algo distinto **y equivocado**, porque ahí el respaldo llega tarde: el número malo ya ganó.
Eso es lo que da 0.

Así que la lectura no sobra: sobra **pagarla por adelantado**. Pasó de autoridad a último recurso,
después de la regla determinista del main plano, y deja nota `slot_rescatado_por_titulo` cuando
entra. Verificado: 19/19 el mismo slot que antes, 1 de 19 paga el respaldo.

**Sabotajes 4/4 en rojo**, hash del diff igual antes y después: que el loop vuelva a leer, que el
respaldo desaparezca, que el respaldo se pague **siempre** (o sea, que vuelva a ser la autoridad),
y que el `slot=` pasado a mano deje de ganar.

Esperado: **−552 ms** en la espera y **−286 ms en cada vuelta del loop** dentro de S9. Lo medido en
vivo, y en qué se equivocaba esa predicción, está en el §5.

## 3. El panel: cuatro intentos, cuatro refutados por su propia medición

En el banco (en proceso, máquina quieta) el panel cuesta **526-674 ms**, y por dentro es
**det 97 · recortar 5 · rec 406**. El reconocimiento es el 85 %.

| intento | qué pasó |
|---|---|
| **MKL-DNN** (`enable_mkldnn`, viene apagado) | **−4 %**. Lecturas idénticas, pero no es la palanca |
| **menos hilos** (`cpu_threads` 10 → 6, sobre 6 núcleos) | **−5 %**; con MKL-DNN también −5 % |
| **reconocer sólo las cajas útiles** (det → filtrar → rec) | **más lento**: 29 % menos cajas y `rec` 376 → 445 ms |
| **el envoltorio de PaddleOCR** | **18 ms (3 %)** — el "175 ms" que había medido antes era **mío** |

Las dos últimas enseñan algo.

**Filtrar cajas no paga, y el mecanismo se entiende.** `text_recognizer` **ordena las cajas por
relación de aspecto** y las procesa en lotes de 6, rellenando cada lote hasta el más ancho. La
basura del panel (`'x'`, `'7'`, `'DETAIL'`, `'RARITY'`, `'Ver'`) es toda corta, así que se agrupa
entre sí y sale casi gratis. Lo caro son las líneas largas — que son justo las que el parser
necesita. Sacar lo que no se usa no ahorra: ya no costaba.

**El envoltorio de 175 ms no existía.** Lo medí corriendo siempre la llamada entera primero y el
pipeline a mano después, así que la segunda rama heredaba los hilos calientes de la primera.
Alternando el orden, la diferencia cae a 18 ms. Es la misma trampa que apareció esta misma tarde
con el juego abierto, y prima hermana de **C1.b**: un orden fijo entre dos ramas es una condición
que se le suma **entera** a una sola.

Lo que sí quedó probado de ese intento: **partir el pipeline a mano (det + recorte + rec) da el
texto idéntico** en 19 de 19. No sirve hoy; sirve el día que se cambie de runtime.

## 4. El hueco que quedaba era más grande que todo lo anterior

| el mismo recorte del panel | |
|---|---|
| en el banco | **526-800 ms** |
| **en vivo, durante la pasada** | **1784 ms** (p50 de las llamadas grandes dentro de un despacho) |

Primero descarté, una por una, todas las explicaciones del lado del código:

| sospecha | medición |
|---|---|
| el socket / serializar el frame | **1,34 ms** (ya estaba medido, con el payload más grande) |
| que el OCR viva en otro proceso | worker **598** vs en proceso **587** |
| `CREATE_NO_WINDOW`, prioridad, EcoQoS de Windows 11 | 584-614 ms las cuatro variantes |
| la fuga acumulada (12,46 MB por inferencia) | 60 llamadas seguidas, de 1390 a 2716 MB de commit: **+1 %** |
| mandar una vista no contigua en vez de una copia | 623 vs 604 ms |
| el envoltorio de PaddleOCR | 18 ms |

Ninguna. Lo que quedaba de distinto entre el banco y la pasada es que **en vivo el juego está
corriendo**. Medido, con procesos quemando CPU para simularlo:

| carga | hilos de Paddle: 10 (hoy) | hilos: 4 |
|---|---|---|
| máquina quieta | **487 ms** | 463 ms |
| 6 procesos quemando (= los 6 núcleos) | **3300 ms** | 6102 ms |
| 12 procesos quemando | 23 666 ms | 21 546 ms |

**El costo del panel en vivo no es una propiedad de nuestro código: es cuánta CPU deja el juego.**
Los 1784 ms de la pasada caen justo entre la máquina quieta y la máquina saturada, que es lo que se
espera de alguien navegando el inventario con ZZZ renderizando al lado.

Y de paso, mi hipótesis de los hilos quedó al revés: **bajar `cpu_threads` con la máquina llena es
peor** (6102 contra 3300). Pedir menos hilos no te deja pasar antes; te deja menos posibilidades de
agarrar un núcleo libre.

### El error de método que esto destapa

La prueba de prioridad / EcoQoS del §4 la corrí con **la máquina vacía** y concluí "ninguna mueve
nada". No podía moverse nada: no había con quién competir. **Una prueba en la máquina quieta no
puede refutar una hipótesis sobre la máquina llena.** Repetida con carga, la prioridad sí parece
mover algo:

| prioridad del worker, con 6 procesos quemando | p50 | rango |
|---|---|---|
| normal (hoy) | 2333 ms | 1154-5622 |
| por encima de lo normal | 1861 ms | 1408-5169 |
| alta | 1967 ms | 1160-4128 |

**No lo declaré una mejora**: n=8 por variante, tres workers distintos uno después del otro y los
rangos pisados enteros. Por C1.b eso no es evidencia, es una pista.

### La pista era mía: con el diseño arreglado, el efecto desaparece

Se repitió con **un solo worker al que se le cambia la clase en caliente entre llamada y llamada**
(`SetPriorityClass` anda sobre un proceso vivo), **orden sorteado en cada vuelta** y n=30 por
variante. Mismo proceso, mismos modelos cargados, misma memoria: lo único que cambia es la
prioridad.

| prioridad del worker, con 6 procesos quemando | n | p50 | IC de la mediana | |
|---|---|---|---|---|
| normal (hoy) | 30 | 1761 ms | [1631-1966] | |
| por encima de lo normal | 30 | 1738 ms | [1381-1859] | −23 ms · **se solapa** |
| alta | 30 | 1697 ms | [1518-2128] | −65 ms · **se solapa** |

Los 472 ms de "mejora" de anoche eran **la deriva entre tres corridas**, no la prioridad. La misma
forma que C1.c, ahora del otro lado: primero medí en un escenario donde nada podía moverse, después
en uno donde lo que se movía era otra cosa.

**Y el instrumento sí funcionaba**, que es lo que hay que descartar antes de aceptar un resultado
negativo:

1. **La clase queda puesta.** `SetPriorityClass` devolver `True` es la intención; se leyó de vuelta
   con `GetPriorityClass` y las tres clases quedaron aplicadas.
2. **La prioridad muerde.** Con el worker en `HIGH`, un trabajo **fijo** en un proceso normal pasa
   de 575 a 625 ms: **+9 % para todo lo demás**. O sea que sí le saca CPU al resto — sólo que no la
   convierte en OCR más rápido.

**Conclusión: no se hace.** Cuesta 9 % del resto de la máquina —el juego incluido— y devuelve, en
el mejor caso, 65 ms sobre una espera de 2531 (2,6 %), que encima no se distingue del ruido. Que
el OCR no vaya más rápido con más prioridad dice además algo del cuello: el worker pide **10 hilos
sobre 6 núcleos** y cada inferencia son tandas paralelas cortas con barrera — la barrera la marca
el hilo más lento, y eso no se arregla llegando antes a la cola.

## 5. Verificado en vivo (2026-09-20, 22:44-22:51) — **99 discos**

Pasada de Daniel por el inventario, `qa_launch -ReadOnly -FromSource -Metrics`. La ventana se
acota **del primer al último disco**: la sesión trae 8 minutos previos de navegación por menús,
donde el loop cuesta otra cosa. Comparada contra los 6 minutos equivalentes de la pasada anterior.

| | antes (n=72) | hoy (n=99) | |
|---|---|---|---|
| **click→log** | **2766** ms [2687-2860] | **2531** ms [2484-2594] | **−235 ms · sin solape** |
| disco fresco→log | 2172 [2141-2266] | 1969 [1938-2015] | −203 · sin solape |
| **período del loop** | **703** ms [672-734] | **375** ms [375-390] | **−328 ms · sin solape** |
| `detector` | 218 | 203 | −15 |
| `capturer` | 49 | 42 | −6 |
| **el panel** (control) | 1877 [1840-1937] | 1898 [1854-1923] | **se solapan** |
| **lecturas del título** | **271** a 243 ms | **5** | el mecanismo, a la vista |

**El control se mantuvo.** El panel era el control declarado *antes* de la pasada: si hubiera
bajado también, lo que cambió serían las condiciones de la máquina y no el arreglo. Se solapa —
así que la mejora es atribuible.

**El mecanismo se ve directo:** mismo trabajo (6 minutos de inventario), las lecturas de la franja
del título pasaron de **271 a 5**. Esas 5 son el respaldo entrando donde el panel no supo: **5 % de
99 discos**, contra el 1 de 19 (5,3 %) que había dado el corpus. La predicción de cuántas veces
haría falta se cumplió.

### Predije −550 y salieron −235, y eso también tiene mecanismo

No es que el ahorro no esté: el **período del loop** cayó 328 ms, más de lo previsto. Lo que estaba
mal era mi modelo de la espera. **La espera no es una suma de trabajo: está cuantizada por vueltas
del loop.** Con el loop más rápido entran más vueltas adentro de la misma espera, y cada vuelta
trae su `classify`: el `detector` pasó de aparecer **0,31 veces** dentro de la espera a **0,93**, y
el `capturer` de 0,5 a 1,5. Eso devuelve ~170 de los ~300 ms que "faltan"; el resto es la
granularidad de qué vuelta se entera del click.

Dicho de otro modo: sacar trabajo de cada vuelta mejora la espera **menos** de lo que sugiere la
resta, porque parte del ahorro se reinvierte en mirar más seguido. Sigue siendo una mejora real y
afirmable, pero la próxima predicción de latencia de la espera tiene que modelar las vueltas, no
sumar milisegundos.

Verificado además: **sha256 de la DB de dominio sin cambios** (el `-ReadOnly` cumplió) y **0
warnings o errores** en toda la pasada.

## 6. Lo que queda

- De los **2531 ms** que quedan, **1898 son el panel** (75 %). Es lo único grande que sobra.
- **El panel no tiene más jugo por el lado de Python.** Si se lo quiere bajar de verdad hay que
  cambiar lo que corre: un runtime más barato en CPU (ONNX Runtime sobre los mismos pesos, que este
  repo ya usa para el embedder) o llevarlo a la GPU. Eso es una fase propia, con su medición.
- ~~La prioridad del worker~~ **probada y descartada** (§4): con el diseño arreglado el efecto
  desaparece (−23/−65 ms, IC solapados) y cuesta **+9 % a todo lo demás**.
- Los otros dos call-sites del OCR del panel (11 % y 6 % del total) siguen sin tocar.

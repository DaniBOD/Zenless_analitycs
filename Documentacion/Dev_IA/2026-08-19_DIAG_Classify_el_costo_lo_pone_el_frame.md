# `classify` tarda 3,5 s y el costo lo pone el FRAME, no el template — 2026-08-19

> **Qué pasó:** salimos a averiguar por qué el censo de discos avanza a ~4 s por disco y
> encontramos que `ScreenDetector.classify` se come el 83 % del ciclo. Pero **las dos hipótesis
> con las que salimos eran falsas**, y una de ellas ya estaba escrita en un doc anterior.
>
> **Punto de partida:** "S9 tarda 4,3 s, debe disparar un camino caro (¿`_deep_detect_s18`?
> ¿muchos templates candidatos?)".
> **Diagnóstico real:** S9 no tiene nada de especial. **Todas** las pantallas tardan lo mismo,
> porque `matchTemplate` cuesta lo mismo con un template de 8×8 que con uno de 1022×431.
>
> **Este doc es solo el DIAGNÓSTICO.** El refactor y el caché del OCR van aparte, en ese orden.

---

## 0 · Condiciones de la medición

Lo primero fue medir de nuevo, porque los números del planteo original se habían tomado con la
máquina cargada.

| | |
|---|---|
| Instrumental | QA-06 real: `DANIBOD_METRICS=1`, decorator `@measure_latency("detector")` sobre `classify` |
| Lector | `metrics.resumen()` — n/p50/p99/max, el lector del propio instrumental |
| DB | `metrics.db` redirigida a un temporal con `DANIBOD_METRICS_DB`. **La DB de dominio no se tocó** |
| Máquina | quieta: se esperó a que terminara una corrida ajena de `pytest` que saturaba ~10 de 12 hilos |
| cv2 | 4.11.0, 12 hilos, `useOptimized=True` |
| Frames | fixtures de `Screenshots_Triggers`, 2559×1440 (la resolución de captura real) |

**Trampa de la máquina quieta (anotarla).** El chequeo automático "¿hay otro `python.exe`?"
**dio falsa alarma en las dos corridas**. El `python.exe` del `.venv` es un *stub redirector*
(consecuencia del Python de NuGet, ver el doc de reconstrucción del entorno): lanza al intérprete
real como **proceso hijo**, así que un solo script se ve como dos procesos. Verificado por
parentesco y CPU: el stub (PID 13596) es el padre del intérprete real (PID 364) y acumula
**0,0 s de CPU** contra 21,8 s del hijo. **Contar procesos no sirve como chequeo de quietud en
esta máquina; hay que mirar tiempo de CPU.**

---

## 1 · Los números limpios

```
superficie=detector   n=39   p50=3572.3   p99=4542.0   max=4542.0 ms
```

Por pantalla (mismo detector, mismo tamaño de frame):

| pantalla | n | min | **p50** | max |
|---|---|---|---|---|
| S9 inventario discos | 15 | 3572 | **3650** | 4542 |
| S17 detalle disco | 8 | 3128 | **3391** | 4074 |
| S10 modal upgrade | 8 | 3067 | **3223** | 3787 |
| S12 transición | 8 | 3167 | **3443** | 4066 |

**Hipótesis 1 muerta: S9 no dispara ningún camino caro.** Hasta una S12 —una pantalla que el
detector *no reconoce*— cuesta 3,4 s. No hay nada que optimizar "del lado de S9".

**Los 4,3 s del planteo original eran con la máquina cargada.** El número limpio de S9 es
~3,6 s. La conclusión no cambia, el titular sí.

**Y cierra con lo observado en vivo:** el usuario midió 16 ciclos en 65 s = 4,05 s/ciclo en S9.
`classify` (~3,4 s) + `parse_disc_s9` (0,53) + `extract_s9_slot` (0,06) + contador (0,05) +
badge (0,01) ≈ **4,05 s**. El ciclo está explicado entero.

### Desglose del ciclo S9

```
_template_candidates (31 matchTemplate)   3083 ms   <- 83 %
_verify_s30                                322 ms
_verify_s9                                 325 ms
detect_active_tab                            0.3 ms
```

---

## 2 · El costo lo pone el FRAME, no el template

Esta es la parte contraintuitiva, y es la que decide el arreglo. Mismo frame, templates de
tamaños muy distintos:

| template | ms |
|---|---|
| 8×8 | **95,5** |
| 32×32 | 106,7 |
| 128×64 | 110,2 |
| 383×187 | 126,5 |
| **1022×431** | **123,6** |

**Un template de 8×8 cuesta lo mismo que uno de 1022×431.** Al revés, mismo template contra
frames de distinto tamaño:

| frame | Mpx | ms |
|---|---|---|
| 2559×1439 | 3,68 | 124,3 |
| 1919×1079 | 2,07 | 78,6 |
| 1280×720 | 0,92 | 31,1 |
| 640×360 | 0,23 | **5,5** |

**Causa:** `cv2.matchTemplate` con `TM_CCOEFF_NORMED` hace el trabajo pesado **del lado de la
imagen** (integrales + correlación por bloques con DFT sobre el frame entero), y OpenCV lo
**recomputa desde cero en cada llamada**. Es O(área del frame) por llamada, y `classify` la llama
31 veces. ~0,9 ms por Mpx por template.

**Hipótesis 2 (la sospecha principal) parcialmente muerta:** sí, "template matching a resolución
completa" era el lugar correcto — pero la lectura de que había que *bajar la resolución del
match* llevaba a recalibrar los 26 umbrales de `THRESHOLD_BY_STATE`. No hace falta (§4).

### El trabajo duplicado que ya estaba ahí

Dos redundancias que no dependen de nada de lo anterior:

1. **31 entradas usan 27 archivos.** `s17_personalizacion_pistas.png` lo matchean S17 y S26;
   `s9_inventario_general.png`, S9 y S30; `s23_sustitucion.png`, S23, S25 **y** S29. Son
   4 `matchTemplate` que calculan un número que ya se calculó — ~420 ms por frame.
2. **El OCR del header de S9 corre dos veces.** `_verify_s30` y `_verify_s9` llaman los dos a
   `_read_inventory_header` (331 ms), **mismo recorte, mismo OCR**. En un ciclo S9 se pagan 647 ms
   por un dato que se leyó una vez. Es la mitad de lo que cuestan los dos verifies juntos.

---

## 3 · El "~109 ms" del doc de latencia nunca fue una medición de `classify`

El doc del instrumental (2026-08-15, sección "Lo que lo destraba") dice:

> *"`classify` corre en **cada tick rápido (~109 ms)**, no a la cadencia."*

Eso se venía leyendo como "`classify` cuesta ~109 ms". **Nadie lo midió.** Los 109 ms son el
**período nominal del loop** (`app/core/monitor.py:875`): 100 ms de cadencia redondeados hacia
arriba por la granularidad de 15,625 ms de `GetTickCount64`. El comentario del código lo dice de
frente; lo que se coló fue el supuesto implícito de que `classify` entra cómodo en ese tick.
Entra 32 veces más lento.

**Consecuencia que excede la velocidad.** La FRESCURA de QA-06 se justifica así: *"el primer frame
en que se ve el estado nuevo ES el cambio de pantalla, con error acotado por el período del loop
(~109 ms)"*. Con `classify` en 3,5 s, **esa cota real es ~3,5 s, no 109 ms**. El razonamiento
sigue siendo válido; el número que lo acompaña está mal por un factor de 32, y está publicado.
Corregirlo es parte del cierre de esto.

---

## 4 · El techo alcanzable — el pase grueso LOCALIZA, el full-res CONFIRMA

Es el mismo movimiento que ya usamos en S30 (*Hough localiza, una constante encuadra*):

1. **Localizar** — una pasada a 1/4 de escala sobre los **27 archivos únicos** (~5,5 ms c/u).
   El que no llega a `umbral − 0,15` se descarta sin mirarlo más.
2. **Confirmar** — de los que sobreviven, se recorta un ROI de ±24 px alrededor del punto que
   marcó el pase grueso y **se matchea a resolución completa ahí adentro**.

Medido hoy, máquina quieta, contra la implementación actual:

| pantalla | actual | coarse-to-fine | ratio | candidatos |
|---|---|---|---|---|
| S9 | 3063 ms | **169,8 ms** | 18,0× | IDÉNTICOS |
| S17 | 3120 ms | **156,2 ms** | 20,0× | IDÉNTICOS |
| S10 | 3202 ms | **168,3 ms** | 19,0× | IDÉNTICOS |
| S12 | 3146 ms | **163,2 ms** | 19,3× | IDÉNTICOS |

Y sobre el corpus completo (102 frames muestreados de `Screenshots_Triggers`, **incluidos los 37
falsos positivos**; esta corrida fue con la máquina cargada, por eso el tiempo absoluto es mayor):

```
ACTUAL      3387.4 ms/frame
PROTOTIPO    178.0 ms/frame   (19.0x)
diferencias en la lista de candidatos: 0
```

### Por qué NO hay que recalibrar `THRESHOLD_BY_STATE`

Porque **el score final se sigue calculando a resolución completa, sobre el píxel original**. El
pase grueso no decide nada: solo decide *a quién vale la pena confirmar*. Sobre los 126 positivos
del corpus (los que a full-res superan su umbral), el score del ROI dio **idéntico al global a 4
decimales** en 123, y en los otros 3 la diferencia fue ≤0,0001 (ruido de float32).

### Por qué es anti-FP por construcción

El máximo sobre un subconjunto no puede superar al máximo global. El ROI **solo puede
subestimar** ⇒ **no puede crear un falso positivo**, nunca. El único riesgo posible es perder un
positivo, y eso se midió: **0 pérdidas en 126 positivos**, con cualquier padding probado
(8/24/64 px).

*(Aparecieron 24 filas donde el ROI daba "más" que el global. Se revisaron una por una: todas con
delta +0,0000 — el epsilon de comparación estaba más ajustado que la precisión de float32. No era
una anomalía.)*

### El margen del shortlist

El peor positivo de todo el corpus quedó a **−0,029** de su umbral en el pase grueso
(`s10_modal_upgrade` sobre un frame pre-max). Con margen **0,15** hay ~5× de holgura, y el
shortlist queda en 6,2 templates por frame de media (p95 = 11).

### Riesgo residual — cerrado de entrada, no dejado como opción

La distancia entre el argmax grueso y el argmax full-res es p50 = 1 px, p95 = 9 px — pero **llegó
a 167 px** en un caso. Ahí el ROI mira el lugar equivocado y el score sale bajo.

Este doc proponía los top-K picos como cinturón opcional. **Se implementó desde el principio**
(decisión de Daniel): en un módulo load-bearing donde el proyecto ya invirtió una fase entera en
endurecer falsos positivos, pagar ~4 ms por pico para eliminar el único modo de falla conocido no
es una relación discutible.

Y al implementarlo apareció una **segunda razón, independiente y más fuerte**: el diagnóstico de
S12 la necesitaba (§4.1).

### 4.1 · El diagnóstico de S12 no era cosmético

`s12_diag` reporta la confianza del mejor match global "por si a nadie le alcanza el umbral". Se
lo trató como un dato de log — y no lo es: [`monitor.py`](../../app/core/monitor.py) lo usa para
decidir si un frame no-detalle **resetea la identidad latcheada** (`_DETAIL_RESET_MIN_CONF = 0.50`).
Es el mecanismo que evita el latch sostenido: un fundido de transición (conf ~0) no debe resetear,
una pantalla real sí.

**Y el máximo global exacto es incompatible con el arreglo**: conocerlo exige matchear los 31
templates a resolución completa, que es justo lo que se eliminó. No hay forma de preservarlo.

Medido sobre los 102 frames, comparando contra el valor viejo en los 22 donde el diagnóstico manda:

| variante | cruces del umbral 0.50 | max \|dif\| |
|---|---|---|
| solo el mejor pico | **1** ⚠️ | 0,0906 |
| máximo del pase grueso | **1** ⚠️ | 0,0906 |
| solo los confirmados del shortlist | **1** ⚠️ | 0,5194 |
| **top-3 del pase grueso, confirmados** | **0** ✅ | 0,0648 |

El cruce era real: `Modo_Libre_3.png` pasaba de 0,553 (resetea el latch) a 0,493 (no resetea).

Por eso se confirman **siempre** los `_COARSE_DIAG_TOP = 3` mejores del pase grueso, aunque no
lleguen al shortlist. Con eso el valor reportado queda **sandwicheado** entre el máximo del top-3
(que nunca cruzó) y el máximo global real (que es la referencia) ⇒ **cero cruces por construcción**,
no por suerte.

Lo que sí se garantiza y quedó fijado en tests: el diagnóstico **solo puede subestimar** (el ROI
barre un subconjunto), y un diagnóstico inflado —el peligroso— es imposible.

---

## 5 · Veredicto

**El resto vale la pena.** `classify` es el 83 % del ciclo, el arreglo da 18-20× con salida
idéntica verificada sobre 102 frames, y no toca ningún umbral calibrado.

Proyección del ciclo S9: **~4,05 s → ~1,3 s** (170 ms de templates + 331 de un solo OCR de header
+ 528 de `parse_disc_s9` + ~130 del resto). Para los 405 discos del censo: **~30 min → ~9 min**.

**Orden acordado, tres entregas separadas:**

1. Re-medir con la máquina quieta y dejarlo escrito — **este doc**. ✅
2. **El refactor solo** — coarse-to-fine + dedup por archivo + picos múltiples. ✅ (abajo)
3. **El caché del OCR del header, aparte** — por llamada, no global. ⏳

Queda pendiente además corregir la cota de frescura del doc de latencia (§3).

---

## 6 · Resultado del paso 2 (implementado)

`_template_candidates`: **3083 ms → 183,5 ms (16,8×)**. Medido con el instrumental QA-06, máquina
quieta:

| pantalla | antes | después | |
|---|---|---|---|
| S17 detalle disco | 3391 ms | **169 ms** | 20,0× |
| S12 transición | 3443 ms | **196 ms** | 17,6× |
| S10 modal upgrade | 3223 ms | **206 ms** | 15,6× |
| S9 inventario discos | 3650 ms | **788 ms** | 4,6× |

**S9 se queda atrás a propósito:** eliminado el pase de templates, lo que domina su ciclo es el
OCR del header corriendo dos veces (§2) — 586 de sus 788 ms. Es exactamente el paso 3.

Verificación: **1698 unit + 79 del QA negativo de FP + 28 de integración/regresión, 0 fallos.**

Lo que fija `app/tests/unit/test_detector_template_pipeline.py`:

- El coste se mide **contando llamadas, no cronometrando** (un assert de tiempo en Windows es
  flake conocido): cero `matchTemplate` sobre imágenes de ≥1 Mpx, y ningún archivo de template
  matcheado más de `1 + _COARSE_PEAKS` veces.
- Los candidatos salen **idénticos** a un baseline congelado con la implementación vieja.
- El diagnóstico de S12 solo puede subestimar y no cambia de lado del umbral 0.50.
- Un frame adversario donde el pase grueso apunta al lugar equivocado: **se le rompió el test a
  propósito** (con 1 pico reporta 0,928 contra un máximo real de 1,000) para verificar que tiene
  dientes antes de darlo por bueno.

---

## Apéndice · Lo que NO era

| hipótesis | veredicto |
|---|---|
| S9 dispara un camino caro (`_deep_detect_s18`, muchos candidatos) | **Falsa.** Todas las pantallas cuestan 3,2-3,7 s |
| El frame full-res sin downscale es el problema | **A medias.** El problema es el área del frame **× 31 llamadas**; el downscale ingenuo obligaba a recalibrar umbrales, y no hace falta |
| `classify` costaba ~109 ms según QA-06 | **Nunca se midió.** 109 ms es el período del loop |
| Hay que correr el QA negativo por si el downscale mete FP | **Se corre igual**, pero el ROI no puede meter FP por construcción |

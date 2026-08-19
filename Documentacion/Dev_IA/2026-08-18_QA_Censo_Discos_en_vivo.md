# QA en vivo del censo de discos — lo que se rompió y las tres veces que medí mal

> **2026-08-18**, sesión de captura real con escritura a la DB.
> Continúa [`2026-08-18_IMPL_Censo_Discos_con_contador.md`](./2026-08-18_IMPL_Censo_Discos_con_contador.md).
> Estado al cierre: DB reiniciada, dos bugs de campo arreglados, censo listo para la pasada larga.

---

## 0. Resumen

| | |
|---|---|
| discos capturados | 13 (en tandas cortas de validación) |
| bugs de campo encontrados | 2, los dos arreglados |
| **hipótesis mías desmentidas por la medición** | **3** |
| pérdida de datos | ninguna (la DB se reinició a propósito para la pasada limpia) |

Lo primero que funcionó fue el arreglo del día anterior: los ids **6 y 7** son dos discos
`Firmamento llameante · slot 3 · DEF · Nv15` — firma idéntica bajo la clave vieja. El libre habría
**pisado** al de Pyrois. Se separaron por substats. El fix de la clave se validó solo, en los
primeros 7 discos de la corrida real.

---

## 1. Bug de campo #1 — el censo contaba dos veces lo que la persistencia reconocía

```
21:14:51  Disco S9 detectado: Firmamento llameante slot=3 DEF  dueno=-
21:14:51  [censo-discos] 8/405                     ← el censo: "disco NUEVO"
21:14:51  Disco LIBRE persistido id=7 libre_update ← la persistencia: "ya lo tenía"
```

Contador en 10, filas en la DB 8.

**Causa.** Las dos capas usaban definiciones distintas de "mismo disco":

| capa | clave | resultado |
|---|---|---|
| persistencia | `set_id` **resuelto** (matcher difuso) | reconoce el disco |
| censo | el **string** del nombre del set | lo cuenta de nuevo |

Y el OCR lee el nombre del set inconsistente entre pasadas — `Firmamento Ilameante` (I mayúscula)
vs `Firmamento llameante` (l minúscula) normalizan **distinto**, porque son caracteres distintos.
El resolvedor difuso se come esa diferencia; comparar strings no.

**Arreglo.** El censo cuenta la **fila que la persistencia decidió tocar** (`disc_id`), no un
recálculo propio. Una autoridad, no dos. Sin fila (read-only) cae a la identidad del parser y lo
declara **provisorio**, en vez de presentar el total como si todo tuviera el mismo respaldo.

**Lo incómodo:** yo había escrito un test llamado
`test_usa_la_MISMA_identidad_que_el_dedup_de_emision` para prevenir exactamente esto. Verifica que
se **llame a la misma función**, sobre datos sintéticos donde el nombre del set es constante. No
puede ver que las dos capas discrepen cuando el OCR varía. Escribí el principio correcto —*"dos
definiciones de mismo disco sería una de más"*— y lo implementé **duplicando la función** en vez de
**deferir a una sola autoridad**.

---

## 2. Bug de campo #2 — un dueño que no se puede nombrar tira el disco entero

Daniel: *"paré en un disco que debería tener Soukaku y no lo detecta"*.

```
Ben      sim=0.897
Soukaku  sim=0.897      margen 0.000   → el matcher se abstiene
```

La abstención es **correcta**: con esos datos no puede decidir. Pero río abajo,
`persist_s17_disc` sólo escribe si hay dueño confiable **o** si se afirmó libre. El tercer caso
—*"tiene dueño y no sé quién"*— no tenía camino, y el disco se descartaba **entero**: se perdían
set, slot, nivel y los cuatro substats, que sí se leyeron bien. Medido: **3 de 38 (8 %)**.

### No era un umbral mal puesto

| superficie | separación Ben ↔ Soukaku |
|---|--:|
| `grid` (la que usaba S9) | **1,04 – 1,14×** |
| `detail` (histograma de color) | **8,87×** |

En la grilla las refs de Ben están casi tan dispersas entre sí como respecto a Soukaku: **no existe
umbral** que los separe. En el detalle, sí. La información estaba; no se estaba mirando.

### La segunda superficie

El panel derecho del S9 también muestra el avatar del dueño. `crop_s9_detail_badge` lo lee, y
sobre los 14 fixtures (`tools/audit_s9_surfaces.py`):

```
nombrados: grilla 6/14 · detalle 7/14
acuerdos 4 · DESACUERDOS 0 · rescates del detalle 3 · libres coincidentes 4
```

**Cero desacuerdos** — donde las dos hablan, dicen lo mismo. Y el detalle rescata 3 casos que la
grilla pierde (2 sin tile localizado, 1 abstención por look-alike). Sobre el frame real de Soukaku:
grilla abstiene 0.911, detalle **Soukaku 0.814 con margen 0.379**.

### Los dos señuelos de la ROI

La zona tiene tres círculos y sólo uno es el avatar:

```
hexágono del nº de slot   izquierda   sat ~12
badge dorado de rareza    abajo       sat ~119   ← el MÁS saturado
avatar del dueño          derecha     sat ~58
```

Elegir "el más saturado" agarra siempre el de rareza: daba **0.47 constante en los 14 fixtures**,
incluidos los libres que no tienen avatar. **El discriminador es la POSICIÓN.** Tercera vez que la
saturación no separa lo que parece (S17 junio, RF-15 armas, y ahora esto).

Y el radio va **como constante** (18 px), no de Hough: con 18 nombra a 0.843; con 22, 25, 26 o 30
se abstiene. Misma lección que S30.

---

## 3. Las tres veces que medí mal

Vale más que los arreglos, porque las tres tienen la misma forma: **afirmé antes de medir.**

### 3.1 "El sleep es el 83 % del ciclo" — era 0 %

Propuse bajar `polling_cadence_ms` de S9 de 1500 a 700 ms, razonando que el ciclo era
`sleep + procesamiento`. Medido:

```
cadencia 1500 ms  →  16 ciclos / 65 s
cadencia  700 ms  →  16 ciclos / 65 s      idéntico
```

La cadencia es un **período mínimo**, no una pausa agregada. El procesamiento (4 s) ya excedía la
cadencia, así que el sleep valía cero. Revertido, con la medición anotada en el docstring para que
nadie reintente.

### 3.2 "La GPU es la palanca" — el cuello no es el OCR

Perfilado de un ciclo S9:

```
classify (detección de pantalla)   4189 ms   ← 87 %
parse_disc_s9 (OCR del panel)       528 ms
extract_s9_slot (OCR)                60 ms
contador del header                  53 ms
badge del dueño                      13 ms
```

El cuello es el **detector**, no el OCR. (Queda como tarea aparte: la memoria del proyecto registra
`classify ~109 ms` del instrumental QA-06, así que hay 40× sin explicar.)

### 3.3 "Hay 8 refs mal etiquetadas" — falso, y casi rompo la librería

Inventé una métrica: *distancia de cada ref al centroide de su propia clase vs al de otra*. Dio
que 4 refs de "Ben" estaban 8× más cerca de Soukaku, y concluí contaminación.

**No vale para una clase bimodal.** Ben tiene dos grupos de refs; el centroide cae en el medio y
desde ahí *los dos* grupos parecen lejanos. Al sacar esas 4:

```
antes:  TOP-1 93.3%  ·  wrong 2.4%  ·  Ben(ok=3, ab=1)
después: TOP-1 91.5% ·  wrong 4.9%  ·  Ben(ok=0, wr=4)   ← todas a Soukaku
```

Eran refs **legítimas y load-bearing**. Revertido desde backup, 93,3 % confirmado.

Lo que me salvó fue **medir antes y después con la herramienta validada** (`measure_badge_lib.py
--against-labeled`) en vez de confiar en mi métrica nueva. El proyecto ya tenía escrito *"la
métrica mentía de tres formas"*; yo agregué una cuarta.

---

## 4. El ritmo: el método del usuario era mejor que mi indicación

Daniel avanzaba al disco siguiente **cuando saltaba el log** — un lazo de realimentación que por
construcción no pierde discos (7/7 en la primera tanda). Le pedí que contara **5 segundos fijos** y
eso rompió el lazo: **5 de 15 perdidos**. Un intervalo ciego no puede saber cuándo maduró cada
disco, que es lo que varía.

Con el ciclo real en ~4,3 s y su método, la pasada de 405 discos son **~30 min**.

---

## 5. Cosas menores que quedaron anotadas

- **El contador dice 405, no 339.** Los fixtures eran de un momento anterior; el denominador es en
  vivo. La brecha por gemelos sigue valiendo: la pasada no va a llegar a 405.
- **`farm_nodes.toml` no se empaqueta en el `.exe`** — error en cada arranque, pantalla S13. Tarea
  aparte.
- **El guard de instancia única** puede quedar con un socket vivo tras un kill: si la app "sale
  porque ya hay una corriendo" y no hay proceso, revisar con `Win32_Process` filtrando por
  `CommandLine`, no por nombre.
- **Con el juego cerrado el monitor no arranca** y el log queda mudo tras "Logging iniciado". No es
  un cuelgue: `py-spy dump` muestra `app.exec()` idle, o sea la app viva esperando la ventana.

---

## 6. Estado al cierre

DB reiniciada con RNF-01 (`backup_precenso2_20260818_230337`): `inventory_discs` 13 → 0,
`roster_declarations` 58 y `agents` 51 conservados, PRAGMAs en verde. La app corre desde fuente con
los dos arreglos. **Falta la pasada larga.**

Sin commitear todavía: el fix de la autoridad de identidad, la segunda superficie
(`crop_s9_detail_badge` + cableado), `tools/audit_s9_surfaces.py` y esta nota.
Suite relacionada en verde (65 tests); **falta la suite completa**.

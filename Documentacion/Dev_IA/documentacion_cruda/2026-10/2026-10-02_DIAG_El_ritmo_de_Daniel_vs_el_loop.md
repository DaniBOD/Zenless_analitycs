# DIAG · El ritmo de Daniel contra el loop de captura (2026-10-02)

> Daniel, después de farmear y desmontar "a mi ritmo normal": "tengo 379 discos pero en la DB
> figuran 418 … el sistema no es suficientemente rápido para seguir mi ritmo … ¿el sistema capta
> mis inputs? … ese es nuestro gran desafío: la latencia y la robustez de los datos in-game".

Sesión medida: 13:41 → 14:07 (log `app.log`, latencias `db/metrics.db`, bitácoras
`audit/desmontajes/20261002_1357*`, `…_1359*`). App desde fuente con `-Metrics`.

## 1. Dónde se ve: el desmontaje

| tanda | declarados (contador N/300) | con datos | dados de baja | no estaban en la DB | sin leer |
|---|---|---|---|---|---|
| 13:55 → 13:57 | 63 | 41 | 29 | 12 | **22** |
| 13:59 → 13:59 | 10 | 6 | 0 | 6 | **4** |
| 14:00 → ? | 10 | — | — | — | **10** (la tanda nunca se cerró) |

- **36 discos destruidos en el juego siguen activos en la DB** (22 + 4 + 10). Es casi toda la
  brecha 418 − 379 = 39.
- Además, 18 discos se leyeron pero **no matchearon** ninguna fila: o nunca se capturaron, o su
  fila quedó vieja (una mejora que no se confirmó cambia la identidad). No sacan filas de la DB,
  pero tampoco las agregan; hay que mirarlos uno por uno en el censo.
- La tercera tanda: confirmación a las 14:00:56 y vuelta a S11 a las 14:00:58. El "Obtenido" del
  desmontaje (S24), que es lo que la cierra, **no llegó a detectarse**. Es un bug aparte del ritmo:
  la tanda debería cerrarse aunque el "Obtenido" pase en menos de un ciclo.

## 2. Por qué: el ciclo es más lento que el click

Intervalo entre selecciones de Daniel (líneas `+1 →`): **27 de 1 s, 21 de 2 s**, 8 de 3 s.

Costo por ciclo en S11 durante la primera tanda (131 s, 247 ciclos, `metrics.db`):

| etapa | p50 | p90 | qué es |
|---|---|---|---|
| **período del loop** | **407 ms** | **922 ms** | un frame leído cada ~0,4-0,9 s |
| detector | 188 ms | 193 ms | clasificar la pantalla **en cada ciclo**, aunque siga en S11 |
| despacho S11 | 72 ms | 571 ms | el p90 es el OCR del panel cuando hay disco que aparear |
| captura (mss) | 41 ms | 47 ms | |

La bitácora sólo le atribuye un disco a una celda si entre dos frames cambió **una sola**
tilde y el contador subió **uno** (`_process_s11_desmontaje`): es lo que la hace segura. Con un
click por segundo y un frame cada 0,4-0,9 s, seguido entran **dos clicks en la misma ventana** →
delta de dos celdas → no se puede decir cuál es cuál → "sin leer". El diseño no está mal: está
leyendo muy pocas veces por segundo para ese ritmo.

**Lo mismo vale para el resto del ciclo de vida:** la mejora de hoy a las 13:45 (S10 abierta ~2 s,
el primer frame legible ya en Nv 3) y el "Obtenido" del desmontaje que no se vio son el mismo
fenómeno. Lo que dura menos que un par de ciclos en pantalla, no existe para la app.

## 3. ¿La app capta los inputs?

**No.** Hoy no hay ningún listener: todo sale de mirar la pantalla por polling. RNF-03 permite
leer (nunca enviar) con `pynput.keyboard.Listener`; un `pynput.mouse.Listener` es la misma
categoría: un hook pasivo de Windows que **lee** dónde y cuándo se hizo click, sin tocar el juego
ni su memoria. Igual es una ampliación de lo que dice RNF-03 y la decide Daniel.

Lo que daría el click, combinado con mss:

- **cuándo mirar:** cada click dispara una captura a los ~150 ms (lo que tarda la animación), en
  vez de esperar el próximo ciclo;
- **qué se hizo:** la posición del click dentro de las regiones conocidas de cada pantalla
  ("Desmontar", "Mejorar", la celda N de la grilla) es una segunda evidencia, independiente de la
  imagen. En S11, "click en la celda 7" + "la tilde 7 apareció" atribuye aunque haya dos clicks
  en la misma ventana;
- **cuántas veces:** cada click en "Mejorar" es un paso de mejora, aunque la pantalla no llegue a
  mostrarlo.

## 4. Cómo mejorarlo (de lo más barato a lo más profundo)

1. **No re-clasificar la pantalla en cada ciclo (−188 ms por ciclo).** En un estado estable alcanza
   con verificar barato que seguimos ahí (el ancla del estado) y correr el clasificador completo
   sólo cuando el ancla falla. Medido acá, el detector es el 46 % del ciclo: el período bajaría de
   ~400 a ~200 ms sin tocar nada más. Antes de prometerlo: medirlo en S11, S22 y S10 (A1).
2. **Capturar rápido y procesar después.** Separar el "ver" del "entender": un hilo captura a
   alta frecuencia sólo la región que cambia (tildes, panel, barra de nivel; mss ~40 ms el frame
   entero, mucho menos un recorte) y encola los frames distintos; el OCR los consume en orden. La
   pantalla se va, pero el frame queda. Es el cambio de arquitectura de fondo.
3. **Clicks como disparador y como evidencia** (sección 3), si Daniel lo aprueba bajo RNF-03.
4. **Cerrar la tanda de desmontaje aunque el "Obtenido" pase volando** (bug de la tercera tanda).
5. **Después, un censo** (S9 con el contador N/xxx) para dejar la DB igual al juego.

## 5. Siguiente

- Daniel decide el punto 3 (leer clicks bajo RNF-03).
- Medir el punto 1 antes de diseñarlo.
- El censo va **después** de los arreglos: hecho antes, la DB se vuelve a desviar en la próxima
  sesión de farmeo.

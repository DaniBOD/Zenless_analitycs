# El reloj de la frescura medía el epoch, y la espera de los 3 segundos la pone el warmup

**2026-09-15.** Commit `feac3c4`. Fase 0 de un trabajo de 4 fases que sigue abierto: las fases 1-4
están pendientes al cierre de este doc.

## De dónde salió

Daniel pidió un censo de discos nuevo y, antes, bajar la latencia del log — porque **el log es su
señal de avance**: pasa al disco siguiente cuando salta la línea. Mi primera lectura fue que el censo
es *human-bound* (11-20 s por disco) y que optimizar no lo acortaría. Él la corrigió:

> *"tengo pausas constantes para esperar que el log salga, es decir que el sistema diga «eh ya
> capturé este disco puedes proseguir» y yo estaba listo para pasar hace 3 segundos o más"*

Medido, tenía razón y yo estaba mirando el problema al revés. **La espera no es su tiempo de
reacción: es una espera deliberada del código.** El número heredado ("human-bound") escondía que una
parte del intervalo por disco la pone el sistema — A1, un número heredado no es una medición.

## 1 · El instrumento que tenía que responder esto estaba roto

`frescura_estado_a_log` abría el cronómetro con `time.monotonic()` (el reloj del loop rápido) y lo
cerraba con `time.time()`. La resta de dos relojes distintos **no da un número malo: da el epoch
entero**, ~1,789e12 ms. Había **14 muestras así, de un mes atrás**, y ningún test tocaba la métrica.

⭐ **Lo que hace peligroso a este bug no es la resta, es que el síntoma se disfraza de dato.** Una
métrica de latencia rota se ve *igual* que una métrica de latencia mala: un número grande parece "ah,
estuvo lento". No hay nada en el reporte que grite. Por eso sobrevivió un mes en una tabla que se
consulta justamente para decidir qué optimizar.

**No se arregló la línea, se arregló de quién es el reloj** (B1, una sola autoridad por pregunta):

- `metrics.ahora()` entrega el instante y `metrics.registrar_desde(superficie, t0)` hace la resta
  **adentro del módulo**. Ningún llamador vuelve a elegir reloj.
- Red de seguridad en `registrar()`: una muestra negativa o mayor a una hora se **descarta** y avisa
  **una vez por superficie**. Ninguna superficie con presupuesto de 20-500 ms puede tardar una hora,
  así que ese valor no es lentitud, es el cronómetro mal cerrado. Mejor un agujero ruidoso que un
  percentil envenenado.

Barrido del resto del repo: **era la única mezcla**. `teardown_batch` usa `monotonic` en sus 3
puntos y los censos usan `time.time()` en los suyos — cada objeto es internamente consistente.

## 2 · La métrica que faltaba: la frescura del CONTENIDO

La frescura existente mide **cambios de pantalla**. Lo que Daniel vive en un censo es un cambio de
**contenido sin cambio de pantalla**: la pantalla queda quieta y cambia el disco mirado. El doc de
QA-06 §10 ya decía de frente que la de pantalla *no cubre* ese caso, así que **su queja no tenía
instrumento**: aun con el reloj arreglado, el número que él describía no existía en ninguna parte.

| superficie nueva | qué mide |
|---|---|
| `frescura_disco_a_log` | del primer despacho que ve el disco nuevo, hasta su línea en el log |
| `frescura_disco_warm` | el **subconjunto** que pasó por el warmup del dueño |
| `loop_period` | período real del loop rápido, explícito |
| `s17_owner_sample` | el muestreo del dueño, que corre en cada pasada rápida en S17 |

Dos decisiones de diseño que importan más que el código:

- **Apertura y cierre gobernados por la MISMA firma** (la del handler de despacho), aunque en S17 el
  loop rápido note el disco nuevo unas decenas de ms antes. Con dos firmas de umbrales distintos, un
  parpadeo re-abriría el cronómetro y la muestra saldría **corta** — sesgada hacia lo optimista justo
  en el caso que se quiere medir. Lo que queda afuera se mide aparte con `loop_period`.
- **`_warm` como subconjunto, no como flag en el mensaje.** Comparar los dos p50 **atribuye** la
  espera; un solo número obliga a interpretarla.

## 3 · La causa raíz de los 3 segundos

El disco se lee, **madura** (`disc_is_mature`: set + slot + main + substats) y ahí el código
**posterga la emisión a propósito** si el dueño quedó incierto:

- **S9** (la pantalla del censo, `Pistas de disco [N/3000]`) — `_s9_warming`: reintenta el badge
  hasta `_S17_AGG_MAX_CYCLES = 5` ciclos.
- **S17** — difiere hasta juntar `_S17_OWNER_MIN_SAMPLES = 4` pasadas del loop rápido.

⭐ **El warmup se cuenta en PASADAS del loop, no en tiempo**, y su constante declara el supuesto en el
comentario: *"2 es ~0.2 s al loop rápido (10 fps)"*. **El loop no corre a 10 fps.** Medido:

| | nominal / declarado | medido |
|---|---|---|
| período del loop rápido | `_FAST_CAPTURE_MS = 100` ("template match en ~50ms") | **p50 391 ms** · p99 4547 · max 8579 (n=416) |
| `detector` (classify) | presupuesto 50 ms | **p50 193 ms** (y 192 ms tres días antes: estable) |

⇒ Una espera diseñada para 0,4-0,5 s hoy dura **~1,6 s a p50**, y la cola es peor. **Dos
multiplicadores encadenados**: `classify` infla cada pasada, y el warmup multiplica la pasada por
4-5. Cada ms que se le saque a `classify` se cobra **×5** en la espera que el usuario siente.

⚠️ **El warmup no es un bug y no se baja a ciegas.** Existe porque con 1 sola muestra el voto del
dueño es frágil y el disco sale "dueño incierto" (5R.L.6) — lo que costó 3 de 38 discos antes de
`6d36f78`. Lo que está mal es su **condición de salida**: un conteo de pasadas se estira en silencio
cuando el loop se pone lento. La evidencia exigida no cambia; cambia cuándo se deja de esperar por
algo que no va a llegar. Precedente a reusar: `equip_libre` ya corta el warmup de S9 por esta misma
razón (*"reintentar el badge de un disco que YA se afirmó libre es esperar algo que no va a
aparecer"*).

## 4 · Verificado EN VIVO, no sólo en los tests

La app corrió en readonly con `-Metrics`. Daniel no llegó a recorrer S9/S17, así que
`frescura_disco_a_log` sigue en 0 muestras — eso es la Fase 1. Lo que igual quedó probado:

- **`loop_period` disparó solo: n=416, mínimo 281 ms.** El loop **nunca** se acerca a los 109 ms
  nominales, y esto ya no es inferido de los huecos entre muestras de `detector`: está medido.
- **`frescura_estado_a_log` volvió a dar números plausibles**: p50 **1094 ms**, max 12438 ms, contra
  un presupuesto de 500 ms. O sea que la métrica no sólo dejó de mentir: **destapó que la frescura de
  pantalla está 2,2× fuera de presupuesto a p50**, algo que nadie podía ver mientras devolvía el
  epoch. El max de 12,4 s coincide con la carga del modelo de OCR (`ocr_text` max 5941 ms en la misma
  corrida) — el freeze conocido del arranque, fuera de alcance acá.
- sha256 de la DB de dominio **sin cambios**.

## 5 · Discos y engines NO se arreglan igual (pregunta de Daniel)

| | discos (S17, S9, S3, S5) | engines (S26, S30) |
|---|---|---|
| agregador + maduración + techo | **sí** | **no existe** |
| warmup que posterga la emisión | **sí** | no |
| compuerta por firma | resetea el agregador; re-OCR cada ciclo hasta emitir | **arriba de todo**: panel quieto ⇒ `return`, cero OCR. Una lectura **por arma mirada** |
| voto del dueño entre frames | sí, y **retiene** el disco | sí, pero **no retiene**: decide con lo que tiene (abstención pegajosa si osciló) |
| **la palanca** | *cuándo dejás de esperar* (política, no cómputo) | *el costo de un ciclo*: `dispatch:S26` **p50 2747 ms** contra cadencia 1000 |

⭐ Y una lectura que cambia el significado del número: como S26 vuelve inmediatamente cuando el panel
está quieto, **sus 21 muestras no son ciclos promedio, son las pasadas que efectivamente leyeron**.
Los 2747 ms son el **costo de leer un arma**, no un promedio diluido.

Lo único que comparten es `classify` y el período del loop — y la primitiva de OCR, que es código
compartido de verdad (`parser_weapon_s26` reusa `_ocr_detail_lines` de `parser_disc_s17`).

**Decisión de Daniel:** los engines se ven **en un segundo censo de QA**, después del de discos. No
se agregó `frescura_arma_a_log`: mezclar las dos palancas haría que ninguna mejora se pueda atribuir.

Hueco honesto: **sé que el ciclo de S26 cuesta 2747 ms pero no sé en qué se van.** Dos OCR a ~130 ms
de p50 no explican 2,7 s; faltan ~2,5 s por atribuir. Eso es diagnóstico pendiente, no una hipótesis
que quiera defender.

## 6 · De paso: `report_latency` se moría justo cuando servía

El `⚠️` del veredicto no existe en cp1252, así que al redirigir la salida tiraba
`UnicodeEncodeError`. Y ese emoji sale **sólo** en las líneas de superficies **fuera de
presupuesto**: la herramienta de latencia se caía exactamente en el único caso en que hay algo que
reportar. Verificado que es previo a este cambio (la versión de `HEAD` falla igual). Arreglado con
`reconfigure(encoding="utf-8", errors="replace")`.

## 7 · Lo que queda pendiente (fases 1-4)

1. **Fase 1 — baseline medido** (Daniel, ~5 min): recorrer S9 y S17 con `-Metrics`. Sin ese "antes"
   no se toca el warmup. **Si `frescura_disco_warm` sale con p50 parecido al general, mi hipótesis
   está mal** y hay que volver al diagnóstico.
2. **Fase 2 — la espera**: condición de salida del warmup por evidencia + techo de ms de pared, y
   recién después mirar si `classify` tiene margen (ya se optimizó 16,8× en `3a5889a`). Un cambio por
   vez, midiendo entre cada uno.
3. **Fase 3 — `nivel`: separar "no leído" de "nivel 0"** (pendiente desde el cierre del 2026-08-30).
   Hoy hay **23 discos en nivel 0** y no son verificables: los 12 que tienen 3 substats son
   exactamente los 12 de nivel 0 (consistente con la regla de ZZZ del 4º substat a +3), pero un
   nivel 15 mal leído como 0 es indistinguible de los otros 11. Cuatro trampas ya localizadas:
   - `disc_is_mature` usa `0 <= nivel < 3` para pedir **3** substats; con `None` pediría **4**, y
     discos de nivel bajo dejarían de madurar — el bug del QA 2026-06-27 (Velina Nv0), que además
     **empeoraría la latencia** que la Fase 2 vino a arreglar;
   - `repositories.py` usa `nivel=?` en la clave de dedup y **`nivel = NULL` no matchea nunca** en
     SQL ⇒ el disco se insertaría **duplicado** en vez de actualizar su fila;
   - la columna es `nivel INTEGER DEFAULT 0`, sin `NOT NULL` ni `CHECK` ⇒ **no hace falta migración**;
   - la UI repite el colapso: `app/ui/discos/datos.py` hace `int(r[24] or 0)`, que vuelve a convertir
     NULL en 0. Va a "sin leer", como en Roster y Armas.
4. **Fase 4 — el censo**: pasada completa de los 385 discos por S9, con la app escribiendo, backup y
   PRAGMAs (RNF-01). La pregunta que esta fase existe para responder: **de los 23 nivel-0, cuántos
   eran genuinos.**

## Verificación de este commit

- Suite **2929 passed / 0 failed / 0 skipped** (17:46). ⚠️ El baseline que yo arrastraba (2915)
  **estaba corrido en uno**: medido, son 2916 + los 13 nuevos. Otra vez A1 — el número venía de un
  resumen, no de una medición.
- **Sabotaje (A3), dos veces, las dos detectadas:** volviendo el cierre a `time.time()` se ponen
  rojos 2 tests; sacando la llamada de apertura del handler de S17 se ponen rojos los **2 que manejan
  `_process_disc_s17_continuous` de verdad**. Esos dos son la defensa contra **A2**: sin ellos los
  tests pasarían aunque nadie invocara la instrumentación desde el pipeline, que es precisamente cómo
  una métrica puede existir y no medir nada.
- sha256 de `db/danibod_zzz_v2.db` idéntico antes y después.
- No cambia el comportamiento de captura: sólo mide.

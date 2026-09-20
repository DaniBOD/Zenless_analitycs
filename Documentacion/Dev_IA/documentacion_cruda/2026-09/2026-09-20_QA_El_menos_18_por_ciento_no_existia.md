# El −18 % no existía: dos medianas de n=10 con los intervalos solapados

**2026-09-20 · QA de la medición · corrige al
[PERF de la Fase 2](2026-09-17_PERF_Latencia_del_log_en_S9_lo_que_midieron_las_pasadas_A_y_B.md)**

> Daniel, después del censo: *"el tema de la latencia es la medición"*. Tenía razón.

## 1. Qué se afirmó

La Fase 2 declaró que el click→log en S9 bajó de **3109 a 2562 ms (−18 %)** entre la Pasada A y la
Pasada B. Sobre esa base se dio la fase por cerrada, y el 2026-09-17 reporté que el censo (p50
**3547 ms**) era una **regresión de ~830 ms** contra ese 2562.

**Las dos afirmaciones caen.** Ninguna de las dos se sostiene con los datos que las respaldan.

## 2. Qué son realmente esos números

Las muestras de `frescura_disco_click_a_log` de cada pasada, crudas y ordenadas:

```
Pasada A (16-09 22:00, n=10): 2000 2219 2781 3061 [3109] 3125 3250 3703 3828 4406
Pasada B (17-09 00:00, n=10): 2156 2171 2187 2328 [2561] 3139 3235 3235 3375 10828
```

**Los dos titulares son el quinto valor de diez.** Con n par no hay un medio: hay dos. El
instrumento (`metrics.percentile`) usa **rango más cercano** —`ceil(n·p/100)−1`— y elige el de
abajo. No es un bug: la función es correcta y su docstring explica que arregla un off-by-one previo.
Pero con n=10 los dos valores centrales de la Pasada B difieren un **22 %** (2561 vs 3139): la
convención, y no el sistema, decide el titular. La mediana real de B es ~2851.

## 3. Remuestreo: los intervalos

Bootstrap de la mediana, 4000 réplicas, IC 95 %:

| pasada | n | mediana | IC 95 % |
|---|---|---|---|
| A — el "antes" | 10 | 3117 ms | **2641 – 3703** |
| B — el "después" | 10 | 2851 ms | **2188 – 3305** |
| censo de discos | **383** | 3547 ms | **3359 – 3688** |

- **A y B se solapan casi por completo** ⇒ no se puede afirmar que la Fase 2 haya mejorado la
  espera. El −18 % está dentro del ruido de sus propias 10 muestras.
- **El censo es indistinguible de A**, el estado *previo* a las optimizaciones (3359–3688 contra
  2641–3703).
- El censo **sí** difiere de B, y ese fue el "hallazgo" que reporté: una diferencia contra un punto
  que nunca tuvo esa precisión.

**Salvedad honesta:** las pasadas (10 discos, ritmo tranquilo) y el censo (380 discos seguidos, con
dos relevos del worker de OCR) tampoco son la misma condición. El solapamiento **no prueba que no
haya diferencia**; prueba que con estos datos **no se puede afirmar ninguna**. Es la diferencia
entre "no hay efecto" y "no medí lo suficiente para saberlo", y acá estamos en la segunda.

## 4. Una hipótesis mía que el control refutó

Al ver el censo reporté que el `detector` se había encarecido de ~190 a ~585 ms. Controlando por
pantalla —quedándome sólo con las vueltas que coinciden con un despacho de S9— el cuadro cambia:

| período | en S9 | en otras pantallas |
|---|---|---|
| antes de la caché del header | **499** | 192 |
| con la caché | **520** | 655 |
| después del revert | **585** | 580 |

En S9 el detector **siempre costó ~500-585 ms**. Los "190 ms" nunca fueron S9. Estaba comparando
mezclas de pantallas distintas y leyendo esa mezcla como una regresión. (De paso, esto confirma por
otro camino lo que el propio PERF ya anotaba: la caché del header **no ahorró nada**, 499 → 509.)

Lo mismo vale para dos métricas que parecían desplomarse entre la pasada y el censo:
`dispatch:S9` 128 → 2222 ms y `ocr_bboxes` 17 → 601 ms. No es que el sistema se frenara: en una
pasada de 10 discos **la mayoría de los despachos no tienen disco nuevo que leer** y son baratos,
así que arrastran la mediana. Sólo las métricas **por disco emitido** (`frescura_*`) son comparables
entre pasadas con distinta densidad de trabajo.

## 5. La regla que faltaba

El instrumento estaba bien. Lo que faltaba era **qué se le puede pedir a una muestra**:

1. **Un p50 de n=10 no es un baseline.** Cualquier comparación de latencia reporta **n** junto al
   número, y si se va a declarar una mejora, su **intervalo**. Dos intervalos solapados no son una
   mejora, por más que las medianas difieran.
2. **Comparar sólo métricas por ítem** (`frescura_disco_click_a_log`) entre corridas de distinta
   densidad. Las agregadas por vuelta (`dispatch:*`, `ocr_*`, `detector`, `loop_period`) dependen de
   cuántas vueltas fueron trabajo real.
3. **Controlar la pantalla** antes de comparar el detector o el loop: su costo no es una constante
   del sistema, es una constante *por pantalla*.

## 6. Qué queda en pie del PERF de la Fase 2

Lo que **no** depende de esas medianas sigue siendo válido, y es la mayor parte:

- Los defectos encontrados y arreglados: "Salir" no guardaba las métricas, los libres esperaban un
  warmup que no les tocaba, el despacho leía frames animados.
- La **caché del header revertida** por acertar 0/72 en vivo — decisión tomada con un conteo, no con
  una mediana.
- Que el **OCR del panel** es el tramo grande que queda (la Fase 2C).
- La Pasada A desmintiendo el diagnóstico previo ("el primer despacho no emite"), que salió de mirar
  una serie bimodal.

Lo que cae es **el titular**: no hay evidencia de que la espera haya bajado, y tampoco de que el
censo la haya empeorado.

## 7. Qué hacer con la Fase 2C

Antes de tocar el OCR del panel hay que poder **saber si sirvió**. Con ~100 muestras por condición
—unos 10 minutos de pasada, que el censo mostró que es perfectamente viable— el intervalo de la
mediana se angosta a ±100-200 ms, y ahí sí una mejora de 500 ms se ve. Medir antes y después con esa
cantidad, y reportar el intervalo, es más barato que discutir si el cambio sirvió.

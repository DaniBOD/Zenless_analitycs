# Las librerías de badges y tres trampas de medición — 2026-08-11/12

> **Qué pasó:** salimos a subir el naming del dueño en el inventario de W-Engines y terminamos
> descubriendo que **la métrica con la que veníamos evaluando las librerías de avatares mentía, de
> tres formas distintas**. Este doc guarda el diagnóstico, porque los números que creíamos buenos
> se citan en varios docs anteriores.
>
> **Punto de partida:** QA de S30 en vivo, `presencia 7/7 · nombre 3/7`.
> **Diagnóstico de entonces:** "faltan referencias, 8 PJs tienen una sola".
> **Diagnóstico real:** las tres cosas de abajo, ninguna de las cuales era esa.

---

## Trampa 1 · El leave-one-out se INFLA con clones

Contar referencias no era medir cobertura. Medido con umbral de clon 0.03:

| superficie | refs | **distintas** | PJs con UNA sola imagen |
|---|---|---|---|
| `row` | 365 | **62 (17%)** | **40 de 50** |
| `grid` | 486 | 356 (73%) | 6 de 56 |
| `detail` | 193 | **85 (44%)** | 22 de 50 |

Alice, Jane, Miyabi, Nangong Yu, Zhao, Zhu Yuan y 16 más mostraban **cuatro refs que eran la misma
imagen repetida**. Pyrois tenía siete idénticas.

**Causa:** la cosecha del flujo de discos llama a `learn` una vez por cada disco del PJ, pero el
avatar del panel de detalle —y el de la barra superior— **no cambia con el disco seleccionado**.
Seis discos, seis copias. El `grid` se salvaba porque su tile sí cambia.

**Por qué el leave-one-out no lo veía:** saca una ref y la busca contra el resto, pero **si su
gemela idéntica sigue adentro, matchea a 0.000 y cuenta como acierto perfecto**. Medía "¿quedó una
copia mía?" en vez de discriminación. Sobre `detail`: **91.2% con clones contra 42.4% dedupeada**.

Y el 42.4% coincidía con el campo (el QA de S30 dio 5/11 = 45%). El número de laboratorio era el
que mentía.

**Agravante:** `add_reference` desaloja FIFO al llegar a 10, así que una clase llena de clones
**expulsa las refs diversas** para meter más copias.

---

## Trampa 2 · El leave-one-out se DEPRIME con clases de una sola ref

Al ver `row` en 35.5% lo reporté como "la superficie más floja del sistema". **Era otro artefacto,
en la dirección contraria.**

Con 40 de 50 PJs teniendo una sola imagen, el leave-one-out le saca a la clase su **única**
referencia: queda vacía y no hay respuesta correcta posible. Separando por tamaño de clase:

| superficie | clases con 1 ref | clases con ≥2 refs |
|---|---|---|
| `row` | 0/40 *(imposible por construcción)* | **22/22 = 100%** |
| `detail` | 0/22 | 36/63 = 57.1% |
| `grid` | 0/6 | 280/350 = 80.0% |

**El `row` no tenía un problema de discriminación: acertaba 22 de 22 cuando tenía con qué
comparar.** Su problema es de fragilidad — 40 PJs dependen de una sola imagen, sin red si ese
recorte sale mal. El 6.5% de wrong que reporté salía también de las clases de una ref: al sacarla,
el match cae en otro PJ. En producción esa referencia está.

> **Regla:** el leave-one-out solo significa algo sobre clases con ≥2 refs distintas. Sobre las de
> una, mide una pregunta sin respuesta.

---

## Trampa 3 · `is_gray` no separaba lo que decía separar

Con las dos trampas anteriores corregidas quedaba un problema real: `detail` acertaba 57% **aun
teniendo refs disponibles**, contra 80% del `grid`.

Primeras dos hipótesis, **las dos descartadas por datos**:

- *¿Encuadre?* No: `detail` tiene la **mejor** separación entre PJs de las tres (inter-clase 0.330).
  Lo que estaba mal era la dispersión INTRA-clase: 0.190 contra 0.052 de las otras dos.
- *¿Contaminación (una cara ajena con el nombre equivocado)?* No: cero clases mezclaban gris y
  color, y el patrón no era de refs sueltas envenenadas.

Lo que apareció: **35 de 85 refs marcadas `is_gray=True`**, incluidas todas las de Seth, Rina,
Velina, Corin y Pan Yinhu — PJs obtenidos, con discos equipados, avatar a color.

`is_gray` manda el match a compararse **solo por luminancia, descartando el color**. Se decidía con
`saturación < 45`, umbral que el propio código declaraba desde 2026-06-10 *"sin muestras grises
reales aún: tentativo, a calibrar"*. Nunca se calibró.

**No hay bimodalidad.** Es una sola distribución continua cortada al medio:

| superficie | marcados gris (sat) | a color (sat) |
|---|---|---|
| `detail` | 11.8 – **45.0** | **44.8** – 129.8 |
| `grid` | 12.9 – 46.8 | 42.6 – 135.7 |
| `row` | 15.3 – 48.3 | 47.6 – 117.0 |

Lo que el flag separa **no es obtenido/no obtenido: son PALETAS**. El arte de Seth tiene saturación
7.3, Anby 10.6, Lycaon 16.6, Corin 24.7, Velina 26.2 — personajes de negro. A esos les tiraba lo
único que los distingue entre sí, y por eso **Seth caía a 0.084 de Zhao**, los dos de oscuro.

El diagnóstico cierra solo: en `detail`, las refs con el flag **apagado** aciertan **39/39** en
1-NN; las que lo tienen **encendido**, **16/24**. Los 8 fallos estaban todos del mismo lado.

### Por qué RELATIVA y no "siempre color"

"Siempre color" daba el mejor número puro (detail 98%, grid 95%) — y **habría roto una capacidad
probada**: hay un test que verifica que una Ellen desaturada matchea su ref a color justamente por
la ruta de luminancia. Lo encontré **después** de proponer sacar la ruta entera.

Y un umbral absoluto mejor no existe: un personaje de negro (7.3) y un avatar realmente grisado
(10-20) **se solapan**. Ningún número los separa.

Pero *grisado* no es tener poca saturación: es tener **mucha menos que la referencia contra la que
te comparás**. Eso sí se mide.

```python
descriptor_distance(q, ref, gray_only=None)   # None = "decidí vos"
# -> gray_only = sat(q) < _GRAY_SAT_RATIO * sat(ref)
```

`True`/`False` siguen siendo decisión explícita del que llama.

**`k = 0.25` está calibrado, no elegido:** entre refs legítimas del MISMO PJ la razón nunca baja de
0.75 (`detail`) ni 0.98 (`row`); una Ellen desaturada al 12% da 0.14. Queda aire para un grisado
más suave sin rozar la variación normal.

**Una tercera vía que parecía buena y era peor:** tomar el mínimo de ambas métricas. Medida, baja
el grid de 95% a 89% — infla el parecido y crea falsos. Descartada por datos.

---

## Estado de las librerías al cierre

Tras limpiar 541 copias (**cero clases perdidas**) y con la métrica relativa:

| superficie | refs | leave-one-out (guard 0.80) | wrong |
|---|---|---|---|
| `grid` | 356 | **90.7%** | 1.4% |
| `detail` | 85 | **52.9%** | 3.5% → **1.2%** |
| `row` | 62 | 35.5% *(ver trampa 2)* | 6.5% → **3.2%** |

Los aciertos suben ~10 puntos donde hay con qué comparar, y **el wrong —el fallo que importa— cae a
menos de la mitad en las tres**.

Baselines versionados nuevos: `audit/avatar_*_snapshot_20260811_dedup.npz` (31,8 MB contra 65,5 MB
de los viejos). Los anteriores **no se reescribieron**: quedan como historia.

---

## Qué cambió (commits)

| commit | qué |
|---|---|
| `5af4667` | spec de la cosecha del detalle desde S26 |
| `7256ab7` | el flujo de armas alimenta la librería que consume |
| `54120f2` | el veto de cosecha mira el match crudo, no el consenso |
| `4afecc3` | falso LIBRE de S30 + dedup por contenido + ruido del diag |
| `ff9be32` | spec del dedup en la cosecha de discos |
| `2ec8f5e` | la cosecha deja de clonar + limpieza de las refs repetidas |
| `f18ace7` | la ruta gris se decide relativa |

---

## Lecciones de método

1. **Contar referencias no es medir cobertura.** El indicador de salud es **refs distintas**. Un
   contador que dice 4 y son la misma imagen es peor que uno que dice 1: nadie va a mirar.
2. **Un número agregado esconde dos poblaciones.** Tanto el 91% (inflado por clones) como el 35%
   (deprimido por clases de una ref) desaparecen al separar por tamaño de clase.
3. **Reportar y aprender piden evidencia distinta, y en direcciones opuestas.** Para nombrar hace
   falta mucha; para negarse a aprender, muy poca. Reusar el umbral de reporte como veto dejó
   cosechar la cara de Billy bajo el nombre de Lycaon.
4. **Preguntar antes de terminar de investigar sale caro.** Ofrecí "siempre color" sin saber que
   rompía un test que ya existía. El orden es investigar y después ofrecer.
5. **Medir la tercera vía en vez de imaginarla.** La que se me ocurrió era peor que las dos que ya
   tenía, y solo se supo midiéndola.
6. **Dos corridas con el número idéntico descartan la concurrencia.** 592 fallos exactos las dos
   veces = determinismo, no contaminación por editar en paralelo (que también hice, y era
   irrelevante). El culpable real: `from tools.X import ...` en un test le tapa a PaddleOCR su
   propio paquete `tools`.

---

## Pendiente

- **Cosechar imágenes distintas** de los PJs que aparecen en el inventario de armas. El naming del
  dueño sube cuando la cobertura profunda alcance a esos dueños, no antes.
- **El `row` es frágil**, no roto: 40 de 50 PJs con una sola imagen. Una cosecha dedicada de S18 le
  daría margen. Es la superficie que identifica al PJ en S8/S18/S19 (el latch), aunque el diseño lo
  tiene contenido: el menú S15 lo siembra por OCR, el matcher se abstiene bajo guard y el monitor
  sostiene al último conocido.
- **`is_gray` quedó como dato informativo** en el descriptor. Si nunca vuelve a usarse, se saca.
- Los tiles de la grilla de S30 (el censo de las 57 armas en una pasada) siguen sin empezar.

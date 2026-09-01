# El censo como instrumento: cinco hallazgos, y tres con la misma forma

> **2026-08-30/31.** Pasada completa del censo de discos — 383 capturados en dos horas. Salieron
> cinco bugs que **ninguna suite había visto**, y tres de ellos son el mismo error estructural con
> tres disfraces.
>
> Cierre operativo en [`audit/censo_discos_cierre_20260830.md`](../../audit/censo_discos_cierre_20260830.md).

---

## La forma que se repite

**Un umbral ABSOLUTO donde la señal que discrimina es el MARGEN.**

Aparece en el guard de identidad, en el resolvedor de nombres de set, y —con otro disfraz— en el
nivel 0. En los tres casos el sistema tenía la respuesta y un número la tiraba.

---

## 1. El guard de identidad no era uno, eran dos

`_S17_GUARD_DEFAULT = 0.80` se aplicaba a las dos superficies de badge. **No miden en la misma
escala**: sobre los fixtures donde ambas aciertan, la confianza del detalle corre **-0.042** por
debajo de la de la grilla. Era el número de la grilla usado sobre una escala ajena.

Lo destapó un disco de Soukaku, cinco frames seguidos:

```
GRILLA   top=[Ben:0.90, Soukaku:0.90]                 margen 0.00, se dan vuelta
DETALLE  top=[Soukaku:0.79, Jane:0.44, Lucía:0.44]    margen 0.346
```

El detalle da el nombre correcto, con Ben **fuera de su top-3** y un margen 8,6× el mínimo — y se
descartaba por tener la confianza **una centésima** debajo del guard.

### El número salió de un barrido, no de una corazonada

Leave-one-out sobre la librería del detalle: 73 consultas, 32 clases con ≥2 refs distintas tras
dedup exacto (el leave-one-out miente con clones).

| guard | acierta | MAL | se abstiene |
|---|---|---|---|
| 0.80 | 45 | 1 | 27 |
| **0.70** | **56** | **1** | 16 |
| 0.45 | 56 | 1 | 16 |

11 rescates, **cero errores nuevos**, y las 11 son aciertos — incluidos Soukaku ×2 y Manato, los
dos casos reportados en vivo. Que por debajo de 0.70 no cambie nada dice que **no es un filo**: a
las 16 restantes las frena el margen, no la confianza.

El único error de la librería (Seth→Zhao) viene con conf **0.916**: ningún guard lo detiene. Es un
problema de datos de esa clase.

**Convergencia que da confianza:** el laboratorio mide Soukaku en 0.739/0.268 y el campo en
0.79/0.346. Dos fuentes independientes, mismo veredicto.

## 2. El resolvedor de sets: el mismo error, otra tabla

De 433 detecciones, 415 persistieron. Las 18 restantes vienen de **dos** lecturas:

| lectura | veces | candidato | ratio | margen al 2º |
|---|---|---|---|---|
| `Melodia Faett` | 15 | Melodía de Faetón | 0.8148 | **0.3603** |
| `Metalcolmilluda (i)` | 3 | Metal Colmilludo | 0.8485 | **0.2771** |

Las dos por debajo del cutoff absoluto de **0.86**, y las dos **inequívocas**. Simulado sobre las
60 lecturas del censo, una regla de margen aceptaría las 18 y ninguna lectura tiene dos candidatos
cerca.

No se perdió ningún disco: el agregador reintenta hasta que sale una lectura buena. El costo fue
**tiempo** — hasta 4 intentos y ~45 s para un disco.

⚠️ **Antes de tocar ese cutoff:** la familia `Blues libre Precdom` resuelve con ratio **0.7407**,
muy por debajo del umbral. O sea que hay **otra vía** (el matcher de logos, 90 refs de 30 sets).
Medir el resolvedor de texto sin saber eso lleva a la conclusión equivocada.

## 3. El nivel 0 es un nivel

```python
f"Nivel {disc.nivel}/15" if disc.nivel else "Nivel ?"
```

`0` es falsy. Una tanda entera de discos recién dropeados salía como **"Nivel ?"** — que en ese log
significa *no lo pude leer*— cuando el dato estaba perfectamente leído. La línea de al lado
(`main_valor`) ya usaba `is not None`: era una inconsistencia dentro de la misma función.

**Deuda anotada, no arreglada:** `parser_disc_s17` tiene el mismo patrón en el merge del agregador
(`if new.nivel: b.nivel = new.nivel`), y ahí importa más porque afecta lo que se **persiste**: si un
frame malinterpreta el nivel como distinto de cero, una lectura correcta de 0 nunca lo corrige. No
se tocó porque el parser usa 0 como valor **y** como centinela de "no lo leí", así que separarlos
pide cambiar el tipo y eso ramifica hasta la DB.

## 4. El desempate por build se realimenta a sí mismo

Este no es un umbral: es una fuente de verdad que no lo era todavía.

El desempate promueve al top-2 sobre el top-1 cuando el empate visual es ínfimo **y** la DB
corrobora exclusivamente al segundo. Corroboró a Antón sobre Harumasa porque Antón tenía 4 piezas
del set y Harumasa 1.

**Pero ese dato lo lee de la tabla que el censo está construyendo.** Harumasa tenía 1 pieza porque
todavía no se había llegado a las otras, no porque no las tuviera. Y cada error hace más probable
el siguiente: el primero establece la firma que justifica al segundo.

### La DB sola delata el resultado

Un PJ **no puede** tener dos discos en el mismo slot. Al cerrar el censo había exactamente dos
casos, los dos en Antón (slots 1 y 5) — y Harumasa, el PJ más incompleto, es justo al que le
faltaban los slots 1 y 5. Sus dos duplicados son del set del que Harumasa ya tiene dos piezas.

Es un invariante que la app podría chequear sola.

## 5. El arreglo de la fuga trajo su propia fuga

`stop()` cerraba el syncer y la conexión a la DB, pero no el OCR. Cuando el OCR pasó a otro proceso,
`self._ocr` dejó de ser un objeto que el GC se lleva; y `_init_dependencies` corre en **cada**
`start()`, así que cada stop→start abandonaba un worker vivo con su GB.

Medido: dos workers a la vez (1040 y 1359 MB) tras un ciclo de pausa, y **26 procesos** de python
al cerrar la app después de varios.

**Lo destapó contar procesos al cerrar.** Ninguna métrica del proceso principal lo mostraba —
justamente porque ya no vive ahí.

---

## Lo que me llevo

**Un umbral absoluto es una apuesta a que todas las escalas son la misma.** El 0.80 del guard valía
para la grilla; el 0.86 del resolvedor valía para los nombres que se habían visto hasta entonces.
Los dos fallan igual: cuando lo que separa al acierto del error es la **distancia al segundo**, un
piso sobre el primero mide otra cosa. Y el síntoma es engañoso, porque el sistema no falla ruidoso:
**se abstiene**, que parece prudencia.

**Mover un problema puede sacarlo del alcance de su propia red.** El watchdog de RNF-06 sigue ahí y
sigue andando, y dejó de cubrir la memoria del OCR en el mismo commit que la arregló — no porque se
rompiera, sino porque mide el proceso equivocado. Un control que deja de aplicar es peor que uno que
falla: no avisa.

**Y una instrumentación bien puesta vale más que una hipótesis buena.** El rescate por detalle
fallaba en silencio por cuatro caminos distintos. Agregar una línea que dijera *por qué* —y después
otra que dijera *a quién habría nombrado*— convirtió cada abstención en un dato etiquetado, y de ahí
salió el barrido que fijó el número. Antes de eso yo tenía una hipótesis razonable y equivocada en
su parte principal: creía que el bloqueo era la confianza, y en la grilla es el margen.

---

**Commits:** `35eaab4` (re-arme del gemelo) · `c037a82` (LIBRE en el log) · `8505e25` (diagnóstico
del rescate) · `aef92a0` (worker huérfano) · `71191e0` (guard por superficie) · `cff60ae`
(nivel 0) · `e469c04` (cierre del censo).

**Pendientes:** confirmar en pantalla los slots 1 y 5 de Harumasa · revisar los 7 PJs a 5/6 ·
desactivar la promoción del top-2 con censo abierto · regla de margen en el resolvedor de sets ·
el centinela del nivel en el merge del agregador.

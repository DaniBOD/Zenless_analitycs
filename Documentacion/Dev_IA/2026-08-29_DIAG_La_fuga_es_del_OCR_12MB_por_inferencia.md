# La fuga de RAM es del OCR: 12,46 MB por inferencia — y el objeto efímero no alcanza

> **2026-08-29.** El censo de discos se interrumpía solo: el watchdog de RNF-06 reiniciaba la app
> entera al cruzar los 6 GB, **dos veces por pasada**. Este doc aísla de dónde salen esos GB y
> descarta, midiendo, la solución que parecía obvia.
>
> Continúa [`audit/mem_diag_20260613.md`](../../audit/mem_diag_20260613.md), que cerró la fuga de
> junio (28 GB → 155 MB, causa: `load_merge` retenía arrays completas vía view de numpy).

---

## 1. La trampa de medición, primero

Esto va antes que los resultados porque casi me lleva a la conclusión equivocada.

La primera prueba fue: parsear **3 frames fijos** 30 veces y mirar la memoria.

```
tras warmup     workingset  656 MB   commit 1189 MB
+10 parseos     workingset  752 MB   commit 1465 MB
+20 parseos     workingset  752 MB   commit 1465 MB      <- plano
+30 parseos     workingset  752 MB   commit 1465 MB      <- plano
```

**Plano.** Con ese resultado la conclusión habría sido "el OCR no fuga, buscá en otro lado" — y es
falsa. Con contenido repetido el pipeline no vuelve a llamar a Paddle: lo que se midió fueron
aciertos de caché, no inferencias.

La fuga sólo aparece **variando el contenido**, como en el censo real. Es la regla A1 con una
vuelta de tuerca: no alcanza con medir, hay que medir *el caso*.

## 2. Aislamiento por componente

Todo sobre fixtures reales de `09_Inventario_discos_general`, con `gc.collect()` entre muestras.

| componente | iteraciones | commit | ¿fuga? |
|---|---|---|---|
| captura de pantalla (`mss`) | 90 | +12 MB, después plano | no |
| `detector.classify` | 600 ticks | +3 MB | no |
| recortes de badge | 30 | +1 MB | no |
| match de badges (grid + detalle) | 30 | +0 MB | no |
| **parseo con OCR, contenido variado** | 150 | **+4401 MB** | **sí** |

Los 600 ticks de captura+`classify` son la prueba más fuerte del lado limpio: es exactamente el
trabajo por tick del monitor, sostenido, y no se mueve.

### El bug de junio no volvió

Se verificó explícitamente, porque era el sospechoso natural. El recorte del badge **sí** es una
view del frame completo (`crop.base is not None`), así que si el descriptor guardara cualquier cosa
derivada de él, cada referencia retendría los 11 MB del frame entero. No lo hace:

```
frame completo   (1439, 2559, 3)   11,0 MB
crop del badge   (60, 60, 3)        0,011 MB   view=SÍ
descriptor       gray/hist/ncc/regions, todos view=no
memoria retenida por UN descriptor: 0,066 MB
```

Con el tope de 10 refs por PJ y 56 clases, la librería en RAM son ~37 MB. No es la fuga.

## 3. El número

```
60 parseos  ->  141 inferencias de OCR

commit      +1756 MB   ->   12,46 MB por inferencia
workingset   +791 MB   ->    5,61 MB por inferencia
```

Lineal, sin plateau, en las cinco muestras. Proyectado al censo completo (401 discos ≈ 940
inferencias): **~11,7 GB**. El watchdog corta a los 6 GB, que es exactamente por qué se reinicia
dos veces por pasada.

Las mitigaciones de junio siguen puestas en [`ocr_paddle.py`](../../app/core/ocr_paddle.py)
—`FLAGS_eager_delete_tensor_gb=0.0` y `FLAGS_allocator_strategy=auto_growth`— y aun así queda esto.

## 4. La solución que parecía obvia, y la medición que la descarta

La idea era hacer el motor de OCR **efímero**: soltarlo cada tanto y crear uno nuevo, para que el
arena nativo se libere.

```
base                      commit 2058 MB
tras 40 parseos           commit 3322 MB   (+1264)
al SOLTAR el motor        commit 2563 MB   ( -759)   <- vuelve el 60 %; el 40 % queda tomado
con el motor NUEVO        commit 3214 MB   (+1156 vs base)

ahorro real: 108 MB de 1264  (~9 %)     costo: 2,2 s por reciclado
```

Dos razones por las que no sirve, y hacen falta las dos para verlo:

1. **Soltar el objeto no devuelve todo.** El 40 % queda retenido por el proceso — el allocator
   nativo no le devuelve las páginas al sistema.
2. **El motor nuevo cuesta casi lo mismo que se liberó.** 651 MB para volver a cargar los modelos.

O sea: 2,2 segundos de pausa para recuperar el 9 %. Lo único que devuelve el 100 % es **terminar el
proceso** — que es, exactamente, lo que el watchdog ya hace.

## 5. Dónde queda

La intuición de hacerlo efímero era correcta; lo que cambia es **el nivel**: tiene que ser efímero
el *proceso*, no el objeto. De ahí sale el trabajo siguiente — mover el OCR a un worker propio,
reciclable, con el reemplazo pre-calentado para que el cambio no se note.

Hay un detalle que ese trabajo no puede pasar por alto: **hay dos instancias de Paddle vivas en el
proceso**, no una. La del controller y la global `_s26_verify_ocr` del detector
([`detector.py:1640`](../../app/core/detector.py)), que corre sobre *toda* pantalla que matchee el
template de S17 — o sea, muchas más inferencias que el parser. Mudar sólo la primera dejaría la
fuga casi intacta.

---

## Lo que me llevo

**Una prueba que da "plano" puede estar midiendo otra cosa.** Los 3 frames fijos no midieron el
OCR: midieron el caché. El resultado era limpio, reproducible y falso. Cuando una medición dice
"acá no hay nada", vale preguntarse si el experimento ejerce de verdad el camino que se quiere
medir — y el criterio es si se parece al caso real, no si es cómodo de montar.

**Y la asimetría entre soltar y recrear.** Un reciclado se evalúa por el neto, no por lo que
libera. Los -759 MB solos parecían un éxito; los +651 MB del reemplazo son la mitad de la ecuación
que convierte el arreglo en un gasto de 2,2 segundos.

---

**Mediciones:** todas con `app.core.mem_diag.mem_counters()` (workingset y commit del proceso),
`gc.collect()` entre muestras, sobre los 19 fixtures de
`Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general/`.

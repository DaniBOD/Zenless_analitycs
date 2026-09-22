# Fase 2E: el OCR cambia de motor, no de modelo

**2026-09-21 · PERF** · sigue a la
[Fase 2D](2026-09-20_PERF_Fase_2D_el_titulo_de_prepo_y_el_panel_que_no_afloja.md), que dejó la
espera en 2531 ms con el panel adentro valiendo 1898 — el **75 %**.

## 1. La premisa ya estaba medida

La 2D probó cuatro formas de bajar el panel por código y las cuatro fallaron (MKL-DNN −4 %, menos
hilos −5 %, filtrar cajas **peor**, el envoltorio 3 %). Y encontró por qué: el mismo recorte cuesta
**526-800 ms en el banco y 1784 en vivo**, y la diferencia no era el socket, ni el proceso aparte,
ni la fuga, sino **la CPU que deja el juego**. Con los 6 núcleos ocupados, 3300 ms.

De ahí la fase: si el cuello es cuánta CPU consigue, hay que gastar menos CPU por inferencia. Eso
no se toca desde Python — se toca cambiando el motor.

## 2. Lo que se midió antes de escribir una línea de integración

Las dos ramas corren **el mismo PaddleOCR**: mismo pre-proceso (resize/normalize del DBNet), mismo
post-proceso (unclip de cajas, decodificación CTC) y **los mismos pesos**. Lo único distinto es
quién multiplica. Ramas **intercaladas** con el orden sorteado en cada vuelta, 19 capturas del
corpus de S9, IC bootstrap de la mediana:

| máquina | paddle inference | onnxruntime | |
|---|---|---|---|
| quieta | 881 ms [808-913] | 781 ms [746-807] | −11 % · sin solape |
| **con los 6 núcleos llenos** | **2767 ms** [2676-2980] | **1669 ms** [1627-1742] | **−40 % · sin solape** |

**La ventaja crece justo en la condición real.** Paddle pide 10 hilos sobre 6 núcleos y se degrada
feo cuando no los consigue; ORT reparte mejor. Es coherente con las otras dos cosas que ya sabíamos
del mismo cuello: bajarle los hilos a Paddle lo empeora, y subirle la prioridad al proceso no lo
mejora.

**Y no cambia lo que lee.** Sobre el corpus entero, comparando lo que sale del PARSER —que es el
dato que termina en la DB: set, slot, nivel, main con unidad, rareza, tier y los 4 substats con sus
rolls—: **0 diferencias en 19 capturas**. No "texto parecido": el registro completo.

## 3. El entorno, que era el riesgo de verdad

`pip install onnxruntime` a secas quiere subir **protobuf de 3.20.2 a 7.36**, y paddlepaddle 2.6.2
depende de protobuf. Este proyecto ya perdió un día reconstruyendo el entorno por una subida así,
así que:

- la prueba se hizo en un **venv desechable**, con paddle, paddleocr y ORT de las mismas versiones;
- recién cuando dio, se instaló en el de la app con **`--no-deps`** y se verificó que paddle sigue
  levantando y que protobuf **sigue en 3.20.2**;
- `pip check` se queja de que onnxruntime *declara* `protobuf>=4.25.8`. Corre igual —lo que
  necesita viaja en la DLL nativa— y está verificado inferencia por inferencia. Queda dicho acá en
  vez de escondido: es una desviación conocida, no un descuido.

La conversión de los modelos vive en `tools/export_ocr_onnx.py`, con las instrucciones del venv
desechable y la verificación obligatoria.

## 4. Un arreglo de deuda que vino de arriba

Con `use_onnx=True`, PaddleOCR **no descarga nada**: los `maybe_download` de los tres modelos están
del otro lado de un `if not params.use_onnx`. Así que los pesos dejan de vivir en `~/.paddleocr`
—fuera de la app, bajados en el primer arranque, distintos entre máquinas— y pasan a viajar en
`app/resources/ocr/`. Es exactamente lo que pide **D1**, y no estaba buscado.

## 5. Cómo se vuelve atrás

`DANIBOD_OCR_ENGINE=paddle` devuelve el motor de siempre sin tocar código ni reempaquetar. Y si
faltara un modelo o no se pudiera importar `onnxruntime`, el backend **cae solo al motor viejo y lo
escribe en el log con el motivo** (`no están los modelos …`, `onnxruntime no se pudo importar …`).
Un 40 % de latencia extra no se nota mirando la app: si nadie lo dice, se descubre midiendo tres
semanas después. Eso es **D2**.

El `.exe` también se lleva ORT: `collect_all("onnxruntime")` en `main.spec`. Sin eso el motor nuevo
andaría en desarrollo y moriría empaquetado — la forma que este repo ya tiene anotada en memoria.

## 6. Sabotajes

5 de 5 en rojo, hash del diff igual antes y después: que el motor se elija pero el kwarg no llegue,
que el interruptor de vuelta atrás deje de mirarse, que no se chequee que los modelos estén, que la
caída al motor lento no avise, y que los modelos se busquen fuera de `app/`.

## 7. Verificado en vivo (2026-09-22, 107 discos)

Pasada acotada del **primer al último disco** (10:42:01 → 10:49:09), contra la pasada de la 2D
acotada igual (22:44:51 → 22:51:03, 99 discos). El motor efectivo se leyó del arranque de
PaddleOCR (`use_onnx=True`, modelos de `app/resources/ocr/`), no se asumió.

| | 2D (20/09) | 2E (22/09) | |
|---|---|---|---|
| **click → log** | 2539 ms [2484-2594] | **1203** [1172-1234] | **−53 % · sin solape** |
| panel (`ocr_bboxes`) | 1721 [1659-1820] | **587** [543-603] | **−66 % · sin solape** |
| disco → log | 1969 | 657 | −67 % |
| *`capturer`* (control) | *42* | *43* | *+2 %* |
| *`detector`* (control) | *203* | *198* | *−2 %* |

Predije 1800 y dieron **1203**: le erré, y para el lado contrario que en la 2D. El banco con seis
quemadores daba −40 % y en vivo dio −66 %. Que el juego compita peor que seis bucles ocupados es
una hipótesis razonable, no algo que esta pasada mida. Lo que sí cierra es el mecanismo: el panel
baja 1134 ms y se llama ~2 veces por disco (199/98 el 20, 211/107 el 22).

### El control que declaré estaba mal elegido

Había declarado de antemano el **período del loop**, con el argumento de que el detector no usa OCR
desde la 2C. Bajó 375 → 360 ms — poco, pero bajó. Y su p90 se desplomó **2266 → 828**, que es la
delación: **el loop se bloquea mientras se parsea**, así que su período está causalmente conectado
al tratamiento y nunca pudo haber sido un control. Declararlo antes de mirar era necesario y no
alcanzaba.

Los controles buenos de esta pasada resultaron `capturer` y `detector`, y **`capturer` se movió para
arriba** (+2 %): no hubo una máquina más rápida el 22. Regla nueva: **C1.d**.

### La ventana importa tanto como el número

La primera lectura tomó para la 2D la ventana *arranque del monitor → detenido* (22:39-23:00) en
vez de primer↔último disco. Eso metía **14 minutos de navegación**: 2296 muestras de `loop_period`
contra 899 de una pasada equivalente, y `ocr_bboxes` en 568 ms con IC **[178-1622]** — bimodal
porque mezclaba pantallas. Acotada bien, la misma serie da 1721 [1659-1820]. Es **C1.b** otra vez:
una mezcla de pantallas se disfraza de medición.

## 8. La fuga de memoria era de paddle, no del OCR

El reciclado del worker (`TECHO_RECICLADO_MB = 2500`) está dimensionado sobre **12,46 MB por
inferencia**, medidos el 2026-08-29 **con paddle inference**. Es un número heredado, así que se
volvió a medir (**A1**): 90 inferencias, **un proceso por motor** —si comparten proceso, el que fuga
primero infla la base del otro—, descartando las 20 primeras, con la pendiente por mínimos
cuadrados sobre el régimen y midiendo *commit*, no working set (el working set lo recorta el
sistema y taparía la fuga).

| | pendiente | proyección a 380 inferencias |
|---|---|---|
| paddle inference | **+15,8 MB/inferencia** | 7948 MB |
| onnxruntime | **+0,016 MB/inferencia** | 1108 MB |

**Mil veces menos**, y la pasada en vivo lo confirma sin laboratorio: **0 relevos del worker en 107
discos**, y terminó en 592 MB. El 20/09 cruzaba el techo en cada sesión.

Dos consecuencias, ninguna urgente, las dos anotadas:

- el reciclado pasa a ser **una red que ya no se dispara nunca**, y una red que no se ejerce no está
  testeada (**D2**);
- el proceso aparte **existe por la fuga** — así lo dice su propio docstring. Sigue dando
  aislamiento y no se toca, pero su justificación original dejó de aplicar y el módulo debería
  decirlo en vez de seguir afirmando algo que ya no es cierto (**B1**: una sola autoridad, y hoy
  esa autoridad miente).

## 9. Lo que la pasada rompió

Daniel reportó tres discos que "no se captaron". El log los separa en dos cosas distintas:

- **10:42:34, Hado emplumado slot 2**: sí se logueó, 3 s después. No fue una pérdida: le ganó de
  mano al sistema.
- **10:44:22 (Seth) y 10:46:05 → 10:47:39 (Floración del alba)**: el log se queda **mudo** 40 s y
  94 s. En el segundo, al volver leyó el **slot 2**, no el slot 1 que estaba seleccionado.

Contando huecos entre discos consecutivos:

| | 20/09 (99 discos) | 22/09 (107 discos) |
|---|---|---|
| intervalo entre discos | 4,0 s (p90 5) | **2,0 s** (p90 3) |
| huecos ≥ 8 s | **0** | **5** (máx 94 s) |

O sea: la mitad de tiempo por disco, y cinco trabes donde antes no había ninguna. Es el **trabe
mudo de S17** ya abierto desde el 2026-07-23, pero la **frecuencia es nueva** y aparece justo cuando
el loop gira 2,2× más seguido. No hay con qué atribuirlo: la pasada corrió sin `-LogDebug` y
durante esos 94 s el log **no dice nada**. Contra el silencio no se depura — antes que teorizar,
hace falta que el despacho grite cuando lleva demasiado sin resolver.

## 10. Lo que falta

- **El aviso de la caída al motor viejo no llega a ningún lado.** El `WARNING` del §5 se emite
  dentro del **worker**, que a propósito no escribe en `app.log` (dos procesos rotando el mismo
  archivo lo truncan). El worker ya devuelve los errores como dato para que los escriba el padre;
  el motivo del motor tiene que viajar por ahí. Tal como está, la red de D2 avisa donde nadie mira.
- **El trabe mudo**, con la instrumentación del §9.
- El `.exe` **no** se reconstruyó (`main.spec` quedó listo para cuando toque).
- Los otros dos call-sites del OCR del panel siguen sin tocar, pero ahora todos corren sobre ORT.

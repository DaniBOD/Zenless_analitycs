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

## 7. Lo que falta

- **Verificarlo en vivo.** Esperado: el panel de ~1898 a ~1150 y la espera de 2531 a ~1800. El
  control declarado de antemano es el **período del loop**, que no debería moverse: el detector no
  usa OCR desde la Fase 2C, así que si también baja, lo que cambió fue la máquina.
- El `.exe` **no** se reconstruyó (`main.spec` quedó listo para cuando toque).
- Los otros dos call-sites del OCR del panel siguen sin tocar, pero ahora todos corren sobre ORT.

# Prácticas aprendidas — las que se pagaron caro

> **Leer antes de trabajar.** No son principios generales de ingeniería: cada una salió de un
> error concreto de este proyecto, y varias aparecieron **más de una vez disfrazadas de problemas
> distintos**. Están acá porque las lecciones estaban dispersas en 62 docs de `Dev_IA/` y nadie
> las lee todas.
>
> Última actualización: **2026-09-20**.

---

## A · Evidencia

### A1 · Medir antes de afirmar. Un número heredado no es una medición.

Se citaba *"`classify` cuesta ~109 ms"* desde el instrumental de QA-06. **Nunca se midió**: los
109 ms eran el **período del loop**, y alguien lo leyó como si fuera el costo. Medido de verdad:
**3.500 ms**, 32 veces más. Ese número mal leído además contaminó la cota de frescura publicada
en otro doc.

En una sola sesión de censo se afirmaron tres cosas antes de medirlas y **las tres eran falsas**
(que el sleep era el 83 % del ciclo — era 0 %; que la GPU era la palanca — el cuello era el
detector; que había 8 refs contaminadas — eran legítimas y sacarlas empeoró todo).

**Cómo aplicarlo:** antes de optimizar algo, medilo *hoy*, con la máquina quieta. Si el número
viene de un doc, andá a ver si alguien lo midió o si lo dedujo. Y cuando corrijas un número
heredado, fijate si tu propio cambio ya lo movió otra vez.

**Y medí con la métrica que usa el sistema, no con una parecida** (2026-09-12). Para saber si una
referencia de avatar estaba mal etiquetada se comparó con una distancia L2 sobre la imagen en
gris: dio lejos, y la hipótesis correcta se descartó. Con `descriptor_distance` —la que el matcher
realmente usa— esa misma ref era la más cercana (0.156 contra 0.475) y era la causa del bug. Una
medición con la métrica equivocada no es media medición: es una refutación falsa, y cuesta más que
no haber medido, porque cierra la puerta con aire de rigor.

**Un test que pasa prueba el mecanismo, no la premisa** (2026-09-17). Se cacheó el OCR del header
del inventario por los BYTES del recorte, porque "el título no cambia mientras se recorren discos".
El test con `classify` y Tesseract reales pasó: comparaba el frame contra `a.copy()`, que es idéntico
byte a byte **por construcción**. En vivo: **0 aciertos de 72**. Que dos frames REALES consecutivos
traigan el header con los mismos bytes nunca se midió; se revirtió. Antes de construir sobre una
premisa del mundo (qué hace el juego, qué trae la pantalla), medila en vivo — el laboratorio no la
puede contradecir si el propio test la fabrica.

### A2 · El silencio no es un aprobado.

*"No hay ERROR en el log"* no significa que anduvo: puede significar que **ese código nunca
corrió**. El catálogo de nodos se carga solo cuando el juego está abierto; con el juego cerrado,
un bug puesto y un bug arreglado se ven **idénticos**.

**Cómo aplicarlo:** si el éxito de un QA es que no pase nada, decilo explícito y **dejá una señal
verificable**. Y separá siempre "no falló" de "no se ejecutó".

**Vale también para la suite** (2026-09-13): *skipped* no es *passed*. Los tests de widgets de los
toasts se **salteaban en silencio** en toda suite completa porque otro archivo había creado antes una
app de Qt sin GUI, y la suite se reportaba verde. El mismo choque hacía que tests nuevos **mataran el
proceso** al 90 %, sin resumen: sueltos pasaban, sólo fallaban en combinación. Un "N skipped" que no
se sabe explicar es un hallazgo pendiente, no un detalle. Y un proceso de pytest que muere **sin
resumen** no es un rojo: es un crash que hay que aislar (widget por widget, con `faulthandler`). Esa
misma tarde volvió con otra causa: una excepción dentro de un `paintEvent` que PySide convierte en
*access violation*.

### A3 · Verificar el EFECTO, no la intención — y romper el test a propósito.

Un `except` que loguea convierte un crash en silencio: había un test que miraba el reporte
(un subproducto) y pasaba mientras la escritura a la DB **no ocurría**.

Otro test se llamaba `test_usa_la_MISMA_identidad_que_el_dedup` y verificaba que se llamara a la
misma *función*, sobre datos sintéticos. No podía ver que las dos capas discreparan bajo OCR real
— y discrepaban.

**Cómo aplicarlo:** testeá la fila que cambió, no el reporte que lo cuenta. Y **rompé el test a
propósito** antes de darlo por bueno: si no falla, no tiene dientes.

### A4 · Verificar el estado, no deducirlo.

Los folders de `Screenshots_Triggers/` **no nombran el estado del detector**: hubo un feature
planificado entero sobre el supuesto de que una pantalla era S6/S7 cuando era S17.

Una carpeta de worktree sin `.git` propio devuelve el estado del **repo principal** si la
consultás con git: parecía "limpia y al día" y estaba vacía.

**Cómo aplicarlo:** clasificá el fixture antes de planificar sobre él. Consultá el estado real,
no el que sugiere el nombre.

---

### A5 · Un recorte de la evidencia es otra evidencia. `grep -c` antes de concluir.

Investigando si el desempate de dueño había escrito mal durante el censo, se corrió
`grep "desempate" app.log | tail -20`. Las 20 líneas eran todas abstenciones, y de ahí salió la
conclusión *"el desempate nunca disparó, así que el arreglo planeado no sirve"*. `grep -c` sobre
el mismo archivo: **54 desempates exitosos**, 11 de ellos dando vuelta al top-1 durante la pasada.
El pendiente estuvo a punto de descartarse por las últimas 20 líneas de 7107.

Es el mismo error que [C1](#c1--medí-contra-un-baseline-validado-antes-y-después-no-inventes-una-métrica-nueva)
pero en la lectura, no en la métrica: `head`, `tail` y un `LIMIT` son **muestras**, y una muestra
no ordenada por relevancia no dice nada sobre el resto. La trampa es que el recorte se siente como
"el resultado" porque lo devolvió el comando que uno escribió.

**Cómo aplicarlo:** cuando la conclusión sea *"esto nunca pasó"* o *"esto pasa siempre"*, la
evidencia tiene que ser un **conteo sobre el total** (`grep -c`, `COUNT(*)`, un agrupado), no un
recorte. Si igual mirás un recorte, decí en voz alta de cuántos es. Y desconfiá especialmente
cuando el recorte confirma que **no hay que hacer trabajo**: es la dirección en la que uno no
insiste.

**Dos casos del 2026-09-12**, en la misma dirección: *"nadie usa `AgentDiscRepo`"* salió de un grep
inundado por `app/build/` (el bundle de PyInstaller), con el `head` cortando justo la línea del
optimizador — se lo borró y hubo que restaurarlo. Y *"el optimizador corre al equipar"* salió de un
grep que encontró la llamada, **sin seguir quién llama a esa función**: nadie la llamaba. Buscar en el
repo se hace excluyendo `app/build/`, y "X se ejecuta" se afirma recorriendo la cadena de llamadas
hasta un punto de entrada, no desde la primera coincidencia.


## B · Autoridad de los datos

### B1 · Una sola autoridad por pregunta. Dos definiciones de lo mismo son una de más.

Apareció **dos veces en la misma semana**:

- El censo contaba 10 discos donde la DB tenía 8. La persistencia comparaba el `set_id`
  **resuelto**; el censo, el **string** del nombre — y el OCR lee `Firmamento Ilameante` /
  `llameante` inconsistente entre pasadas.
- `preseed_badge_lib.py` tenía su **propia lista** de cuál era el baseline y reinstalaba el
  snapshot de **junio**, mientras la app reponía el de agosto. Nadie lo había notado.

**Cómo aplicarlo:** cuando dos capas necesitan la misma respuesta, una **defiere** a la otra. No
alcanza con llamar a la misma función: hay que consumir el **mismo resultado**.

### B2 · Ausencia de evidencia no es evidencia de ausencia (RNF-02).

Abstenerse es correcto. Lo que **no** es correcto es que abstenerse cueste el dato entero: un
disco cuyo dueño no se podía nombrar se descartaba completo — se perdían set, slot, nivel y los
cuatro substats, que sí se habían leído bien (8 % de los discos).

Y al revés: **no borres por ausencia**. Un audit podó 4 referencias de un PJ porque su clave
estaba mojibakeada, no porque sobraran.

**Cómo aplicarlo:** separá *"no lo tiene nadie"* de *"no sé de quién es"* — son estados distintos
y mezclarlos infla cuentas que después se usan para validar. Ante la duda: NULL, abstención, y
**renombrar antes que borrar**.

**Y una red de seguridad sin salida es una fuga.** Guardar el disco marcado como *"alguien lo
tiene y no sé quién"* evitó perder el dato, pero **nada podía reclamar esa fila después**: la
consulta que busca a qué disco pertenece una captura excluía a propósito toda fila sin dueño. Cada
vez que se reiniciaba la captura y el disco sí se nombraba, se insertaba una fila nueva. El rescate
se volvió una fábrica de duplicados — 3 de 5 marcados eran fantasmas.

Cuando agregues un estado *provisional*, la pregunta que casi siempre falta es **quién lo saca de
ahí**, y que al salir se **borre la marca**: una marca que sobrevive a su propia condición envenena
el contador que dice cuánto falta (decía 5 cuando eran 4, y no iba a bajar nunca).

**Lo bueno del estado explícito:** una marca es una AFIRMACIÓN, así que se puede **refutar**.
*"Alguien lo tiene en el slot 6"* se contradice sola si los 51 PJs ya tienen su slot 6 ocupado —
y eso resolvió los cinco casos sin mirar ninguno de los discos. Una fila `libre` no da ese
apoyo: dice *"no lo tiene nadie"*, y que otro PJ tenga uno idéntico no la contradice.

### B3 · Un audit no muta su objeto de estudio.

`AgentIdentifier()` a secas **poda y persiste** al construirse. Dos herramientas de diagnóstico
modificaron la librería del usuario **con solo mirarla**; una borró 4 refs.

**Cómo aplicarlo:** `prune=False` explícito en toda tool. Y "READ-ONLY" en el docstring no es
evidencia: **testeá el sha256 antes y después**. Los tests que tocan la DB de dominio se aíslan
por defecto (`autouse`), no por disciplina.

---

## C · Cuando la métrica miente

### C1 · Medí contra un baseline validado, antes y después. No inventes una métrica nueva.

La métrica de la librería de caras mintió **de cuatro formas distintas**:

| forma | efecto |
|---|---|
| clones inflando el leave-one-out | 91,2 % de laboratorio vs **42,4 %** real |
| clases de una sola ref | deprimían un matcher que acierta 22/22 |
| `is_gray` separando paletas, no obtenidos | un PJ de negro se comparaba **sin color** |
| distancia al centroide en clase **bimodal** | el centroide cae en el medio ⇒ todo parece lejano |
| **mediana** de `dispatch:S9`, que es **bimodal** (2026-09-16) | cayó en el modo barato ⇒ "el primer despacho no emite", falso |

La cuarta la inventó el asistente y llevó a "descubrir" 8 refs contaminadas que eran legítimas.
Sacarlas bajó el acierto de 93,3 % a 91,5 %.

La quinta es **la misma forma un mes después**. `dispatch:S9` mezcla despachos que no leen nada
(11-148 ms, el disco ya salió) con lecturas reales (1,8-3,0 s). Con 43 muestras la mediana dio
135 ms, se tomó como "lo que cuesta leer un disco", y de ahí salió un diagnóstico entero que la
pasada siguiente desmintió (los contadores dijeron `agg 1c · 0 desc`: la primera lectura
alcanzaba). **Antes de resumir una serie con un número, mirá si tiene dos poblaciones**: ordenala
entera, o separá por lo que la genera. Un resumen de una mezcla no describe a ninguna de las dos.

**Cómo aplicarlo:** usá `measure_badge_lib.py --against-labeled`, que está validado, y corré
**antes y después** de cualquier cambio. Una métrica nueva se valida contra la vieja antes de
decidir con ella. Contar referencias **no** es medir cobertura.

#### C1.b · Un p50 de n=10 no es un baseline (2026-09-20)

La Fase 2 declaró que la espera en S9 bajó **3109 → 2562 ms (−18 %)**. Los dos números son **el
quinto valor de diez muestras**. Con n par no hay un medio: hay dos, y en la Pasada B difieren un
22 % (2561 y 3139), así que **la convención del percentil —no el sistema— elegía el titular**. El
bootstrap de las medianas da intervalos que se solapan casi por completo (A: 2641-3703 · B:
2188-3305): **no hubo evidencia de mejora en ningún momento**. Peor: sobre ese 2562 se reportó
después una "regresión de 830 ms" del censo (n=383), que resultó **indistinguible de la Pasada A**,
o sea del estado previo. Una medición frágil no sólo no prueba la mejora: **fabrica la regresión
siguiente**.

En la misma revisión, dos comparaciones más que no querían decir lo que parecían:
- **El detector "se encareció" de 190 a 585 ms.** Falso: controlando por pantalla, en S9 **siempre**
  costó ~500-585 ms. Los 190 eran otras pantallas. Se comparó una *mezcla de pantallas* con otra.
- **`dispatch:S9` 128 → 2222 ms y `ocr_bboxes` 17 → 601 ms.** Tampoco: en una pasada de 10 discos la
  mayoría de las vueltas no tienen disco que leer y son baratas. Son métricas **por vuelta**, y sólo
  se pueden comparar entre corridas con la misma densidad de trabajo.

**Cómo aplicarlo:** al comparar latencias, (1) reportá **n** junto al número, y el **intervalo** si
vas a declarar una mejora — dos intervalos solapados no son una mejora; (2) compará sólo métricas
**por ítem** (`frescura_*`) entre corridas de distinta densidad, nunca las agregadas por vuelta;
(3) **controlá la pantalla**: el costo del detector y del loop no es una constante del sistema, es
una constante por pantalla. Con ~100 muestras por condición (≈10 min de pasada) el intervalo baja a
±100-200 ms y una mejora de 500 ms se ve. Detalle:
[2026-09-20_QA_El_menos_18_por_ciento_no_existia.md](documentacion_cruda/2026-09/2026-09-20_QA_El_menos_18_por_ciento_no_existia.md).

#### C1.c · Una prueba en la máquina quieta no refuta nada sobre la máquina llena (2026-09-20)

El OCR del panel cuesta **526-800 ms en el banco y 1784 en vivo**, y ninguna explicación del lado
del código sobrevivió a la medición (el socket son 1,34 ms; el proceso aparte, 598 contra 587; la
fuga acumulada, +1 % en 60 llamadas). La diferencia era **el juego corriendo al lado**: con los 6
núcleos ocupados, el mismo recorte pasa a **3300 ms**.

Antes de eso había probado prioridad del proceso, `CREATE_NO_WINDOW` y el throttling de Windows 11,
y anoté "ninguna mueve nada" — **con la máquina vacía, donde no había con quién competir**. Repetida
con carga, la prioridad sí parece mover ~20 %. La conclusión anterior no era falsa: era **vacía**, y
encima venía con la forma de un descarte prolijo.

En la misma tanda, dos hipótesis mías más refutadas por su propia medición: filtrar las cajas
inútiles antes de reconocerlas es **más lento** (Paddle ordena por relación de aspecto y agrupa de a
6: la basura es corta y ya salía casi gratis), y **bajarle los hilos a Paddle con la máquina llena
la empeora** (6102 contra 3300) — pedir menos hilos no te deja pasar antes, te deja menos chances de
agarrar un núcleo libre.

**Y el A/B necesita alternar el orden.** Medí "175 ms de envoltorio de PaddleOCR" corriendo siempre
la llamada entera primero y el pipeline a mano después: la segunda rama heredaba los hilos ya
calientes. Alternando, son 18 ms. Un orden fijo entre dos ramas es una condición que se le suma
**entera** a una sola — la misma forma que C1.b, en la escala de la llamada.

**Cómo aplicarlo:** (1) la condición de la prueba es parte de la hipótesis — si el fenómeno es "en
vivo", la prueba necesita la carga de en vivo, y si no la tiene, el resultado se anota como *no
probado*, nunca como *descartado*; (2) en cualquier A/B intercalá el orden; (3) cuando una
optimización dependa de cómo agrupa el motor por dentro, mirá cómo agrupa antes de estimar el
ahorro. Detalle:
[2026-09-20_PERF_Fase_2D_el_titulo_de_prepo_y_el_panel_que_no_afloja.md](documentacion_cruda/2026-09/2026-09-20_PERF_Fase_2D_el_titulo_de_prepo_y_el_panel_que_no_afloja.md).

### C2 · Un reloj declara una unidad, no una granularidad. Y un sello de tiempo no es un ID.

Apareció **dos veces**, disfrazada de cosas distintas:

| caso | lo que declaraba | lo que hacía |
|---|---|---|
| bench de desmontaje | `thread_time` con `resolution=1e-07` | avanzaba de a **15,625 ms** (tick del scheduler) |
| nombres en `audit/` y backups | `%f` — seis dígitos de microsegundos | avanzaba de a **un tick del timer global** |

En Windows la granularidad del reloj de pared **no es una propiedad de la app**: es global y
mutable (15,625 ms por defecto; baja a ~1 ms sólo mientras otro proceso la sube con
`timeBeginPeriod`). Un test que pasa hoy puede estar pasando por lo que el usuario tiene abierto.

El caso de `audit/` llegó como flake (~1 de cada 30) y era **pérdida de datos**: dos bitácoras de
desmontaje con el mismo nombre y `os.replace` pisando en silencio. Medido con el timer en 1,0 ms:
**14 %** de colisión entre dos escrituras seguidas; con el timer por defecto, casi 100 %. Y en los
respaldos RNF-01 el sello era al **segundo**, o sea un millón de veces más grosero — lo que
sobrevivía no era "un backup menos" sino un archivo que **dice** ser el estado previo y ya trae la
escritura adentro.

**Cómo aplicarlo:** el sello es para que un humano ubique la corrida, **nunca** para garantizar
unicidad. Pedir el nombre a `app.core.unique_paths`, que reserva con `O_CREAT | O_EXCL` — crear
*sólo si no existe* en un paso indivisible; `if existe:` seguido de escribir son **dos** pasos y
entre medio cabe otro escritor. Para medir tiempo, `perf_counter` + mínimo de lotes cortos, o
contar llamadas. Y antes de correr un test flaky en bucle, **sacale el azar** (congelar el reloj):
40 corridas verdes de un test probabilístico no distinguen "arreglado" de "tuve suerte".

Ver `2026-08-19_FIX_Unicidad_de_nombres_en_audit.md` y `2026-08-20_FIX_Unicidad_del_backup_RNF-01.md`.

---

### C3 · Un instrumento roto se ve igual que un dato malo. Y el que mide no elige el reloj.

`frescura_estado_a_log` abría el cronómetro con `time.monotonic()` y lo cerraba con `time.time()`.
La resta de dos relojes **no da un número malo: da el epoch entero** — ~1,789e12 ms. Quedaron **14
muestras así durante un mes** en la tabla que se consulta justamente para decidir qué optimizar.

⭐ **Lo que lo volvió invisible no fue la resta, fue que el síntoma se disfraza de dato.** En una
métrica de latencia, un número absurdamente grande **parece un hallazgo** ("uh, estuvo lento"), no
un defecto. No hay nada en un reporte de percentiles que grite. Es el caso peor de [A2](#a2--el-silencio-no-es-un-aprobado): el pase no
es el silencio, es una salida que se lee como resultado.

La otra mitad de la lección es de autoridad ([B1](#b1--una-sola-autoridad-por-pregunta-dos-definiciones-de-lo-mismo-son-una-de-más)): el bug fue posible porque **cada llamador
elegía su reloj**. Un `# ojo: usar monotonic` al lado no lo evita; lo evita que la resta no esté ahí.

**Cómo aplicarlo:**

- El módulo que registra es el dueño del reloj: abrir con `metrics.ahora()` y cerrar con
  `metrics.registrar_desde(superficie, t0)`. Ningún sitio de medición vuelve a llamar a un reloj.
- **Poner una cota de plausibilidad y que avise.** Ninguna superficie con presupuesto de 20-500 ms
  puede tardar una hora: por encima de eso no es lentitud, es el cronómetro mal cerrado. Descartar
  la muestra y loguear una vez por superficie — un agujero ruidoso es mejor que un percentil
  envenenado, y convierte un bug invisible en uno que se anuncia.
- **Testear el rango, no sólo que se registre.** Un test que cuenta muestras pasa con el epoch
  adentro; el que afirma "cae por debajo de 60 000 ms" se pone rojo. Y como la instrumentación vive
  en el pipeline, el test tiene que manejar el **handler real** — si sólo llama al helper, pasa
  igual cuando nadie lo invoca desde producción ([A2](#a2--el-silencio-no-es-un-aprobado) otra vez).
- Corolario: **una métrica sin un test que la mire puede existir y no medir nada.** Antes de creerle
  a una serie histórica, mirá una muestra cruda.

**Reapareció a los dos días, con otra forma: una métrica que PARECE completa** (2026-09-17).
`ocr_text` medía **sólo** `OcrProxy.text`. `text_with_bboxes` —el OCR principal del panel de S9,
S17, S26, S3, S10, desmontaje— no dejaba rastro, y cuesta **8,2×** una lectura de texto (735 contra
89 ms offline; ~1,6 s en vivo). Durante meses `ocr_text` reportó la parte chica del OCR, y la grande
aparecía como "tiempo sin explicar": ~1,5 s por disco, ~2,5 s por arma. Un nombre genérico
(`ocr_text`) sobre una medición parcial se lee como "el OCR cuesta esto". La guarda no es acordarse
de decorar: es un test que deriva los métodos del contrato (`OcrBackend`) y exige que el proxy los
tenga TODOS medidos (`test_ocr_medido.py`), así un método nuevo sin medir cae con su nombre.

Ver `2026-09-15_FIX_El_reloj_de_la_frescura_media_el_epoch_y_la_espera_la_pone_el_warmup.md` y
`2026-09-17_PERF_Latencia_del_log_en_S9_lo_que_midieron_las_pasadas_A_y_B.md`.

---

## D · Entorno y empaquetado

### D1 · Todo lo que la app lee vive DENTRO de `app/`.

`Path(__file__).parents[2] / "audit"` da la raíz del repo en desarrollo y **`_internal/audit/`**
congelado — carpeta que el bundle nunca copió. El `.exe` no "asume que el repo está al lado":
**no llega al repo por ninguna vía**.

**Cómo aplicarlo:** la regla es `Path(__file__).parent.parent / "resources" / …`, la misma que
`detector.TEMPLATES_DIR`. Cualquier `parents[N]` que se escape del paquete es un bug latente que
**solo se ve empaquetado**. Verificalo midiendo: el `.exe` escribe la ruta resuelta en el
traceback, y `find` sobre el bundle prueba el otro extremo.

### D2 · Una red de emergencia que en dev nunca se ejerce, nunca se testea.

El auto-restore de la librería de caras llevaba meses muerto en el `.exe`. Había un test
—`test_los_baselines_versionados_existen`— que pasaba: los archivos estaban, solo que no donde el
`.exe` mira.

Y el modo de falla **no es el ruidoso**. Cuando esa librería se perdió, el sistema no se quedó sin
dueños: **nombró mal con confianza** (4,3 % de acierto, 14 discos ajenos a un PJ).

**Cómo aplicarlo:** testeá la **ubicación relativa al paquete**, no la existencia. Y cuando
evalúes el riesgo de un componente, preguntá cómo falla, no solo si falla: *degradar callado* es
peor que *romper fuerte*.

### D3 · Si una restricción del entorno se puede medir, que el script la mida.

Una build murió con un `FileNotFoundError` que nombraba un archivo que estaba ahí: el problema era
el **largo de la ruta** (límite de 260 chars de Windows). La conclusión quedó como nota mental
—"buildeá desde el repo principal"—, que es la clase de nota que falla el día que nadie se acuerda.

**Cómo aplicarlo:** una nota en un doc no es un mecanismo. Si el script puede medir la restricción
y adaptarse, que lo haga, y que **avise cuando el margen se achica** — no solo cuando ya falló.

---

## E · Cómo se trabaja

### E1 · Una investigación que no deja archivo no se puede revisar ni retomar.

Un worktree cerró una investigación con *"no toqué el repo, git status limpio"* — presentado como
virtud. Significaba que el análisis existía **solo en el contexto de ese agente**: no se podía
revisar ni continuar si esa sesión se perdía.

**Cómo aplicarlo:** todo hallazgo que decida trabajo futuro va a `Dev_IA/` **antes** de
implementarlo. Un diagnóstico es un entregable, no un paso previo.

### E2 · Si el usuario tiene un método que funciona, no lo reemplaces por uno abierto.

Daniel avanzaba al disco siguiente **cuando saltaba el log** — un lazo de realimentación que por
construcción no pierde discos (7 de 7). Se le pidió que contara **5 segundos fijos** y eso rompió
el lazo: **perdió 5 de 15**. Un intervalo ciego no puede saber cuándo maduró cada disco, que es
justo lo que varía.

**Cómo aplicarlo:** antes de "mejorar" un procedimiento manual, entendé qué señal está usando la
persona. Un lazo cerrado le gana a un intervalo abierto casi siempre.

### E3 · Un cambio por vez, y el diagnóstico primero.

El refactor del detector y el caché del OCR iban a ir juntos "de paso". Si el QA negativo se movía,
no se iba a poder saber cuál de los dos lo movió. Fueron en tres entregas separadas —diagnóstico,
refactor, caché— y el diagnóstico **cambió el plan** de los otros dos: mató las dos hipótesis con
las que se había salido.

**Cómo aplicarlo:** el diagnóstico primero y escrito; después un cambio, con su verificación
propia. "Ya que estoy" es cómo se pierde la capacidad de atribuir una regresión.

---

## Cómo mantener este doc

Se agrega una práctica cuando un error **se repite** o cuando costó caro entenderlo. Cada entrada
lleva el incidente concreto: sin el caso, la regla se lee como una obviedad y se ignora. Si una
práctica deja de aplicar, se borra — un doc de reglas muertas enseña a ignorar el doc entero.

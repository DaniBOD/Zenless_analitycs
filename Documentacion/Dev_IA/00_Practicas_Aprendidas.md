# Prácticas aprendidas — las que se pagaron caro

> **Leer antes de trabajar.** No son principios generales de ingeniería: cada una salió de un
> error concreto de este proyecto, y varias aparecieron **más de una vez disfrazadas de problemas
> distintos**. Están acá porque las lecciones estaban dispersas en 62 docs de `Dev_IA/` y nadie
> las lee todas.
>
> Última actualización: **2026-08-19**.

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

### A2 · El silencio no es un aprobado.

*"No hay ERROR en el log"* no significa que anduvo: puede significar que **ese código nunca
corrió**. El catálogo de nodos se carga solo cuando el juego está abierto; con el juego cerrado,
un bug puesto y un bug arreglado se ven **idénticos**.

**Cómo aplicarlo:** si el éxito de un QA es que no pase nada, decilo explícito y **dejá una señal
verificable**. Y separá siempre "no falló" de "no se ejecutó".

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

La cuarta la inventó el asistente y llevó a "descubrir" 8 refs contaminadas que eran legítimas.
Sacarlas bajó el acierto de 93,3 % a 91,5 %.

**Cómo aplicarlo:** usá `measure_badge_lib.py --against-labeled`, que está validado, y corré
**antes y después** de cualquier cambio. Una métrica nueva se valida contra la vieja antes de
decidir con ella. Contar referencias **no** es medir cobertura.

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

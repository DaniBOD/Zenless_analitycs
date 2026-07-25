# IMPL — Bitácora de desmontaje: seguimiento de S11 + commit por S24

**Fecha:** 2026-07-25 · **Branch:** `feature/desmontaje-bitacora` · **Modo:** display-only (escribe
un archivo en `audit/`, **nunca** la DB) · **RF:** RF-04 §4/§9.

El desmontaje era el **único flujo del juego donde los discos dejan de existir** y el sistema no
lo registraba. La pantalla ya se detectaba (`S11`) pero solo para *no capturar* — así lo declaraba
el RF: *"Ignorar — NO capturar aunque haya NEW!"*. Cerrarla también cierra la **cobertura de
extracción**, que es el prerequisito declarado para retomar el trabajo de latencia/GPU.

**Alcance acordado con el usuario:** solo la bitácora de lo destruido. Sin calibración de scoring,
sin censo de inventario, sin desmontaje inteligente (siempre criterio humano).

---

## 0. La anatomía del problema

Un click en un tile hace **dos cosas a la vez**: muestra el disco en el panel DETAIL **y** alterna
su tilde. Un segundo click sobre el mismo lo desmarca. De ahí salen tres señales con autoridades
distintas, y confundirlas es todo el riesgo del feature:

| Señal | Fuente | Costo | Autoridad |
|---|---|---|---|
| **Cuántos** se van a destruir | contador `N/300` del header (OCR) | ~50 ms, gateado | **Única** autoridad del conteo. Global: sobrevive al scroll. |
| **Cuál** acaba de cambiar | tildes por celda (máscara HSV) | < 3 ms | Solo para **aparear**. Nunca cuenta: solo ve el viewport. |
| **Qué es** ese disco | panel DETAIL (OCR) | ~700-900 ms | Los stats. Si falla, se declara hueco. |

`Ejemplo_3` es la prueba de por qué el conteo NO puede salir del censo: declara **7** y solo hay
**1** tilde visible; los otros 6 quedaron scrolleados fuera de pantalla.

---

## 1. La regla de atribución: por prueba, no por reloj

El problema real es la carrera — el OCR del panel tarda ~800 ms y el usuario clickea cada 1-2 s.

> Se atribuye el disco del DETAIL a la celda `C` **solo si** el censo de tildes del frame que se
> OCReó es idéntico al del frame donde apareció el tilde en `C`.

Como el censo y el parseo salen del **mismo frame**, un delta de exactamente una celda *confirmado
por el contador* prueba que ese fue el único click de la ventana ⇒ el panel está mostrando ese
disco. Todo delta mayor o mezclado declara el hueco sin atribuir nada.

Consecuencia buscada: que el OCR sea lento solo puede costar **discos sin datos** (aceptable — el
conteo igual sale del contador), nunca **apareos cruzados** (inaceptable, RNF-02).

### Por qué cada evento exige confirmación del contador

Es lo que neutraliza el scroll sin necesidad de razonar sobre él:

| Situación | Tildes | Contador | Decisión |
|---|---|---|---|
| click real | +1 celda | +1 | atribuir |
| el scroll TRAE un tilde al viewport | +1 celda | **igual** | no atribuir |
| el scroll SACA un tilde del viewport | −1 celda | **igual** | **no borrar** lo ya capturado |
| destilde real | −1 celda | −1 | quitar |
| clicks más rápidos que la cadencia | ≥2 | ≥2 | hueco, sin atribuir |

---

## 2. El censo de tildes: por qué el color no alcanza

El tile **enfocado** (el que se muestra en el DETAIL) lleva un **aro de selección** que pasa por la
misma esquina donde vive el badge del tilde. Medido sobre los fixtures:

- badge del tilde: **H 24-33**, S 255, V 197-253
- aro de foco de `Ejemplo_6`: **H 28** ← indistinguible por color
- y el aro **cambia de tono entre frames**: amarillo brillante (`E3` r3c5), lima (`E4` r3c2), oliva
  (`E4` r3c5)

Peor: **`Ejemplo_6` tiene el aro brillante con el contador en `0/300` y cero tildes**. Cualquier
detector basado en "hay amarillo en la esquina" habría reportado un disco marcado que nadie marcó.

**Solución geométrica, no cromática:** fracción de amarillo en un **annulus** centrado en el badge
— el mismo idiom que `_detect_s17_slot_by_hexagon` usa para el aro dorado del hexágono. El badge es
un disco compacto con un check oscuro adentro, así que su anillo se llena; el aro de foco es un
trazo fino que apenas lo roza.

| Experimento (225 celdas = 5 capturas × 45) | tilde mínimo | no-tilde máx. | separación |
|---|---|---|---|
| disco lleno, ROI 0.013 | 0.242 | 0.229 | **1.06×** (inservible) |
| disco lleno, ROI ajustado 0.005 | 0.431 | 0.146 | 2.96× |
| **annulus [0.45, 0.85]** | **0.551** | **0.140** | **3.93×** |

Umbral 0.30, con ~1.8× de margen a cada lado. El disco lleno perdía porque el **check oscuro del
centro** se come la mitad del ROI; el annulus lo esquiva por construcción.

### El gate que faltaba (lo encontró el test de negativos)

El amarillo del badge **no es exclusivo del desmontaje**: el botón "Aceptar" del modal de re-login
(`Dispara_disco_descarte.png`) lleva un círculo lima idéntico que caía justo en la celda (3,5) y
disparaba a 0.676. No era una pantalla de desmontaje: era *"Se han actualizado los datos del juego,
vuelve a iniciar sesión"*.

Gate nuevo: un tilde solo se acepta sobre una celda que **tiene un tile de disco**, comprobado por
su franja de rareza (mismo criterio que `parser_s2.tile_boxes`). Medido: las 45 celdas de S11 dan
**≥0.657**; los negativos, **0.000**.

---

## 3. El contador: el OCR lee `3o0`, no `300`

PaddleOCR devuelve el denominador como **`3o0`** en las 5 capturas — el cero del medio sale como
`o`, de forma consistente. Un regex con `/300` literal **no habría matcheado nunca**, y el bug
habría aparecido recién en el QA en vivo.

La 2ª pasada normaliza las confusiones clásicas (`o/O→0`, `S→5`, `l/I→1`, `Z→2`, `B→8`) y el
resultado se acepta **solo si el ancla `/300` aparece después de normalizar**: sin ancla, un dígito
suelto de cualquier pantalla se leería como "hay N discos seleccionados".

---

## 4. El estado S24 y sus dos vecinos peligrosos

Medido antes de escribir una línea: los dos frames post-desmontaje caían a **S12 por
`dark_frame_filter`**. No los eclipsaba nadie — **ningún template matcheaba, tampoco el de S22**.
O sea que la idea de "usar el flujo para desambiguar los dos Obtenido" era correcta pero
innecesaria como mecanismo principal: el problema no era confundirse, era no detectar nada.

`_verify_s24`, dos condiciones independientes y sin OCR:

| Condición | S24 (objetivo) | Ejemplo_8 (diálogo) | S22 (baterías) | S23 (sustitución) |
|---|---|---|---|---|
| verde "Confirmar" **centrado** | **0.0222** | 0.0000 | 0.0000 | 0.0000 |
| franjas de rareza | **2-3** | — | **12-14** | — |

La 2ª es la que impide que los dos "Obtenido" se roben la pantalla: **cada uno falla el verify del
otro** (S22 exige ≥6 franjas).

### `Ejemplo_8` sigue cayendo a S12, a propósito

El diálogo de confirmación del propio desmontaje **matchea el template de S23 a 0.699** y solo lo
salva `_verify_s23` al no encontrar "sustituir" en el texto. Decisión: **no detectarlo**. Solo
aparece cuando la selección incluye grado S ⇒ no es una señal confiable, y darle estado propio
arriesgaría S23 sin ganancia. El commit lo da el "Obtenido". Hay test de regresión explícito.

**Corolario en el dispatch:** `S12` está exceptuado de la regla de abandono. El diálogo cae ahí, y
matar la tanda en ese punto haría que el desmontaje por ese camino **nunca** se registre.

---

## 5. Lo que no se pudo leer, y se dice

La cantidad de cada material del "Obtenido" es un oráculo **secundario** (corrobora el contador,
nunca lo reemplaza). Los nombres se leen bien; las **cantidades de un dígito las dropea el
downscale del detector de Paddle**, y el rescate por upscale tampoco las recupera (la banda es
demasiado fina y el detector se pierde).

Contrato explícito: cantidad ilegible ⇒ `None`, **jamás la de la columna vecina** — tomar la del
vecino haría afirmar una corroboración falsa.

Se decidió no seguir invirtiendo ahí, y hay una segunda razón: **la evidencia sobre qué significa
ese número es contradictoria**. La previsualización de `Ejemplo_3` muestra `7, 19, 7, 4` y el
"Obtenido" de `Ejemplo_7` muestra `1, 19, 57600, 1, 4`: el 19 y el 4 coinciden, el primero no. Es
justamente por eso que el contador es la única autoridad.

---

## 6. Identidad: por qué la firma canónica no alcanza

El bloque `identidad` del registro replica **literalmente**
`InventoryDiscRepo.row_matches_parsed_identity` — `(set_id, slot, nivel, main, {substat, rolls})` —
para que el futuro script de baja compare directo y no re-derive una definición que se desincronice.

**Pero esa firma sola no sirve acá:** en discos **Nivel 0 todos los rolls son 0**, así que colapsa
a `(set, slot, main, nombres de substat)` — y la mayoría de lo que se desmonta es Nivel 0. Por eso
el registro guarda **además los valores y unidades** de cada substat y del main.

Regla para el futuro matcher: usar `identidad ∧ valores` y, ante **≥2 candidatos, reportar
ambigüedad en vez de dar de baja** (misma regla que `find_swap_candidates_by_identity`: 1 → usar,
0 → no existe, ≥2 → no tocar).

---

## 7. Formato

```
[desmontaje] tanda abierta
[desmontaje] +1 → 1/300 · Firmamento llameante (2) Nv0 · ATK 79.0 · DEF% 4.8
[desmontaje] ⚠ selección masiva: 1 → 31/300 en un ciclo · 30 sin datos
[desmontaje] tanda cerrada · 8 desmontados (5 con datos, 3 sin) · material ×8 ✓
[desmontaje] → audit/desmontajes/20260725_001159_940796_desmontaje.json
```

Toast: **uno por tanda** (pedido explícito — 50 toasts en una limpieza serían inusables), variante
violeta `DESMONTADOS`, body con el conteo del lote y el desglose `N con datos · M sin leer`. El
hueco se **muestra**, no se esconde: si el usuario clickeó rápido o usó selección masiva, tiene que
verlo en vez de suponer que la bitácora quedó completa.

---

## 8. Desviaciones del plan

1. **No se agregó muestreo en el loop rápido (10 fps).** El plan lo tenía, pero la regla de
   atribución exige que censo y parseo salgan del MISMO frame, así que el muestreo asincrónico no
   aporta corrección — solo adelantaría la detección del cambio. Con la cadencia en 300 ms y clicks
   cada 1-2 s alcanza, y se ahorra presión de RNF-06 (frames retenidos en memoria: el historial de
   la fuga de 28 GB pesa).
2. **`tile_rarity()` público y el matcher de dígitos de slot (H8) no se hicieron.** El slot sale del
   `(N)` del título del panel, que ya está probado; el badge del tile exigiría cosechar 6 clases de
   refs propias (el IMPL de S22 demostró que no transfieren entre pantallas). Queda para si el QA
   en vivo muestra apareos erróneos.
3. **El bench del panel es una guarda de regresión, no el objetivo de 600 ms del plan.** Medido:
   ~700-900 ms en CPU, del mismo orden que el crop de S17 (~850 ms documentado). Bajar de ahí es el
   trabajo **diferido** de `2026-07-10_Futuro_Latencia_GPU_Distribucion.md`, que por su propia nota
   no se retoma hasta cerrar la cobertura de extracción — o sea, hasta después de este feature.

### Lección de método: el bench mentía dos veces, y la segunda tapaba un problema real

El bench del censo **falló dos veces en la suite completa pasando aislado**. La primera vez lo
atribuí a contención y promedié 20 corridas; la segunda tomé el mínimo de varias tandas. Seguía
fallando, porque el problema no era la estadística sino el **instrumento**: `perf_counter` mide
reloj de pared, que incluye el tiempo en que el proceso está desalojado, así que estaba midiendo el
CPU que se llevaban los otros 1100 tests.

Con `thread_time` (CPU de este hilo) apareció lo que las dos versiones anteriores tapaban: el censo
costaba **2.34 ms contra un presupuesto de 3 ms**. Un 30 % de margen es demasiado fino — de ahí que
cualquier carga lo pasara. El síntoma "test flaky" era en realidad "el código está al límite".

Y el costo no era el trabajo de píxeles (45 recortes de 46×46 px son nada) sino el **overhead de
135 llamadas** al binding de OpenCV. Vectorizado (los 45 recortes apilados → un `cvtColor`, un
`inRange`, medias por `reshape`): **2.34 → 1.56 ms**, 1.9× de margen.

> Un bench que falla según lo que más corra en la máquina no es solo molesto: **oculta la señal que
> debía dar**. Si hubiera subido el umbral —la tentación obvia— el censo se habría ido a producción
> corriendo a 10 fps con un 30 % de margen y nadie se enteraba.

El bench del **panel** sí usa reloj de pared a propósito: ahí interesa la latencia que el usuario
percibe, y el OCR de Paddle es multi-hilo (`thread_time` sub-contaría). Su umbral es una guarda de
regresión generosa, no un objetivo.

---

## 9. Archivos

**Nuevos:** `app/core/parser_desmontaje.py` (censo de tildes, contador, scroll, materiales) ·
`app/core/teardown_batch.py` (lógica pura de la tanda + writer atómico) · `app/core/audit_paths.py`
· `app/resources/templates/s24_obtenido_desmontaje.png`.

**Tocados:** `detector.py` (registro de S24 + `_verify_s24` + cadencia de S11 5000→300) ·
`parser_disc_s3.py` (`parse_disc_s11`) · `monitor.py` (2 handlers + regla de abandono + `_diag` +
continuos) · `tokens.py` / `toast.py` / `controller.py` / `main.py` (variante `desmontado`) ·
`live_panel.py` · `tools/build_templates.py` (flag `--only`).

`--only` merece nota: agregar un estado nuevo no debería reescribir los 20 templates ya calibrados
y validados.

---

## 10. Verificación

- **95 tests nuevos** en 6 archivos. El **bloqueante** es
  `test_el_aro_de_seleccion_no_es_un_tilde`: si `Ejemplo_6` devuelve algún tilde, el conteo entero
  miente y todo lo que se construya encima es falso.
- **Regresión:** los 55 de S3/S5/S7/S9 tras tocar el módulo compartido `parser_disc_s3.py`; 78 de
  las suites del detector (33 negativos de FP, thresholds, máquina de estados); los 4 fixtures de
  S22 siguen dando S22, los 7 de S23 siguen dando S23, `Ejemplo_8` sigue en S12.
- **La DB no se toca:** test de sha256 antes/después (patrón `test_reemplazo_readonly`).

### Bug que atrapó un test y no el diseño

La regla de abandono estaba en la rama `else` del dispatch, pero **los estados con handler propio
(S9, S17, S8…) nunca llegan al `else`**: salir a S9 dejaba la tanda viva y el S24 siguiente la
commiteaba como si el usuario hubiera desmontado. Se movió al principio de `_dispatch_state`.

---

## 11. Pendiente

**QA en vivo — una sola pasada** (`tools/qa_launch.ps1 -FromSource -ReadOnly`):

1. Entrar a S11 → verificar `0/300` y que el primer disco del DETAIL **no** se registra.
2. Tildar 3 discos **despacio** (~3 s) → 3 líneas con stats completos.
3. Destildar 1 → línea de `−1` y el contador bajando.
4. Tildar 2 **rápido** (~0.8 s) → provocar el hueco y ver que se declara.
5. **Scrollear** y tildar 1 fuera del viewport original → hueco `fuera_de_viewport`.
6. Desmontar → confirmar el diálogo de grado S → llegar al "Obtenido".

**Esperado:** `declarado = 5`, `capturados = 3-4`, 1-2 huecos con motivo, **un solo toast**, y la DB
con el mismo sha256 al inicio y al final.

**Medir:** latencia p50/p95 de `parse_disc_s11` y la ratio `capturados/declarado` · CPU 2 min en
S11 quieto vs clickeando (RNF-06 < 3 %) · frecuencia de tildes nuevos sin subida de contador
(calidad de `scroll_pos`) · si la cantidad del primer material iguala al conteo en tandas de 2, 3,
7 y 15 (hoy la evidencia es contradictoria).

**Ya hecho:** `RF-Logic_Captura_Discos.md` §4/§9/§5 actualizado — decía *"detectar S11 y cortar
cualquier captura"*. La regla queda documentada como **revertida**, con el razonamiento original y
por qué cambió: el veto seguía siendo correcto para el *pre-registro* (S11 no da de alta discos),
pero descartaba el dato más valioso de la pantalla — es el único flujo donde los discos dejan de
existir, y no registrarlo garantiza que la DB se desincronice con cada limpieza.

Memoria: `project_bitacora_desmontaje`.

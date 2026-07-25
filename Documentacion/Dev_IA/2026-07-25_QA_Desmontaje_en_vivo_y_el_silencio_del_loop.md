# QA en vivo del desmontaje · el silencio del loop · S25

**Fecha:** 2026-07-25 · **Rama:** `feature/desmontaje-bitacora` · **Modo:** read-only (`-FromSource -ReadOnly -NoFocusGate`)

Primera pasada en vivo de la bitácora de desmontaje (implementada el mismo día, ver
[`2026-07-25_IMPL_Bitacora_Desmontaje_S11_S24.md`](./2026-07-25_IMPL_Bitacora_Desmontaje_S11_S24.md)).
Salieron tres cosas: el feature funciona en los bloques 1-5, el flujo de commit **no se pudo
probar**, y apareció un problema de observabilidad que costó media mañana y no era del desmontaje.

---

## 1. Lo que quedó verificado en vivo

Log real, 09:28:27 → 09:31:41, sobre la cuenta de Daniel a 2560×1440:

| Bloque | Evidencia en el log | Veredicto |
|---|---|---|
| Entrar a S11 | `[desmontaje] tanda abierta` · contador `0/300` | ✅ y el disco que el juego muestra solo en el DETAIL **no** se registró |
| 3 tildes lentos | `+1 → 1/300`, `2/300`, `3/300` con set, slot, nivel, main y 4 substats | ✅ |
| Destildar | `−1 → 2/300 · destildado: Firmamentollameante` | ✅ el contador manda, como se diseñó |
| 2 tildes rápidos | `+1 → 3/300`, `+1 → 4/300` (a ~7 s, no a 0.8) | ⚠️ no se provocó el hueco; **cero apareos cruzados** |
| Scroll | `scroll detectado — las celdas dejan de identificar al disco` + `alta y baja en el mismo ciclo — no se atribuye ni se borra` | ✅ |

**Los parsers aguantan en vivo.** Medido sobre un frame real cosechado de la sesión: 3 tildes bien
ubicados, contador `5`, panel DETAIL legible. La geometría calibrada contra fixtures no necesitó
retoque al pasar a la pantalla real.

**El bloque 6 nunca ocurrió.** Daniel canceló en el diálogo de grado S. Sin "Obtenido" no hay
commit, y eso es exactamente lo diseñado — pero significa que **el commit, el toast y el JSON
siguen sin probarse en vivo**.

### Un diagnóstico que estuvo mal encaminado

Al ver `S11 → S12 (conf=0.70)` di por hecho que el "Obtenido" no se detectaba. Cosechar el frame
mostró otra cosa: era el **diálogo de grado S**, y Daniel seguía parado ahí. La lección es la de
siempre en este repo, y la volví a saltear: *el estado se verifica, no se deduce*. El frame estaba
a una llamada de distancia.

---

## 2. El "silencio del loop": una falsa alarma, y por qué igual dejó código

> **Resuelto el mismo día. No hubo defecto.** Se documenta completo porque el error de método
> costó media mañana y es reincidente.

**Lo que parecía:** entre 09:31:45 y 09:39:56 el monitor no escribió una sola línea, mientras el
cosechador —un proceso aparte— tenía frames de diálogo, grilla y S17 a confianza 1.000. `py-spy`
mostraba el hilo `zzz-monitor` ausente y el proceso con CPU en 0. Se descartaron seis causas
(gate de foco, watchdog de RAM, pausa por hotkey o botón, pérdida de ventana, y dos excepciones
reproducidas offline con los frames reales) y ninguna cerraba.

**Lo que era.** Los timestamps de los frames cosechados, que estaban en el nombre del archivo
desde el principio:

| Frame | Hora | Pantalla |
|---|---|---|
| 001 | 09:37:05 | el diálogo de grado S |
| 002 | **09:39:54** | la grilla (el usuario canceló) |
| — | **09:39:56** | `Monitor detenido.` (botón del panel) |
| 003-029 | 09:39:57 → 09:42:00 | S17 |

De 09:31:45 a 09:39:54 **la misma pantalla, sin cambiar**. El logging es edge-triggered y S12 es
un estado que no captura: no había nada que decir, y no decirlo era lo correcto. Los 27 frames de
S17 que se habían tomado como prueba de "la pantalla cambió mientras la app callaba" son todos
**posteriores al stop** — la app ya estaba apagada.

**El error de método, que es lo que hay que no repetir:** se leyó "el cosechador vio tres
pantallas" sin mirar *a qué hora vio cada una*, y se construyó un misterio encima. Es el mismo
error de la sección 1 —deducir el estado en vez de verificarlo— repetido dos horas después, con
la evidencia ya en la mano. El dato que lo cerraba estaba en el nombre del archivo.

**Queda un cabo suelto menor, sin perseguir:** entre el cancelar (09:39:54) y el stop (09:39:56)
el monitor tuvo ~2 s para loguear `S12 → S11` y no lo hizo. Dos segundos en plena secuencia de
apagado no justifican investigación; si reaparece, ahora el latido lo va a mostrar.

### Por qué el código se deja igual

Nada de esto era un defecto, pero tres cosas que se escribieron para diagnosticarlo **sí arreglan
problemas reales**, y por eso quedan:

1. **El latido** habría cerrado esto en **una línea y treinta segundos** en vez de media mañana:
   un loop vivo sobre pantalla quieta late con el estado puesto, uno muerto no late, y uno sin
   frames late con `frames_nulos` alto. Las seis hipótesis descartadas a mano se distinguen de un
   vistazo. El valor no es haber encontrado un bug: es que el próximo silencio sea legible.
2. **`_safe_dispatch` sí tapa un agujero real e independiente de esto.** El cuerpo del loop no
   tenía `try/except`: cualquier excepción de un handler mataba el hilo y dejaba la app viva y
   ciega, con el traceback yéndose a un stderr bufferizado que en el `.exe` puede no vaciarse
   nunca. Eso podía pasar hoy, ayer o mañana; que hoy no haya pasado no lo hace menos cierto — y
   de hecho es justo por ese agujero que la hipótesis no se pudo descartar sin reproducir a mano.
3. **`stop()` con origen** responde en el acto la pregunta que aquí se contestó por descarte
   (¿usuario, watcher o cierre?).

### Lo que se agregó

1. **Latido del loop** (`_heartbeat`). Late tras 60 s de silencio de la app, y cada 600 s como
   línea de base. Reporta ciclos girados, frames nulos, estado y excepciones acumuladas. Va en los
   **tres** caminos del loop, incluidos los dos que hacían `continue` sin decir nada (pausado y
   frame nulo) — que eran justamente los mudos.

   ```
   [hb] 600 ciclos · frames_nulos=0 · estado=S17 · tanda=- · excepciones=0
   ```

   Con esa línea, las seis hipótesis de la tabla se distinguen de un vistazo: un loop muerto no
   late, uno girando en vacío late con `frames_nulos` alto, y una pantalla quieta late con el
   estado puesto.

2. **Despacho protegido** (`_safe_dispatch`). El cuerpo del loop no tenía `try/except`: cualquier
   `raise` en un `_process_*` terminaba el thread y dejaba la app **viva y ciega**. Peor en el
   `.exe`, donde el traceback va a un stderr bufferizado que puede no vaciarse nunca — que es
   exactamente por qué hoy no pudimos descartar esa hipótesis del todo. Ahora se loguea una vez
   por firma de fallo (una pantalla rota se queda en pantalla y llenaría el log) y el contador lo
   sigue cantando el latido.

3. **`stop()` dice quién lo pidió.** `Monitor detenido · pedido desde: <frame>`. La duda de hoy
   —usuario, watcher o cierre de app— cambiaba por completo el diagnóstico.

---

## 3. El auto-stop en segundo plano

Daniel pidió al empezar: *"desactiva la capacidad de detener la captura en segundo plano, eso me
ha generado inconsistencias"*. Había **dos** mecanismos y en la primera pasada apagué solo uno.

| Mecanismo | Qué hace | Estado |
|---|---|---|
| Gate por foco (`monitor.py:887`) | No captura si el juego no está al frente | Ya desactivable con `DANIBOD_NO_FOCUS_GATE=1` |
| Watcher de ventana (`controller.py:270`) | Cada 3 s, `stop()` si `find_zzz_window()` da None | **Desactivado por defecto ahora** |

El segundo es el peligroso: detenerse es peor que seguir, porque `_get_frame` ya maneja la
ausencia de ventana (avisa una vez, duerme 4 s, re-busca) mientras que un `stop()` deja la app
abierta y sin capturar sin que nada se lo diga al usuario. Un solo ciclo de falso negativo
—alt-tab, cambio de resolución, un instante sin título— cortaba la sesión.

Queda como opt-in: `DANIBOD_AUTO_STOP_ON_WINDOW_LOST=1`. El **arranque** automático no se tocó:
eso agrega capacidad, no la quita.

---

## 4. S25 — el diálogo de confirmación del desmontaje

### Se revirtió una decisión de diseño, y conviene saber por qué

El plan original decía **no detectar** este diálogo, con este argumento: *solo aparece cuando la
selección incluye grado S, así que no es una señal confiable, y el commit lo da el "Obtenido"*.
**Esa parte sigue vigente: S25 no commitea nada.**

Lo que cambió lo trajo el QA: el diálogo **tapa el header**, y ahí el contador `N/300` —la única
autoridad del conteo— se vuelve ilegible. El log lo mostró tal cual
(`[S11/contador] sin resultado — no se pudo leer el contador N/300`). Atravesar ese tramo a ciegas
es justo lo que no queremos en el momento de mayor tensión del flujo.

### Lo medido

El comentario viejo decía que el diálogo *"matchea el template de S23 a 0.699"*. **Estaba mal**:
0.699 era la confianza del estado ya degradado a S12, no el score del template. El score real:

| Frame | Template S23 | Umbral |
|---|---|---|
| `Ejemplo_8` (fixture) | **0.998** | 0.85 |
| `Ejemplo_9` (en vivo, 2560×1440) | **0.996** | 0.85 |

O sea que el template de S23 —la fila genérica "Cancelar/Confirmar" de ZZZ— ya identificaba el
diálogo perfectamente. Faltaba el verify.

### Diseño: dos estados, un template

S25 **reusa** `s23_sustitucion.png` y se distingue por `_verify_s25` (OCR del texto, busca
`desmontar`), igual que S23 busca `sustituir`. Va **después** de S23 en `_STATE_TEMPLATES`: ante
scores empatados el orden decide quién se verifica primero, y ese turno le toca al estado que
escribe la DB.

**`_verify_s25` falla cerrado si no hay OCR** — al revés que `_verify_s23`. La convención del repo
(no degradar ante ausencia) asume que el estado es el único que reclama esa pantalla; acá no lo
es. Sin Tesseract no hay forma de distinguir un diálogo del otro, y de los dos el que tiene
consecuencias reales es S23: mueve un disco entre PJs y **escribe la DB**. S25 solo congela un
contador. En una máquina sin Tesseract —el caso del `.exe` distribuido— S25 no existe y S23 queda
exactamente como estaba.

### El riesgo que introdujo, y cómo lo atrapó un test

Al dejar de caer a S12, el diálogo salió de la lista blanca de la regla de abandono — y la regla
habría matado la tanda **justo antes del commit**, el peor momento posible porque los discos ya
están destruidos. Lo cazó `test_la_tanda_sobrevive_al_dialogo_de_grado_s`, escrito antes de tocar
el monitor. Es el segundo bug que atrapa esa familia de tests (el primero fue salir a S9).

### Qué aporta

- Una línea cuando el sistema queda sin contador:
  `[desmontaje] confirmación de grado S · 5 declarados · esperando el Obtenido`
- Constancia en el registro: `"confirmacion_grado_s": true` distingue un desmontaje que el usuario
  confirmó a mano sabiendo que incluía grado S.

---

## 5. Lo que sigue sin probarse

**El commit end-to-end.** Bloque 6 pendiente: confirmar el diálogo, llegar al "Obtenido" y ver el
toast violeta, el resumen y el JSON en `audit/desmontajes/`. Todo lo que está aguas abajo del
"Obtenido" está probado solo contra fixtures y stubs.

Y lo que había que **medir** en vivo y sigue abierto: la ratio `capturados/declarado` al ritmo
real de clicks, el CPU del proceso en S11 (RNF-06 < 3 %), y si la cantidad del primer material
iguala al conteo en tandas de distinto tamaño.

---

## Archivos

**Nuevos:** `app/tests/unit/test_detector_dialogo_desmontaje.py` (13) ·
`app/tests/unit/test_monitor_heartbeat.py` (8) · `app/tests/unit/test_controller_auto_stop.py` (5) ·
`tools/grab_desmontaje_frames.py` (cosechador read-only) ·
`Documentacion/Screenshots_Triggers/Discos_Triggers/12_Desmontaje/Ejemplo_9_(Confirmacion_2560).png`

**Tocados:** `detector.py` (S25: umbral, transiciones, descripción, NON_CAPTURE, verify, registry,
template, cadencia) · `monitor.py` (latido, despacho protegido, `stop()` con origen, handler S25,
lista blanca) · `teardown_batch.py` (`marcar_confirmacion` + campo en el registro) ·
`controller.py` (auto-stop off por defecto) · `test_detector_desmontaje.py` y
`test_monitor_desmontaje.py` (la decisión revertida, documentada en el propio test).

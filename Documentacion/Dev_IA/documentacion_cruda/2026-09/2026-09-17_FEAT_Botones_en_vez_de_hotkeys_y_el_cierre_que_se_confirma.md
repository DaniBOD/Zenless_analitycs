# Botones en vez de hotkeys, y un cierre de censo que se confirma con un conjunto

**2026-09-17.** Commit `481bff4`. Fase 2B del plan "latencia del log + botones + censo nuevo de
discos", entre la Fase 2 (`2026-09-17_PERF_Latencia_del_log_en_S9_lo_que_midieron_las_pasadas_A_y_B.md`)
y la Fase 3 (`nivel` 0 como centinela). Va **antes del censo** porque el censo se cierra con esto.

## Por qué

Las hotkeys no le funcionaban a Daniel en juego, y la app lo avisaba en cada arranque: ZZZ corre
como administrador y Windows (UIPI) no le entrega las teclas a un proceso sin elevar mientras el
juego tiene el foco. Decisión: **sacarlas del todo** —con ellas se va el hook global de teclado— y
poner botones en la card del sidebar que el mockup ya tenía reservada.

## Lo que el código dijo y el diseño no sabía

Tres cosas aparecieron al leer el código antes de tocarlo, y dos cambiaron el diseño aprobado:

1. **`cerrar_censo()` cierra TRES censos** (discos → armas → roster), y el de discos **se abre solo**
   al entrar a S9: está abierto en cualquier uso normal, no sólo censando. Con F8, el primer pedido
   cerraba los inventarios y **recién después** advertía por el roster. Con un diálogo eso es un
   "Cancelar" que ya cerró el censo de discos.
2. **Un censo de inventario vive en memoria y no se reabre** tras cerrarse (a propósito: volver a la
   pantalla no debe contar sobre lo ya reportado). Con F8 un cierre accidental era difícil; con un
   botón siempre visible, un clic de más a mitad de la Fase 4 corta el conteo de la pasada.
3. Código muerto que se fue de paso: la sección `[hotkeys]` de `defaults.toml` **no la leía nadie**,
   el sidebar mostraba `F11 Run` (nunca existió), el parámetro `on_toggle_panel` del `Monitor` no lo
   pasaba nadie, y la bandeja decía `Salir (Ctrl+Shift+Z)` sin que ese atajo existiera.

⇒ **Decisión de Daniel: se confirma siempre, y el primer pedido no cierra nada.**

## El diseño que quedó

| | |
|---|---|
| **Quién ejecuta** | El botón deja un pedido en una `queue.SimpleQueue`; lo ejecuta **el hilo del loop**, al tope de cada pasada — **antes** del chequeo de pausa y de pedir el frame, así funciona pausado y con el juego minimizado. No hay locks en `Monitor` ni en los censos, y F8 tenía la misma carrera desde el hilo del listener. `SimpleQueue` y no un atributo: leer y limpiar son dos pasos y un pedido que llegue en el medio se pierde. |
| **Vuelta 1** | `cerrar_censo()` responde `{"accion": "confirmar", "instantanea": …}` **sin cerrar nada**: censos abiertos con su cobertura + los pendientes del roster que quedarían huérfanos. Sin nada abierto, `{"accion": "nada"}` y no hay diálogo. |
| **Vuelta 2** | La UI re-pide con esa instantánea. Cierra **sólo si lo abierto ahora es exactamente lo confirmado**: mismos censos, mismo conjunto de pendientes. Si cambió, vuelve a preguntar. |
| **Qué NO entra en la comparación** | El progreso de los inventarios: seguir recorriendo con el diálogo abierto no cambia lo que se aceptó cerrar. |
| **Respuesta a la UI** | `on_cierre_censo` (hilo del monitor) → `MonitorController.censo_cierre_resultado` (señal) → `FlujoCierreCenso`, que es un `QObject` para que Qt encole la llamada al hilo de la UI: un diálogo sólo se abre ahí. |

⭐ **La confirmación pasó de ser una ventana de tiempo a ser un conjunto.** Antes era "F8 dos veces
en 15 s", y lo que el reloj protegía era el riesgo visto en vivo el 2026-08-17 (volver al menú abre
una corrida NUEVA; cerrarla declararía huérfanos a los 49 por los que no se volvió a pasar). Un
conjunto lo protege mejor: un diálogo abierto diez minutos no puede confirmar una pasada distinta, y
si se vio un PJ más mientras tanto, lo que se confirmó **ya no es** lo que se declararía.

F9 no lleva botón: un botón no puede mostrar la ventana en la que vive. Lo cubre la bandeja.

## Verificación

- Suite **2964 → 2987 passed**, 0 failed, 0 skipped (17:28). sha256 de la DB de dominio idéntico
  antes y después. Los 3 commits de la Fase 2 se pushearon con su propia suite verde (2964).
- **6 sabotajes, los 6 rojos**, con un script que AFIRMA `count == 1` al aplicar y restaura al final
  (la regla que salió del sabotaje que "pasó" sin aplicarse, 2026-09-16): ejecutar el cierre dentro
  de `pedir`; drenar la cola **después** del chequeo de pausa; una clave de confirmación que ignora
  los pendientes; que el primer pedido cierre los inventarios; el botón sin emitir; aceptar el
  diálogo sin re-pedir.
- Los tests del pedido corren el **`_run` verdadero** (`arnes_loop_monitor`), incluido el camino
  pausado, y uno cruza dos hilos de verdad para afirmar **quién** ejecutó el cierre.
- **Smoke de la `MainWindow` real** offscreen en readonly: el cableado de `_setup_ui` no lo toca
  ningún test (la ventana no se construye en la suite), así que se construyó a mano y se ejercitó
  botón → controller → respuesta → consola.
- `.exe` recompilado: **0 archivos de `pynput` y 0 de `hotkeys` en el bundle**, arranca y cierra
  limpio con `qa_launch.ps1 -ReadOnly`.

## Hallazgo de paso (NO es de esta fase)

Lanzar el `.exe` **sin `qa_launch.ps1`** lo deja leyendo una copia vieja de la DB: sin
`DANIBOD_DB_PATH`, `_resolve_db_path()` usa `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\db\` y esa copia
es **del 2026-08-18**. Roster y Armas tiran `no such column: descartado` y los contadores del
sidebar quedan vacíos. **El acceso directo del escritorio** (`tools/launch_readonly.vbs`) es
exactamente ese camino: setea `DANIBOD_READONLY` pero no el path de la DB. Queda anotado, sin tocar:
decidir si el launcher fija el path o si la copia se migra al arrancar es una decisión de Daniel.

## Pendiente

**Verificación en vivo de Daniel**: abrir una pasada de censo de roster parcial y probar el diálogo
(que diga a quiénes declararía huérfanos, y que Cancelar no cierre nada), y pausar/reanudar con el
juego en foco — que es justo lo que las teclas no podían hacer.

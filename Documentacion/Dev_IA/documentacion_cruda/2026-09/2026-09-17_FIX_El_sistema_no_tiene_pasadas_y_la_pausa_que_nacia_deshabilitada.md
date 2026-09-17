# El sistema no tiene pasadas, y el botón de pausa que nacía deshabilitado

**2026-09-17.** Sigue a `2026-09-17_FEAT_Botones_en_vez_de_hotkeys_y_el_cierre_que_se_confirma.md`
(`481bff4`), que **queda superado en su mitad principal**: el botón «Cerrar pasada de censo» y su
diálogo de confirmación se retiraron el mismo día, después de la primera prueba en vivo.

## 1 · La prueba en vivo: los botones "no eran botones"

Daniel lanzó la app (`-ReadOnly -FromSource`), recorrió 4 discos en S9 y tocó los dos botones. Dijo
que parecían texto de relleno. El log lo confirmó: **ninguna línea de pausa ni de pedido de cierre**.

**Causa: el orden del cableado.** En `MainWindow._setup_ui`, `set_auto_detect(True)` corre antes que
la conexión de los botones. Con ZZZ ya abierto, el watcher **arranca el monitor en el acto**, adentro
de la construcción de la ventana, y `monitor_started` salía cuando el sidebar todavía no escuchaba.
Los botones nunca se habilitaron. La barra de título sí decía CAPTURA porque se conecta antes.

⭐ **Por qué nada lo vio.** Los tests del sidebar le llaman `on_monitor_started()` a mano. El smoke
con la `MainWindow` real —hecho justamente para cubrir el cableado— corrió con
`DANIBOD_NO_AUTOSTART=1`: **la prueba fabricó el único caso que funciona**. Es la forma de A1 que
ya estaba escrita esa misma mañana ("el laboratorio no la puede contradecir si el propio test la
fabrica"), repetida horas después sobre otro código. Lo que la destapó fue el uso real: el juego
abierto antes que la app, que es el caso de todos los días.

**Arreglo:** el botón se cablea antes del auto-arranque, y el test nuevo
(`test_ventana_pausa_con_autoarranque.py`) construye la `MainWindow` **verdadera** con el
auto-arranque emitiendo `monitor_started` en el mismo punto donde ocurre de verdad. Volver el
cableado a su lugar viejo lo pone rojo.

## 2 · "Cerrar censo no tiene sentido"

La objeción de Daniel: **el sistema siempre está censando**. Cada ítem nuevo entra a la DB, nunca
empieza ni termina, siempre está operativo.

El código le dio la razón: **ninguna escritura dependía del cierre**. Lo único que producía era:

| censo | qué hacía el cierre | qué quedó |
|---|---|---|
| discos (S9) | una línea de cobertura | la misma línea, **al detener el monitor** (`resumen de la sesión`) |
| armas (S30) | reporte en `audit/censos/` con las fuera de catálogo | el mismo reporte, **al detener el monitor** |
| roster (S15, `-Censo`) | declarar huérfanos en la DB de dominio | **retirado**: el roster lo declara Daniel a mano |

El concepto de "pasada" que se abre y se declara cerrada era herencia del censo de roster por el menú
de personajes, que no tiene contador. Para discos y armas el contador `N/M` ya está en cada línea.

**Decisiones de Daniel:** sacar el cierre, retirar `-Censo`, dejar sólo la pausa.

- **Monitor:** fuera `censo`, `on_census_progress`, `_observe_census` (la observación en S15),
  `pedir_cierre_censo`, la cola, `cerrar_censo` y la instantánea. `stop()` resume los inventarios
  **sólo si el loop terminó** (si el `join` venció, el loop todavía puede estar tocando esos censos).
- **Controller:** fuera la apertura por `DANIBOD_CENSO` y la señal del cierre.
- **UI:** fuera `app/ui/shell/cierre_censo.py` y el diálogo. La card del sidebar tiene un botón.
- **`qa_launch.ps1`:** fuera `-Censo`; limpia `DANIBOD_CENSO` si quedó de una sesión vieja.
- **Quedaron sin uso** (borrados en un commit aparte, ver §3): `RosterCensus`, `write_census_report`,
  `CensusStore`, `abrir_o_reanudar` y `marcar_huerfanos_en_dominio`, con sus tests unitarios.
  `census_store.roster_y_catalogo` y los umbrales de `census.py` **sí** tenían otros usuarios
  (`roster_declaration`, `test_menu_agent_read`).

## Verificación

- Sabotajes, los 4 rojos (script con `count == 1`, restaurado y con el hash del diff igual):
  cablear la pausa después del auto-arranque; `stop()` sin resumir; resumir con el loop vivo; el
  botón sin emitir.
- La app de QA se cerró identificada por línea de comando, sin `/F`. sha256 de
  `danibod_zzz_v2.db` y de `census.db` iguales antes y después de la sesión en vivo.
- Suite: ver el commit.
- **Sin recompilar el `.exe`** (pedido de Daniel: a lo más la suite).

## Pendiente

- Verificación en vivo de la pausa con el juego abierto **antes** que la app.

## 3 · Los restos del censo de roster, borrados (commit aparte, mismo día)

Decisión de Daniel: borrarlos ya, no después de la Fase 3.

- **Borrados:** `app/core/census.py`, `app/core/census_store.py`, `test_census_cierre.py`,
  `test_census_roster.py`, `test_census_store.py`, y `DANIBOD_CENSUS_DB` del conftest.
- **Mudado, no borrado:** `roster_y_catalogo` (y `_sin_variante`) a `roster_declaration.py`, su
  único usuario, con sus dos tests. Sabotaje sobre el código mudado: rojo.
- **`test_menu_agent_read`:** el test de calibración contra las 9 capturas del menú se quedó (la
  lectura de S15 siembra la identidad), sin los dos umbrales de "censado" que eran del censo.
- **`db/census.db` no se borró: se renombró** a `db/census.retirado_20260917.db` (sigue fuera de
  git con `db/census*.db`). Tenía las dos corridas del 2026-08-17, la #2 abierta con 1/51. Borrar
  el archivo es de Daniel: un dato no se borra por ausencia de uso (B2).
- Las marcas `no_visto_en_censo_<fecha>` que ya estén en `agents.notas` se conservan (las
  escrituras de `notas` preservan las marcas ajenas, `test_s17_avatar_assignment`); ningún código
  las lee y nada nuevo las escribe.

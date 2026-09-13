# La pantalla en vivo: un shell, y una vista que sólo dice lo que vio

**2026-09-12** · diseño acordado con Daniel. Fase 1 de la interfaz.

Daniel lo planteó al cerrar el censo de armas: *"seguimos con la misma interfaz desde el comienzo"*.
Los mockups de Claude Design existen desde mayo y nunca se portaron. Esta es la primera fase: el
**shell de la ventana** y la **pantalla de captura en vivo**.

Referencia visual: [`21-panel-principal-captura-en-vivo.png`](../../../Interfaz/mockups/design_handoff_toast_variants/mockup-exports/21-panel-principal-captura-en-vivo.png),
con su fuente en [`source/panel.jsx`](../../../Interfaz/mockups/design_handoff_toast_variants/source/panel.jsx)
y los tokens en [`source/tokens.css`](../../../Interfaz/mockups/design_handoff_toast_variants/source/tokens.css)
(ya portados a [`app/ui/tokens.py`](../../../../app/ui/tokens.py)).

## Las decisiones, y quién las tomó

| decisión | elegido | por qué |
|---|---|---|
| alcance | **ventana completa** con sidebar, no sólo la pestaña | Daniel |
| chrome | **frameless**, barra de título propia | Daniel, sabiendo el costo (ver *Riesgos*) |
| botones de acción | **fuera** — la pantalla sólo informa | Daniel; y RNF-03 prohíbe actuar sobre el juego |
| centro de la pantalla | el **último ítem leído**, disco *o* arma | Daniel — el censo de armas no puede ser una pantalla muda |
| scoring y alternativas | **no se muestran** | Daniel: *"hay cierta lógica pero no es precisa"* |
| indicadores de telemetría | **fuera** (FPS, latencia, ciclos) | Daniel: no le dicen nada al usuario |
| espacio que sobra | **en blanco**, se ajusta sobre la marcha | Daniel |
| assets fuera de `app/` | se **mudan en esta fase** | evita que la pantalla nazca con la deuda D1 |

## 1 · Un shell, y vistas adentro

`app/main.py` tiene 1100 líneas: la ventana, el header, las 9 pestañas, el cableado del controller,
el tray y tres builders de tabs. Agregarle el sidebar y las columnas lo vuelve inmanejable.

```
app/ui/
├── shell/
│   ├── window.py       ← la ventana: marco nativo sin barra, sidebar + stack + status bar
│   ├── titlebar.py     ← la franja de arriba: logo, estado del monitor, — □ ×
│   ├── sidebar.py      ← 3 grupos, 9 ítems, contadores, card de hotkeys
│   └── statusbar.py    ← franja inferior (SQLite · OCR · ciclo · UID · reloj)
├── live/
│   ├── view.py         ← el layout + el contenedor derecho (hoy vacío)
│   ├── item_card.py    ← el ítem leído: hexágono si hay dueño, caja si no
│   └── console.py      ← la consola de reconocimiento (estado + log con tags)
└── views/              ← los builders de tabs de main.py, mudados sin rediseñar
```

**Los bordes, que es lo que importa:**

- El **shell no sabe nada** de discos ni de scoring: recibe vistas y las muestra. Se prueba solo.
- Cada card **recibe un diccionario y se pinta**. No consulta la DB, no habla con el monitor, no
  sabe de dónde salió el dato. Por eso se testea sin abrir la app ni el juego.
- El `MonitorController` **no cambia de lógica**: sigue emitiendo las mismas señales.
- Las 8 pestañas restantes entran al stack **tal como están**. Esta fase no las rediseña.

**La pestaña `Estado` desaparece.** Lo que muestra (versión de SQLite, backend de OCR, idioma,
contadores) es lo que el mockup puso en la barra inferior, visible siempre. Un lugar por dato (B1).

## 2 · La vista en vivo

### El dueño lo dice la pantalla, no el scoring

Sin scoring confiable **no hay "PJ recomendado"**, y el hexágono del mockup dibuja los 6 slots de
ese PJ. Pero hay un dueño que sí es certero: el que está **escrito en la pantalla**. El badge de un
disco equipado es observación, no predicción. De ahí la regla:

| qué se leyó | qué se dibuja |
|---|---|
| disco **con dueño visible** (S17 / inventario) | hexágono con el build de *ese* PJ, el slot del disco marcado |
| disco **sin dueño** (drop nuevo, libre) | la caja con el disco solo: set, slot, principal, secundarios |
| **arma** (RF-15) | los 6 campos del evento `weapon_seen` + su dueño + el ícono del engine |

Los 6 discos del build salen de **`inventory_discs.agente_asignado`** (305 filas), que es la
autoridad. Ojo con `AgentDiscRepo`, documentado como *"build actual de cada PJ"*: lee la tabla
`agent_discs`, que tiene **0 filas**. Es el repo al que uno iría a buscar esto, y habría dibujado un
build vacío para siempre **sin un solo error**.

> **Corrección:** la primera versión de este doc decía que *nadie lo usa*, y se lo llegó a borrar.
> Es falso: **lo usa el optimizador** para calcular el puntaje del build actual. El grep que
> "probó" que no tenía usos se inundó con los resultados de `app/build/` (el bundle de
> PyInstaller) y el `head` cortó justo la línea que importaba — A5 al pie de la letra. Se restauró
> desde `HEAD` antes de commitear nada.
>
> Y lo que destapó es peor que un repo engañoso: **el optimizador mide el build actual contra una
> tabla vacía**, así que `score_actual` es siempre 0 y cualquier build le parece una mejora. No es
> código muerto — lo dispara `sync_equip` al equipar. Queda como tarea aparte: tocarlo cambia lo
> que el optimizador recomienda, y no es de esta fase.

### Lo que NO se muestra, y por qué

- **Scoring y top de PJs.** El desglose se calcula (`desglose_top`, `top_candidatos`) pero los 51
  thresholds están en el default 0.75/0.50 — el tramo 4 del roadmap, *"captura pero no sugiere
  nada"*. Mostrar un número que no está calibrado es afirmar sin medir. El espacio queda **en
  blanco** y preparado: cuando se siembren los thresholds, las cards entran ahí sin rearmar nada.
- **Sinergia sugerida** (el panel violeta del mockup) es RF-12, Fase 3. No existe.
- **FPS y latencia.** El mockup dice `18 FPS · LATENCIA 312ms`. Medimos: el ciclo del inventario
  tarda **1569 ms** y el loop gira a ~30 ciclos por minuto. *18 FPS es ficción*, y ponerlo sería
  exactamente lo que A1 prohíbe. La barra de arriba queda con el logo, el **estado del monitor**
  (`CAPTURA` / `PAUSADO` / `EN REPOSO` — lo único que responde "¿me está mirando?") y los botones.

Los contadores del sidebar **sí** van: son cuentas de la DB, no estimaciones. Discos **385**,
Roster **51**, Armas **56**, Histórico de `inventory_disc_evaluations`, Lategame **0** (la tabla
está vacía, y muestra 0 — no se esconde).

## 3 · Lo que se toca del backend

Nada de captura, parseo ni persistencia. Tres cambios:

1. **Una señal nueva, `disc_observed`.** Revisando el código apareció que el caso central de esta
   pantalla **hoy no llega a la UI**: `_on_disc_from_monitor` hace `return` temprano para `S17`/`S9`
   —persiste, loguea y corta— así que el disco con dueño visible **nunca emitió nada**. La señal es
   observacional (sin score) y se emite junto al logging que ya existe, no en su lugar.
2. **`AgentDiscRepo` NO se toca** — ver la corrección de arriba: el optimizador depende de él.
3. **El hexágono necesita leer el build por PJ** desde `inventory_discs`: un método de repo nuevo,
   de sólo lectura.

El desglose del scoring **se sigue tirando** en `_build_payload`, porque no se muestra. Cuando
entre, son dos claves aditivas al payload y el toast no se entera.

## 4 · Los assets: la trampa del `.exe`, y un bug vivo

`asset_resolver` busca las imágenes en `Documentacion/Interfaz/...` subiendo **dos** niveles desde
el archivo — o sea, se escapa de `app/`, que es la regla D1.

> **Corrección a la primera versión de este doc**, que decía que los assets "mueren empaquetados".
> Es cierto sólo a medias, y el reparto es lo que importa: `app/build/main.spec` **sí** enumera
> `Set_Discos_Logo`, `splash_arts` y `Pj_stats`. El problema son las que **no** enumera.

| carpeta | quién la lee | consecuencia hoy |
|---|---|---|
| `Set-Discos_Package_Logo` (90) | `SetBadgeMatcher.from_package_badges()`, que el controller instancia al arrancar | **bug vivo**: en el `.exe` el matcher de sets por badge carga **0 referencias**, en silencio |
| `Engines_icons` (93) | nadie todavía — lo necesita la card de armas de esta fase | la card saldría sin ícono |
| `Facciones_Logos` (23) | `FACTIONS_DIR` declarado, sin función | latente |

Es la **tercera** vez que pasa lo mismo, y el propio spec lo tiene escrito: *enumerar carpeta por
carpeta ya falló dos veces* (`farm_nodes.toml` en agosto, los baselines de badges al día siguiente).
La lección no se aplicó a los assets de interfaz.

Se mudan las **5 carpetas — 377 archivos, ~11,7 MB** — a `app/resources/ui_assets/` con `git mv`,
más un cambio de constante y la función `engine_icon_path()` que hoy **no existe** aunque el
directorio sí esté declarado. `app/resources/` se bundlea **entera**, así que las cinco entran
solas y el bug se cierra de costado. `Pj_stats/` queda donde está: ya se bundlea y no es de la
interfaz.

## 5 · Cómo se verifica

- **Cada card es un diccionario convertido en píxeles**, así que se testea offscreen
  (`QT_QPA_PLATFORM=offscreen`, como los tests de toasts) afirmando sobre el texto que quedó:
  sin ítem todavía, arma en vez de disco, disco sin dueño, PJ sin disco en ese slot, arma fuera de
  catálogo.
- **El shell se prueba solo**: los 9 ítems cambian la vista del stack, y los contadores dicen lo
  que dice la DB.
- **Un test de los assets**: que las rutas resueltas caigan **dentro de `app/`** — es la única
  forma de que la regla D1 no se rompa de nuevo en silencio (en dev la ruta vieja funciona).
- La suite completa antes de commitear (2713 tests al 2026-09-12).

**Lo que no se puede automatizar** y Daniel tiene que mirar: que la ventana se arrastre, se
redimensione y haga snap como cualquier ventana de Windows, en sus dos monitores.

## Riesgos

- **El frameless.** Se advirtió y Daniel eligió igual. Se implementa por el camino sólido: en
  Windows se saca **sólo la barra de título** interceptando `WM_NCCALCSIZE` y se deja el marco
  nativo vivo por debajo, así el snap, los bordes de resize y la sombra siguen siendo de Windows.
  El frameless "a mano" (reimplementar arrastre y resize) es el que se llena de bugs.
- **La mudanza de assets es un diff largo** (287 renombres). Todo `git mv`, pero hay que revisar
  que ningún doc quede apuntando a la ruta vieja.
- **Las 8 vistas restantes se mudan sin rediseñar.** Si alguna depende de vivir en un `QTabWidget`,
  se ve al mudarla. No se conocen dependencias así.

## Queda abierto

1. **El espacio en blanco de la derecha**: Daniel lo ajusta sobre la marcha (candidatos: agrandar
   la consola, o una card nueva).
2. **Encender el scoring** depende del tramo 4 del roadmap (sembrar thresholds).
3. **Sinergia sugerida** depende de RF-12 (Fase 3).
4. Las otras 4 pantallas del mockup (discos, modal de disco, modal de PJ, toasts rediseñados)
   quedan para fases siguientes.

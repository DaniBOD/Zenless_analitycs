# SPEC · La página del PJ, con la declaración de sets y stats (2026-09-28)

**Estado:** diseño aprobado por Daniel el 2026-09-28, por partes ("si me cierra", tres veces).
Reemplaza, sin esperar el mockup, la pantalla que pedía `BRIEF_ficha_sets_y_stats.md`.

## Qué pidió Daniel

> "Ahora debemos incorporar la declaración de sets y stats en esa misma pantalla." (2026-09-28)
>
> "Para que sea mejor la UI, cuando se selecciona un PJ toma toda la pantalla en vez de salir una
> ventana flotante, y cuando se realicen las declaraciones ahí sí se usan ventanas flotantes."

El motor de la declaración ya está hecho y probado (SPEC 2026-09-27 del editor de la ficha):
`EditorFichaPJ` escribe cada elección (con backup, transacción, FK e integrity, y se niega en
sólo lectura) y `foto()` entrega lo que la pantalla necesita. Falta la pantalla.

## Decisiones

| pregunta | decisión |
|---|---|
| dónde vive la ficha | una **página** en el área de contenido de la ventana (el menú lateral queda), no un modal |
| cómo se organiza | **todo en una página**, sin pestañas: izquierda "HOY EN EL JUEGO", derecha "BUILD DECLARADA" |
| cómo se edita | **ventanas flotantes**, una por parte: sets, principales, secundarios, fijos |
| cuándo se guarda | **en el momento**, sin "Aceptar/Cancelar" (como el selector de prioridad) |
| cómo se mueve un secundario | **click en la ficha → menú** con los 5 niveles y "Como la guía" |
| los avisos | **junto al bloque que avisan**; el recuadro "Asesor" del modal (commit `88389da`) desaparece |

Pestañas internas y un modal más grande se descartaron. Las pestañas se habían elegido antes de
que Daniel pidiera la página completa; con el espacio de la página ya no hacen falta.

## Parte 1 · Navegación y estructura

- **Navegación.** Un click en un PJ del Roster cambia la ventana a la página del PJ, en el mismo
  `QStackedWidget` de las pestañas (`app/ui/shell/window.py`).
  - El menú lateral queda visible; **"← Roster"** arriba vuelve, y Escape también.
  - Al volver, el Roster queda donde estaba.
  - La página se arma de cero en cada entrada: los datos siempre frescos.
- **Paquete nuevo `app/ui/pj_pagina/`.** `PjModal` se retira: su contenido se porta y sus tests
  pasan a la página.
- **La página** (~1100×740 útiles), de arriba abajo:
  1. **Portada ancha:** arte, nombre, elemento, rol, M, facción y el selector de prioridad (igual que hoy).
  2. **Izquierda, "HOY EN EL JUEGO":** lo que muestra el modal de hoy, sin cambios de contenido.
     - stats de combate;
     - hexágono con los sets equipados, W-Engine, bonus y despertar.
  3. **Derecha, "BUILD DECLARADA":** un resumen de sólo lectura. El título lleva el conteo de
     avisos (`⚠ 1 · ℹ 2`). Cuatro bloques, cada uno con su **✎ Editar**, que abre su ventana, y
     sus avisos debajo:
     - **Sets:** el 4pc y el 2pc que usa el motor, y su origen (declarado / equipado / de la guía).
     - **Principales:** los de los slots 4, 5 y 6.
     - **Secundarios:** los 5 niveles con sus secundarios.
     - **Stats fijos:** objetivo, valor actual, cuánto falta, "el motor lo busca".
     - En todos, lo elegido por el usuario se distingue de lo que viene de la guía.
  4. Al pie, **"↺ Volver todo a la guía"** (`EditorFichaPJ.volver_a_la_guia`), con confirmación:
     borra todas las elecciones de ese PJ.

## Parte 2 · Las ventanas flotantes

**Lo común:**
- **Forma:** ventana sin marco, con borde del color del elemento, centrada sobre la página y modal.
  Título "SETS · ANBY" con ×. Al pie, "↺ Esta parte a la guía" y "Listo".
- **Guardado:** cada elección se guarda en el momento y la ventana se vuelve a dibujar **leyendo la
  DB** (lo guardado, no lo intentado), con los avisos de su parte. Al cerrarla, la página se refresca.
- **Sólo lectura** (`is_readonly()`): una franja "Modo sólo lectura: los cambios no se guardan" y
  los controles deshabilitados.
- **Escritura fallida:** el mensaje con la ruta del backup, en la ventana. Nunca un except mudo (A2).

**1. Sets** (`EditorFichaPJ.build`)
- **4pc:**
  - arriba, **"Automático"** (`build(None)`): el equipado si está en la guía; si no, el primero de la guía;
  - después, los 4pc de la guía en su orden, con logo;
  - después, "Otros sets" (los 30), marcados "fuera de la guía".
- **2pc:**
  - los renglones de la guía para el 4pc elegido, en orden de `pj_sets_2pc.grupo`, con
    "recomendado" y los renglones de dos sets
    (Ju Fufu con Monarca: 1 Sacudestrellas · 2 Tecno Pícido · 3 Voz Astral / Punk Hormonal · 4 Jazz Oscilante);
  - después, "Otros sets".
  - Una nota explica que ese orden es el que usa el motor para cambiar de 2pc cuando falta un fijo (R24).
- El set del 4pc no se ofrece como 2pc. Al cambiar el 4pc, el 2pc pasa al recomendado del
  renglón 1 de la guía para ese 4pc; si la guía no tiene, queda sin 2pc.

**2. Principales** (`EditorFichaPJ.principales`)
- Tres columnas, slots 4, 5 y 6, con los principales válidos del slot
  (`stats_vocab.CANONICAL_MAINS_VARIABLE`) como botones que se prenden y se apagan (varios por slot).
- Los de la guía llevan una marca "guía". Cada slot tiene su "↺ como la guía" (`None`).
- **Apagar el último vuelve el slot a la guía:** el editor rechaza la lista vacía.
- Un principal fuera de la guía muestra su ⚠ ahí mismo.

**3. Secundarios** (`EditorFichaPJ.nivel_substat`)
- Cinco filas (Imprescindible / Muy bueno / Bueno / Sirve / No sirve) con los 10 secundarios como fichas.
- Click → menú con los 5 niveles y "Como la guía" (`None`).
- Borde sólido si lo movió el usuario, tenue si sigue la guía.

**4. Stats fijos** (`fijo`, `desactivar_fijo`, `fijo_de_la_guia`)
- **Un renglón por fijo:**
  - stat;
  - **origen**: del kit (`pj_stats_fijos`), del set (`set_condiciones_4pc` del 4pc objetivo) o
    tuyo (`ajustes_usuario_fijos`);
  - objetivo editable;
  - valor actual (stats del PJ leídas del juego) y cuánto falta;
  - estado: "el motor lo busca" o "cumplido".
- Si el mismo stat viene del kit y del set, vale el mayor (`fijos_del_pj`) y se muestra ese origen.
  Un objetivo del usuario reemplaza al de la guía.
- **Acciones:**
  - cambiar el objetivo;
  - **desactivar** uno del kit o del set (objetivo NULL);
  - "↺ como la guía";
  - **"+ Agregar fijo":** uno de los 9 stats de `ajustes_usuario_fijos` que todavía no tenga objetivo.

## Parte 3 · Datos, refresco, errores y pruebas

**Datos:**
- La página lee de `foto()` (guía, elección, lo que usa el motor, fijos, avisos) y de `ficha_pj()`
  (stats, hexágono, arma, despertar). Sin segundas definiciones (B1).
- Lecturas puras nuevas, cada una desde su fuente única:
  - los **renglones del 2pc con orden y "recomendado"**: `leer_guia_pj` los guarda como conjunto y pierde el orden;
  - el **origen de cada fijo**;
  - los **principales válidos por slot**.
- Un mapa `tipo de aviso → bloque` decide dónde va cada aviso de `coherencia.avisos`.

**Refresco:**
- `EditorFichaPJ` ya llama a `agentes_cambiaron()`: el motor ve el cambio sin reiniciar.
- La columna SUGERENCIA de Discos se recalcula al volver a esa pestaña, como hoy.
- La celda del Roster se actualiza al cambiar la prioridad (la señal de hoy).

**Errores:** sólo lectura y escritura fallida, como en la parte 2. Avisos que no se pudieron
calcular: la página lo dice. PJ sin guía: los bloques dicen "sin guía todavía" y se puede declarar igual.

**Pruebas:**
- Pantalla con la DB del esquema real y filas propias; lo que escribe, sobre una **copia** de la DB.
- Un sabotaje por regla, sha256 de la DB igual antes y después de la suite.

**Verificación visual** (render fuera de pantalla con `QT_QPA_FONTDIR`, datos reales):
- Anby: fijo del set.
- Ju Fufu: renglones de dos sets.
- Gatillo: fuera de la guía.
- Ellen con DEF% declarado en una copia: el ⚠ de verdad.
- Un PJ sin guía.

## Orden de entrega (un commit por paso, suite completa antes de cada push)

1. Este SPEC.
2. Las lecturas nuevas: renglones del 2pc, origen de los fijos, principales por slot.
3. La página del PJ en reemplazo del modal: navegación y "← Roster", el contenido de hoy y el
   resumen de la build con sus avisos.
4. Ventana de secundarios.
5. Ventana de sets.
6. Ventana de principales.
7. Ventana de fijos.
8. Verificación visual y cierre. El SPEC con commits y lo medido; `BRIEF_ficha_sets_y_stats.md`
   marcado "resuelto sin mockup (SPEC 2026-09-28)"; el SPEC de los avisos, con que el recuadro fue reemplazado.

## Fuera de alcance

- Elegir la variante de la guía (5 PJs tienen más de una build).
- Recordar avisos descartados.
- Sugerencias del motor en la página del PJ (viven en Discos).

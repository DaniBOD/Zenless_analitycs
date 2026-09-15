# Pantalla de W-Engines — referencias para Claude Design

> Todo lo de esta carpeta se genera con `python tools/stage_design_engines.py` desde la raíz del
> repo. Los datos (`ARMAS_datos_reales.md`) se versionan; `assets/` está gitignoreada: son copias de
> archivos que ya viven en `app/resources/ui_assets/` y capturas de la app con datos de la cuenta.

## Qué subir

| archivo / carpeta | qué es | para qué |
|---|---|---|
| [`ARMAS_datos_reales.md`](ARMAS_datos_reales.md) | las 56 armas del inventario con rareza, especialidad, ATK base, stat, nivel, P y dueño; huecos del catálogo | **diseñar con la distribución real**, no con una grilla pareja de ejemplo |
| `assets/engines/` | 37 íconos, renombrados por el nombre **en español** que usa la tabla de datos | las cards / filas de arma |
| `assets/pj_avatares/` | 46 caras de los PJs que tienen un arma equipada | el dueño de cada arma |
| `assets/iconos_ui/` | íconos de elemento y de especialidad del juego | filtros y marcas |
| `assets/capturas_app/` | cómo se ven **hoy** las pantallas ya portadas a la app, con datos reales | **que la pantalla nueva sea de la misma familia** |
| `assets/mockups_previos/` | los mockups de Claude Design de esas pantallas | ver qué se tomó del diseño y qué se sacó |

## Cómo es la app hoy (mirá `capturas_app/` antes de proponer)

- **Shell**: sidebar a la izquierda (220 px), barra de título y barra inferior. El área de la pantalla
  mide **1100 × 756 en la ventana mínima** (1320 × 820) y crece al maximizar. La pantalla de armas es
  lo que va dentro de esa área: no rediseñar el shell.
- **Dos plantillas de pestaña ya existen:**
  - **Roster** (`01_roster`): grilla de celdas **sin scroll**, que se achican para entrar; header con
    conteos, 3 filas de filtros del dominio, leyenda obligatoria abajo.
  - **Discos** (`02`, `03`): tabla con scroll, filtros arriba, columna lateral con distribución y
    leyenda abajo.
  Con **56 armas**, las dos entran. Elegir una y decir por qué, o proponer otra con motivo.
- **Modales** (`04_modal_pj`, `05_modal_disco`): 1000 × ~620, sin marco, se abren con click y cierran
  con × o Esc.
- **La única vista de arma que existe hoy** es la card de la vista en vivo (`06`): ícono, nombre,
  rango, nivel, P, stat secundario y dueño.

## Reglas que ya están decididas (no cambiarlas en el diseño)

1. **Sólo informa.** Nada que salga del scoring: no hay score de arma, "mejor arma para X",
   recomendaciones de la comunidad ni botones de acción (optimizar, equipar, sugerir). Las tablas que
   los alimentarían están **vacías** — ver `ARMAS_datos_reales.md`. Si el diseño quiere reservar
   un espacio para eso, que quede **explícitamente en blanco**, como la región derecha de la vista en
   vivo.
2. **Refinamiento se llama P1–P5**, como en el juego (el mockup viejo del modal de PJ decía R1–R5).
3. **Un dato que no hay se dice**, no se inventa: `sin dato`, `sin leer`, `falta ícono`. Hoy:
   - ~~3 armas sin ícono~~ — Daniel los descargó el 2026-09-15: hoy 40/40. Si llega un arma sin
     archivo, hueco neutro, no el ícono de otra arma.
   - **7 armas sin especialidad** en el catálogo.
   - **Tetera esmeraldina** tiene ATK base y valor del stat en blanco (se leyó a Nv 50, no a 60).
4. **Las copias repetidas son normales**: 5 Llanto mielgo, 5 Última cena, 3 Cañón bombástico… se
   guardan como material de refinamiento. Una fila por arma física; si se agrupan por modelo, que el
   conteo de copias se vea.
5. **Libre ≠ sin dato**: 10 armas están LIBRES (nadie las equipa). Los colores de estado ya existen en
   la app: **EQUIPADO verde, LIBRE celeste**.
6. **Rareza**: sólo hay **S (12) y A (44)** en el inventario. En la app, S amarillo y A violeta.

## Cosas a saber de los assets

- ⚠️ **`iconos_ui/` está incompleto.** Especialidades presentes: Anomalía (`Anomaly`), Aturdimiento
  (`Stun`), Defensa (`Defense`), Ruptura (`Rupture`), Soporte (`Support`). **Falta Ataque**, que es la
  especialidad **más numerosa** (16 de 56). Elementos: faltan **Viento** y **Lumen**. Si se usa un
  placeholder, decirlo; no presentarlo como el ícono del juego.
- **Nombres del mismo eje con dos grafías**: el catálogo de armas dice *Ruptura* donde el roster dice
  *Disruptivos*. Es la misma especialidad. En pantalla usar una sola; la unificación en datos es
  aparte.
- **Los stats secundarios están en inglés** en el catálogo (`CRIT Rate`, `Energy Regen`, `PEN Ratio`),
  mientras los discos los tienen en español. Mostrarlos tal cual está bien para el diseño; no
  inventar la traducción.
- **Las pasivas no son el texto oficial**: están resumidas a mano, mezclando español e inglés.
  Sirven para dimensionar un bloque de texto, no para citarlas como si fueran del juego.
- Los íconos de engine son **arte del juego**: no redibujarlos ni uniformar su estilo.

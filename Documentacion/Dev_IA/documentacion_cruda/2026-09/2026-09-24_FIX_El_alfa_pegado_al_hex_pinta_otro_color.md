# FIX · El alfa pegado al hex pinta otro color

> 2026-09-24 · UI (Roster, Armas) · diagnóstico escrito antes de tocar código (E1).

## El mecanismo

Varias marcas armaban un color translúcido pegándole dos dígitos de alfa al hex:
`QColor(AMBAR + "40")`, o en QSS `border: 1px solid {AMBAR}88`. La intención era `#RRGGBBAA`.
Qt lee un hex de 8 dígitos como **`#AARRGGBB`**: el alfa va PRIMERO.

```
QColor("#F0AA3C40").name(QColor.NameFormat.HexArgb) == "#f0aa3c40"
                                   → alfa F0 (94 %), color AA3C40 (rojo)
```

El resultado no es "el mismo ámbar un poco más fuerte": es **otro color, casi opaco**. El ámbar
pasa a rojo y el naranja del ∞ a magenta.

**El QSS parsea igual.** Verificado pintando un `QFrame` con `border: 1px solid #F0AA3C88` sobre
negro: el borde queda `#a03880` (magenta). Con `rgba(240,170,60,136)`, `#805b20` (ámbar atenuado).

Ya había pasado una vez con la barra de prioridad alta (`pintar_marca_prioridad`), arreglada con
`setAlpha`, que es el patrón que se sigue ahora.

## Los casos (grep sobre `app/`, sin `app/build/`)

Búsqueda: `+ "XX"` y `{...}XX` con XX hexadecimal, en `.py` de `app/`. Cinco coincidencias, todas en
`app/ui`, ninguna en `app/core`:

| marca | dónde | intención | pintado hoy (medido) |
|---|---|---|---|
| esquina rayada "le faltan datos" | `roster/celda.py` `CeldaRoster.paintEvent` | ámbar 25 % | `a1393d` rojo |
| halo del rango ∞ | `roster/celda.py` `_Rango.paintEvent` | naranja 40 % | `8a3d66` magenta |
| esquina rayada "falta un dato del catálogo" | `armas/celda.py` `CeldaArma.paintEvent` | ámbar 20 % | `a13931` rojo |
| borde de la tarjeta de PJ sin arma | `armas/view.py` `_TarjetaPJ` (QSS) | ámbar 53 % | `a13981` magenta |
| borde del aviso "PJs sin W-Engine" | `armas/view.py` `_armar_panel_pjs` (QSS) | ámbar 40 % | ídem, sobre el fondo del aviso |

Los píxeles se midieron con `widget.grab().toImage()`, en el hueco entre dos rayas de la esquina y
sobre el borde. Una primera medición de las esquinas dio "sin pintar": la celda de Roster mide 176
px de ancho aunque se le pida 122 (mínimo de su layout), y estaba mirando fuera del triángulo.

## El arreglo

- En `QPainter`: `QColor(color)` + `setAlpha(0xNN)`, con el mismo alfa que se quiso escribir.
- En QSS: `rgba(r, g, b, NN)` con el mismo alfa. *(Al final no: se usó `name(HexArgb)`, ver
  Resultado.)*

Cada uno con un test que captura el widget y compara el píxel de la marca contra la mezcla
esperada (el color con su alfa sobre el fondo que se mide al lado, no uno supuesto). Un commit por
marca.

El cambio visible: las marcas se ven **más tenues** que hasta hoy, porque hoy salían casi opacas
(alfa F0/FF en vez de 20-53 %). Es lo que el código decía que quería.

## Resultado

| commit | marca | sabotajes (todos rojos) |
|---|---|---|
| `da0aa29` | esquina de Roster | vuelve `+ "40"` · alfa 0xF0 |
| `e8938a1` | halo del ∞ | vuelve `+ "66"` · halo opaco |
| `3a8192c` | esquina de Armas | vuelve `+ "33"` · alfa del Roster (0x40) |
| `f67bcff` | borde de la tarjeta (QSS) | vuelve `{AMBAR}88` · el helper pega el alfa al final · opaco |
| `265fd8b` | borde del aviso (QSS) | vuelve `{AMBAR}66` · alfa de la tarjeta (0x88) |
| `9ac5909` | guarda sobre `app/ui` | las dos formas reintroducidas · carpeta equivocada · ignora el `+` · cuenta comentarios |

Todos los sabotajes con reemplazo exigiendo `count == 1` y sha256 del archivo verificado al
restaurar. Los tests están en `app/tests/unit/test_colores_con_alfa.py`.

Para el QSS no hay un `setAlpha` a mano: `_con_alfa(color, alfa)` en `armas/view.py` arma el
`QColor`, le pone el alfa y lo escribe con `name(HexArgb)`, que sale en el orden que el QSS lee
(`#88F0AA3C`). Así el alfa lo acomoda Qt y no quien escribe el stylesheet.

**La guarda.** Es la segunda vez que aparece (la barra de prioridad antes, cinco marcas ahora), y
una nota no lo evita (C3). `alfas_pegados` recorre los tokens de cada `.py` de `app/ui` y marca
`x + "40"` y `f"...{x}88..."`. Mira tokens para que un comentario que cuenta el error no cuente como
el error. Límite conocido: `f"{n}ab"` tiene la misma forma que `f"{x}88"`; si algún texto real cae
en eso, la guarda lo va a marcar y habrá que decidir en ese momento. Hoy, cero coincidencias.

Un error propio en el camino: la primera medición de las esquinas dio "sin pintar", porque tomé
el ancho pedido (122) y no el real (176). Los tests miden sobre `img.width()`.

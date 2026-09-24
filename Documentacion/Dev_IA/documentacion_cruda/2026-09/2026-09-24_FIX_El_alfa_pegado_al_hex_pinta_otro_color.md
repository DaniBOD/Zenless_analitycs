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
- En QSS: `rgba(r, g, b, NN)` con el mismo alfa.

Cada uno con un test que captura el widget y compara el píxel de la marca contra la mezcla
esperada (el color con su alfa sobre el fondo que se mide al lado, no uno supuesto). Un commit por
marca.

El cambio visible: las marcas se ven **más tenues** que hasta hoy, porque hoy salían casi opacas
(alfa F0/FF en vez de 20-53 %). Es lo que el código decía que quería.

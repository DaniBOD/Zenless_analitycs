# SPEC · Los avisos del asesor en el modal de PJ (2026-09-28)

**Estado:** **hecho** el 2026-09-28 (ver "Implementación"). Diseño aprobado por Daniel ese día
("Columna 3, abajo").

## Qué pidió Daniel

> "Vamos con los avisos del asesor en la ficha." (2026-09-28)

El asesor de coherencia (`app/core/coherencia.py`, SPEC 2026-09-27 del editor de la ficha) ya
calcula los avisos. Hoy sólo los ve `foto()`, que espera la pantalla de la ficha (mockup pedido en
`BRIEF_ficha_sets_y_stats.md`). El brief (§2.5) pide los avisos **junto a lo que avisan** y **un
resumen arriba**. Las secciones junto a las que irían (sets, secundarios, fijos) todavía no existen
en el modal. Por eso ahora va **sólo el resumen**, con los estilos actuales. Cuando llegue el mockup,
cada aviso se muda junto a su sección.

## Decisiones

| pregunta | decisión |
|---|---|
| dónde | **columna 3 del modal de PJ, abajo**, debajo de Despertar: es la columna más ancha y la que más lugar libre tiene |
| qué | los avisos del asesor (`avisos_de`), primero los ⚠️ y después los ℹ️, con el texto que ya arma el motor |
| acciones | ninguna: avisa, no bloquea ni corrige |

## Medido antes de diseñar (2026-09-28, DB real en sólo lectura, sha igual antes/después)

- `AgentRepo(con).get_by_id` + `avisos_de`: **mediana 7 ms, máximo 10 ms** sobre los 52 PJs.
  Entra de sobra en los 500 ms (RNF-06): se calcula **al armar la ficha**, sin hilo aparte.
- Hoy: **0 ⚠️ y 22 ℹ️ en 16 PJs, con un máximo de 2 por PJ**. El recuadro entra sin scroll.

## Diseño

- **`FichaPJ.avisos`** (`app/ui/pj_modal/datos.py`): tupla de `Aviso`, o `None` si no se pudieron
  calcular. `ficha_pj` los pide a `avisos_de(con, AgentRepo(con).get_by_id(id))`, la misma función
  que usa `foto()` (una sola autoridad). Si el cálculo falla, se loguea con traceback y la ficha dice
  **"no se pudieron calcular"** (A2: que la falla se vea, no que se confunda con "sin avisos").
- **Recuadro "Asesor"** (`app/ui/pj_modal/modal.py`, columna 3): el título lleva el conteo
  (`ASESOR · 2`). Si hay algún ⚠️, el borde va naranja (`T.WARNING`, el de "descartar"); si hay
  sólo ℹ️, gris. Cada aviso es una línea con su ícono y su texto, con salto de línea. Sin avisos:
  *"Sin avisos."* (no "coincide con la guía": un PJ sin guía tampoco tiene avisos).
- El modal sigue sin consultar nada: recibe la ficha ya armada y se testea sin DB.

## Orden de entrega (un commit por paso, suite completa antes del push)

1. Este SPEC.
2. `FichaPJ.avisos` + recuadro, con sus tests y sabotajes.
3. Verificación visual: el modal renderizado fuera de pantalla con Anby (2 ℹ️), Grace (1 ℹ️) y un
   PJ sin avisos.

## Implementación (2026-09-28)

| paso | commit | qué |
|---|---|---|
| SPEC | `a429682` | este documento |
| recuadro | `88389da` | `FichaPJ.avisos` (`avisos_del_pj`) + recuadro "Asesor" + `test_pj_modal_asesor.py` |

### Lo que encontraron las verificaciones

- **Seis sabotajes, los seis en rojo**: sin orden (los ⚠️ quedan detrás), falla tomada como "sin
  avisos", avisos no pedidos, recuadro sin agregar, borde siempre gris, `None` mostrado como
  "Sin avisos.". El sha de la DB, igual antes y después.
- **Verificación visual** con la DB real en sólo lectura (Anby, Miyabi, Grace, Ellen, y Ellen con un
  ⚠️ simulado de DEF%). El borde inferior del recuadro queda entre los 489 y los 532 px de 640:
  entra sin scroll, con unos 100 px libres.
- El render fuera de pantalla sale en cuadraditos si Qt no encuentra fuentes:
  `QT_QPA_FONTDIR=C:/Windows/Fonts`.
- Un "Sin avisos: coincide con la guía" habría mentido para un PJ sin guía, que tampoco tiene avisos:
  el texto quedó en "Sin avisos.".

## Fuera de alcance

- Mudar cada aviso junto a su sección (espera el mockup de la ficha).
- Recordar avisos descartados (fuera del brief).

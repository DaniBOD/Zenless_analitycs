# Assets para Claude Design — qué hay en esta carpeta

> Acompaña a [`BRIEF_roster_y_confirmaciones_pasivas.md`](./BRIEF_roster_y_confirmaciones_pasivas.md)
> y a [`ROSTER_datos_reales.md`](./ROSTER_datos_reales.md).

## `assets/` — 9.7 MB, 298 archivos

Se genera con `bash tools/stage_design_assets.sh` desde la raíz del repo.

**Está gitignoreada a propósito:** son copias de assets que ya viven versionados en
`Documentacion/Interfaz/`. Duplicar 10 MB de webp en el historial es exactamente lo que costó
reescribir el historial la vez que entraron los íconos de engines full-res.

| carpeta | archivos | qué es | para qué sirve en este brief |
|---|--:|---|---|
| `pj_avatares/` | 58 | `<PJ>-ico.webp` — retrato recortado | **la grilla del Roster**; los avatares de los toasts violeta |
| `pj_splash/` | 57 | `<PJ>-extend.webp` — arte de cuerpo entero | fondos del modal de PJ; hero de la pantalla Roster |
| `facciones/` | 22 | logos de las 16 facciones (+ variantes) | agrupar/filtrar el roster por facción |
| `iconos_ui/` | 13 | íconos de **elemento** (Físico, Eléctrico, Hielo, Fuego, Éter…) y de **rol** (Ataque, Anomalía, Aturdimiento, Soporte, Defensa, Disruptivos) | los dos ejes principales de la grilla |
| `sets_discos/` | 56 | logos de los sets de discos | el `DiscThumb` de los toasts `REEMPLAZADO` / `AHORA EN`; futura pestaña Discos |
| `engines/` | 92 | íconos de W-Engines | el toast `W-ENGINE VISTO`; futura pestaña Armas |

### Cosas a saber antes de usarlos

- **Los logos de facción tienen identidad visual propia del juego. No rediseñar ni uniformar
  estilo** — el usuario los reconoce por su forma exacta.
- **`iconos_ui/` incluye íconos de mecánica específicos de un PJ** (`Icon_Auric_Ink_(yixuan)`,
  `Icon_Frost_(miyabi)`, `Icon_Honed_Edge_(ye_shunguan)`). No son elementos del juego: son recursos
  únicos de esos personajes. No mezclarlos con los 7 elementos reales.
- ⚠️ **`iconos_ui/` está incompleto y conviene saber exactamente cómo.** Lo que hay:

  | eje | presentes | **faltan** |
  |---|---|---|
  | elemento (7) | Físico, Eléctrico, Éter, Fuego, Hielo | **Viento**, **Lumen** (los 2 más nuevos, 1 PJ c/u) |
  | rol (6) | Anomalía, Aturdimiento (`Stun`), Defensa, Disruptivos (`Rupture`), Soporte | **Ataque** |

  El de **Ataque falta y es el rol más numeroso** (15 de 49 PJs). Si la grilla se apoya en el ícono
  de rol, ese hueco se ve en la tercera parte de la pantalla. Se puede diseñar un placeholder, pero
  hay que decirlo explícitamente — no inventarlo como si fuera el del juego.
- **Los avatares no cubren a los 6 personajes no obtenidos por igual** — ver la tabla en
  `ROSTER_datos_reales.md`, incluido el lío `Lichter` / `Lighter`.
- Hay archivos con dos convenciones de nombre (`Aria_ico.webp` con guion bajo contra
  `Burnice-ico.webp` con guion medio). Es ruido histórico, no significa nada.

## Lo que NO se copió, y dónde está

**`Documentacion/Interfaz/referencias_visuales/`** — 6 capturas full-res de pantallas reales del
juego, 16 MB. Son la mejor referencia de *cómo se ve ZZZ de verdad*, pero pesan más que todo el
resto junto. Subilas a mano si el diseño las necesita:

| archivo | qué muestra | relevancia |
|---|---|---|
| `02_agente_hexagono_6_slots.png` | pantalla de agente con los 6 slots en hexágono | **alta** — es la vista que la pestaña Roster indexa |
| `01_disco_detalle_pantalla_completa.png` | detalle de un disco | media |
| `03_modal_disco_overlay.png` | overlay de disco sobre la pantalla | media |
| `04_pantalla_resultado_grid_drops.png` | grilla de drops | media — patrón de grilla del juego |
| `05_upgrade_post_efectos_glow.png` | efectos de glow post-mejora | baja |
| `06_tienda_musica_afinacion.png` | tienda de música | baja |

⚠️ **Ojo con el hexágono:** la numeración 1-6 de los slots **no es como en Genshin**. Está
documentada en el repo; no deducirla de la posición visual.

**`Documentacion/Interfaz/Set-Discos_Package_Logo/`** — 90 archivos, la misma familia de sets pero
en variante `_S` / `_A` / `_B` (el arte cambia según rareza). No se copió porque `sets_discos/` ya
cubre el caso de uso del brief; está ahí si hace falta mostrar rareza en el arte del set.

**Los mockups ya entregados** — `Documentacion/Interfaz/mockups/design_handoff_toast_variants/`
tiene 28 PNG exportados (las 4 variantes de recomendación, el panel de captura en vivo, la pestaña
Discos, el modal de disco y 5 modales de PJ) más el código JSX fuente. **El modal de PJ ya está
diseñado** — la pantalla Roster es su índice, así que conviene mirarlo antes de empezar.

## Los archivos sueltos que ya estaban acá

Los `*.webp` en la raíz de esta carpeta (5 PJs, 4 facciones, 7 sets, 5 engines) son de la primera
sesión de diseño. Quedaron por compatibilidad con los briefs viejos; **para lo nuevo usar
`assets/`**, que es el catálogo completo.

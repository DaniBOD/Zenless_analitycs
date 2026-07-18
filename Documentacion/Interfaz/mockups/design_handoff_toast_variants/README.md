# Handoff: Toast "REEMPLAZADO" + "EQUIPADO" + Consola MSS

## Overview
DaniBOD ZZZ Analytics ya tiene un sistema de toasts flotantes portado a la app real (`app/ui/toast.py`, `app/ui/tokens.py`, `app/ui/live_panel.py`, PySide6). Este mockup HTML añade **2 variantes de toast nuevas** y **1 sección nueva del panel principal** que todavía NO existen en el código Python:

1. **Toast "REEMPLAZADO"** — confirmación pasiva de que el sistema detectó (vía OCR) que un disco fue movido de un PJ a otro. No es una sugerencia — es una notificación de que ya ocurrió y la DB se sincronizó.
2. **Toast "EQUIPADO"** — el flujo correcto es: el sistema sugiere "EQUIPAR" (ya existe) → el sistema detecta vía OCR que el usuario efectivamente lo hizo en el juego → dispara "EQUIPADO" como confirmación pasiva de esa sugerencia. Mismo color/verde que "Equipar" (misma acción, distinta fase), sin countdown ni urgencia.
3. **Consola MSS** — panel de logs en vivo en la pestaña "Captura en vivo" que narra el reconocimiento de pantallas de la máquina de estados (FSM) del sistema: transiciones de pantalla, confianza OCR, discos parseados, etc.

## About the Design Files
Los archivos en `source/` son **referencias de diseño en HTML/JSX** (prototipo con Babel standalone en el navegador) — no son código para copiar tal cual. La tarea es **recrear este comportamiento en PySide6**, siguiendo los patrones ya establecidos en `app/ui/toast.py` y `app/ui/tokens.py` (que ya portaron las 5 variantes originales del mismo sistema).

## Fidelity
**Hi-fi.** Colores, tipografía, espaciados y layout son finales — replicar pixel a pixel usando los helpers Qt ya existentes en `tokens.py` (`font_ui`, `font_display`, `font_mono`, `font_caps`, `color()`).

## Screens / Views

### 1. Toast "REEMPLAZADO"
- **Purpose:** confirmar swap de disco entre 2 PJs detectado por OCR (evento pasivo, sin acción del usuario requerida).
- **Frame:** mismo contenedor base que las otras 5 variantes — 380×116px, `BlockBox` radius 16, border 1.5px, `pattern="carbon"`, `glassTop=true`, glow del color de acento.
- **Acento:** violeta `--purple #9D4EDD` (color "libre" del sistema, no usado por otra variante activa) — border, glow, icono, flechas, ring del avatar destino.
- **Header:** chip 18×18 con icono `swap` (dos flechas ⇄, definido como path SVG nuevo), label "REEMPLAZADO" en violeta 11px 700 weight letter-spacing 0.12em, separador vertical, `#{id}` en gris muted. A la derecha: badge verde `✓ SINCRONIZADO` (NO countdown) — border `rgba(123,201,31,0.4)`, bg `rgba(123,201,31,0.08)`, radius 3px.
- **Body (fila horizontal, gap 4px):**
  - Avatar origen (56px col): label "DEJA" (8px muted), círculo 38px atenuado (`opacity:0.55`, `grayscale(0.5)`, sin ring), nombre 10px.
  - Flecha violeta 22×14 con drop-shadow.
  - Disco central (flex 1): `DiscThumb` 42px tono purple, tier badge escalado (`size * 0.36` — ver fix de bug abajo), debajo nombre del set (10.5px, ellipsis a 124px max-width) + "Slot N" (9px muted).
  - Flecha violeta.
  - Avatar destino (56px col): label "EQUIPA" (violeta), círculo 38px resaltado con ring 1.5px violeta + glow `0 0 9px rgba(157,78,221,0.55)`, nombre 10px primary + mind count.
- **Footer:** barra 3px violeta ESTÁTICA (sin pulso, a diferencia de la urgency bar de las variantes de sugerencia) + línea "EQUIPAMIENTO SINCRONIZADO" / "inventory_discs ✓" en 9px muted.
- **Estados:** idle (auto-dismiss ~3s, más corto que las variantes de sugerencia que duran 5s), hover (congela dismiss, muestra prompt "CLICK ABRIR PANEL · HOVER CONGELADO"), fade-out (opacity 0.35).

### 2. Toast "EQUIPADO"
- **Purpose:** confirmar que una sugerencia "Equipar" fue aplicada por el usuario en juego.
- **Frame:** idéntico a "Equipar" original (mismo layout de disco + PJ objetivo + score), pero:
  - Badge superior derecho: `✓ CONFIRMADO` (verde) en vez de countdown.
  - Footer: barra estática (no pulsante) + texto "SUGERENCIA APLICADA · DETECTADO EN JUEGO" / "inventory_discs ✓" en vez de barra de urgencia + threshold.
  - Mismo color verde `--positive #7BC91F` que "Equipar" — es la misma acción, fase de confirmación.

### 3. Consola MSS (panel "Captura en vivo")
- **Ubicación:** franja inferior a todo el ancho de la pestaña, debajo de la grilla de 3 columnas (disco/scoring/alternativas), altura fija 172px.
- **Header:** icono morado pulsante + "Consola MSS · reconocimiento de pantallas" + badge "FSM v0.9.4" + breadcrumb de pantallas recorridas (`MAIN_MENU › AGENTS › DRIVE_DISCS`, la última resaltada en amarillo) + indicador "SYNC" verde.
- **Body (split):**
  - Columna izquierda (232px, fondo más oscuro): "ESTADO ACTUAL" — nombre del estado FSM en grande (19px display font, amarillo, con cursor parpadeante), subpantalla, y 3 métricas (CONF OCR, FPS, TRANS).
  - Columna derecha (flex, monospace 11px, auto-scroll): feed de líneas con timestamp, tag coloreado por tipo (`[NAV]` info, `[MSS]` purple, `[OCR]` yellow/positive, `[CAP]` muted, `[SCORE]` positive), mensaje. Nueva línea cada ~1.1s, mantiene últimas 24.

## Interactions & Behavior
- **REEMPLAZADO / EQUIPADO:** disparados por eventos del backend (no por click del usuario) — igual que el resto de toasts, hover pausa el auto-dismiss y abre el panel al click; auto-dismiss más corto (~3s) que las variantes de sugerencia (~5s) porque son confirmaciones, no requieren decisión.
- **Consola MSS:** feed continuo mientras la app está en `Captura en vivo`. Auto-scroll al último log. El bloque "ESTADO ACTUAL" se actualiza en cada transición de la FSM.

## State Management
- Toast: mismo modelo que las 5 variantes existentes (`idle` → `hover`* → `fade`/`expanding`), sin estado adicional.
- Consola MSS: buffer circular de últimas N líneas (usar la misma estructura de eventos que ya emite `app/core/monitor.py` / `app/core/detector.py` hacia el log de estados).

## Design Tokens
Todos ya existen en `app/ui/tokens.py` — **excepto** que el diccionario `VARIANTS` en `tokens.py` solo tiene 5 entradas y falta agregar `reemplazado` y `equipado`:

```python
VARIANTS["equipado"]    = {"label": "EQUIPADO",    "color": POSITIVE, "tone": "yellow", "icon": "check"}
VARIANTS["reemplazado"] = {"label": "REEMPLAZADO", "color": PURPLE,   "tone": "purple",  "icon": "swap"}
```
`PURPLE = "#9D4EDD"` ya existe en tokens.py (se usaba para tags de IA/RF) pero nunca se había usado como acento de variante de toast.

Falta también un icono `swap` (2 flechas cruzadas) en el set de iconos Qt — ver el path SVG nuevo en `source/components.jsx` (función `Icon`, case `"swap"`) para portarlo a `QPainterPath` o el sistema de iconos que use `app/ui/toast.py`.

## Assets
Avatares de PJ usados en el ejemplo: `assets/yixuan-ico.webp`, `assets/yanagi-ico.webp` (ya existen en el repo, mismos assets que usa el resto del sistema). Ningún asset nuevo requerido.

## Files
- `source/toasts.jsx` — variantes de toast (buscar `SwapToastContent`, `EquipadoContent`, `VARIANTS`).
- `source/panel.jsx` — Consola MSS (`MssConsole`, `MSS_SEQ`).
- `source/components.jsx` — icono `swap` nuevo + `Rarity` con `size` prop (bugfix: antes tenía tamaño fijo 24px, ahora escala proporcional al disco — aplicar el mismo fix si el badge de tier en Qt está hardcodeado).
- `source/tokens.css` — referencia de colores (ya portado 1:1 en `tokens.py`, solo falta lo señalado arriba).
- `source/DaniBOD ZZZ Analytics.html` — documento completo, abrir en navegador para ver todo interactivo.

Contraparte real a modificar: `app/ui/toast.py`, `app/ui/tokens.py`, `app/ui/live_panel.py`.

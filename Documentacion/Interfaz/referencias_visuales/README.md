# Referencias visuales — Estilo del juego Zenless Zone Zero

Esta carpeta contiene 6 capturas curadas del juego que **definen el lenguaje visual** que el `.exe` debe heredar. La meta es que la app se sienta como una extensión natural del juego, no como una herramienta de terceros.

## Capturas incluidas

| # | Archivo | Qué muestra | Para qué la usamos |
|---|---------|-------------|---------------------|
| 01 | `01_disco_detalle_pantalla_completa.png` | Vista detallada de un disco "Jazz caótico" — panel oscuro con stats, hexágono de slots a la derecha, lista de inventario a la izquierda | **Layout maestro:** tipografía, jerarquía, posicionamiento de stats, color del título de set, formato de substats con badges `+N` |
| 02 | `02_agente_hexagono_6_slots.png` | Hexágono de 6 slots equipados del agente | **Composición icónica de ZZZ** — la presencia del hexágono es signature visual, debemos preservarla en pestañas Roster y Captura en vivo |
| 03 | `03_modal_disco_overlay.png` | Modal de detalle de disco sobre fondo oscuro semi-transparente | **Patrón de modales:** cómo el juego oscurece el fondo al abrir un overlay, opacidad, blur sutil |
| 04 | `04_pantalla_resultado_grid_drops.png` | Resultado post-patrulla con grid de drops nuevos | **Cómo presentar lotes** — útil para la pestaña Histórico cuando muestra múltiples discos del último farmeo |
| 05 | `05_upgrade_post_efectos_glow.png` | Pantalla de upgrade con efectos glow y barra MAX en verde | **Animaciones de feedback** — cómo el juego celebra acciones positivas con glow + color saturado |
| 06 | `06_tienda_musica_afinacion.png` | Tienda de Música (Afinación) — interfaz secundaria | **Layout asimétrico** — paneles flotantes, elementos no alineados a grid rígido, sensación de "broadside" |

## Sistema visual extraído del juego

### Paleta exacta (medida sobre las capturas)

| Token | Hex | Uso |
|-------|-----|-----|
| `bg-base` | `#0a0a0a` | Fondo principal (negro casi puro con ligero degradado) |
| `bg-panel` | `#1a1a1a` ~ `#222222` | Paneles flotantes, semi-transparentes con `rgba(20,20,20,0.92)` |
| `bg-overlay` | `rgba(0,0,0,0.75)` | Backdrop de modales |
| `border-subtle` | `#3a3a3a` | Bordes de paneles, separadores |
| `text-primary` | `#f5f5f5` | Texto principal, casi blanco puro |
| `text-secondary` | `#a8a8a8` | Texto secundario, labels, valores no destacados |
| `text-muted` | `#6b6b6b` | Texto tertiary, hints |
| **`accent-yellow`** | **`#FFCB05`** | **Color SIGNATURE del juego** — selección, badges de nivel, links activos, highlights, hover states |
| `accent-yellow-glow` | `rgba(255,203,5,0.4)` | Glow sutil alrededor del amarillo en elementos seleccionados |
| `action-positive` | `#7BC91F` | Verde lima (Mejorar, MAX, OK) — más saturado que un verde estándar |
| `action-warning` | `#FF6B47` | Rojo-naranja vibrante (Cerrar, Descartar, alertas) |
| `action-info` | `#5BC0EB` | Azul cyan suave (info, links secundarios) |
| `accent-purple` | `#9D4EDD` | Para acentos de IA / sinergias (RF-12) |
| `accent-pink` | `#FF4D8A` | Reservado para retro-feedback bayesiano (RF-13) |

### Tipografía

- **Familia:** sans-serif moderna y angular (similar a "ZZZ Custom" o **Bahnschrift** / **Rajdhani** / **Saira** como sustitutos web/Qt).
- **Pesos:** Regular (400) cuerpo, Semibold (600) títulos, Bold (700) números grandes.
- **Tamaños:** títulos 18-22 px / cuerpo 13-14 px / labels 11-12 px / números destacados 24-32 px.
- **Números:** **siempre tabular-nums** para alineación de columnas (stats, scores, valores monetarios).
- **Espaciado:** letter-spacing leve en mayúsculas (+0.5 px) para sensación más "tech".

### Geometría y bordes

- **Border-radius:** `0` (cero) en la mayoría de paneles — el juego usa **rectángulos puros** + bordes diagonales/chamfered selectivos, no esquinas redondeadas.
- **Cortes diagonales (chamfered corners):** característica visual signature. Aplicar en toast, badges principales, botones primarios. CSS: `clip-path: polygon(...)` o pseudo-elementos.
- **Bordes:** 1 px sólido `border-subtle`, o 2 px `accent-yellow` cuando seleccionado.
- **Sombras:** `box-shadow: 0 4px 16px rgba(0,0,0,0.6)` para paneles flotantes; **glow amarillo** `box-shadow: 0 0 12px rgba(255,203,5,0.5)` para elementos activos.

### Iconografía

- **Estilo:** lineales/outline o flat con relleno, no skeuomórficos.
- **Forma base:** circular con fondo oscuro (badge style) — ej. los iconos de stats al lado del valor.
- **Color:** monocromáticos, generalmente blancos sobre fondo, amarillos cuando representan acción/selección.

### Efectos y animaciones

- **Glow en hover:** halo amarillo que aparece en 200 ms ease-out.
- **Selección:** borde amarillo + ligero scale 1.02 + glow.
- **Confirmación de acción:** flash blanco brevísimo (80 ms) seguido de transición al estado nuevo.
- **Barras de progreso:** rellenadas en verde con animación pulsante cuando llegan a MAX.
- **Backdrop blur:** sutil (~4 px) en modales sobre fondo del juego.

### Layout

- **Asimetría intencional:** paneles flotan en posiciones no alineadas a grid rígido. Da sensación de "interfaz tactical/broadside".
- **Densidad alta de información:** ZZZ no teme mostrar muchos datos a la vez. Aprovechar.
- **Jerarquía por contraste:** el amarillo aparece poco pero contundente; lo importante destaca por color, no por tamaño.

## Cómo usar estas referencias en Claude Design

Cuando entres a [claude.ai/design](https://claude.ai/design) y crees el proyecto:

1. **Sube las 6 capturas** al proyecto como referencias visuales.
2. **Pegá el "Prompt inicial"** del `Brief_Claude_Design.md` (que ahora está actualizado con esta paleta).
3. **Indicale explícitamente:** *"Usa el estilo visual de las 6 capturas adjuntas como referencia. La paleta principal es negro + amarillo `#FFCB05` signature de Zenless Zone Zero. Mantené bordes rectos con cortes diagonales selectivos, paneles semi-transparentes flotantes, y tipografía angular tipo Bahnschrift/Rajdhani."*
4. Refiná pidiendo que cada componente respete la geometría del juego (chamfered corners en toast y botones primarios, hexágono de 6 slots en pestaña Roster, glow amarillo en estados activos).

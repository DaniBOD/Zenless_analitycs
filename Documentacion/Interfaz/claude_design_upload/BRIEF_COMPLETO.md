# DaniBOD ZZZ Analytics — Brief Claude Design (v2 completo)

> Aplicación standalone Windows (`.exe` PySide6) que monitorea **Zenless Zone Zero** en tiempo real
> y muestra recomendaciones de loot, builds y estrategia mientras el jugador juega.
> Usuario único: DaniBOD · 45 PJs · 332 discos · 50 engines.

---

## 1. Sistema visual

| Token | Valor | Uso |
|-------|-------|-----|
| `bg-base` | `#0a0a0a` | Fondo principal |
| `bg-panel` | `rgba(20,20,20,0.92)` | Paneles flotantes |
| `border-subtle` | `#3a3a3a` | Bordes y separadores |
| `text-primary` | `#f5f5f5` | Texto principal |
| `text-secondary` | `#a8a8a8` | Labels |
| **`accent-yellow`** | **`#FFCB05`** | **SIGNATURE** — selección, badges, hover |
| `positive` | `#7BC91F` | Verde lima — Equipar / MAX / OK |
| `warning` | `#FF6B47` | Rojo-naranja — Descartar / Cerrar |
| `info` | `#5BC0EB` | Cyan — Mejorar / info |
| `purple` | `#9D4EDD` | Sinergias IA (RF-12) |
| `pink` | `#FF4D8A` | Retro-feedback bayesiano (RF-13) |

**Tipografía:** Saira / Rajdhani / Bahnschrift — 400 cuerpo · 600 títulos · 700 números grandes · tabular-nums siempre · letter-spacing +0.5px en mayúsculas.

**Geometría:** `border-radius: 14px` en paneles normales · `18px` en paneles hero · bordes 1px sólido · **2px `#FFCB05`** cuando seleccionado.

**Sombras:** `0 4px 16px rgba(0,0,0,0.6)` en paneles · glow amarillo `0 0 12px rgba(255,203,5,0.5)` en activos.

**Hover:** fondo `rgba(255,203,5,0.06)` + transición 200ms ease-out.

**Tema:** oscuro absoluto — sin variante clara.

---

## 2. Assets — carpeta `claude_design_upload/`

Subir todos los archivos de la carpeta junto con este brief.

### Splash arts (5 PJs · 2 versiones c/u)
| Archivo | Uso |
|---------|-----|
| `yanagi-ico.webp` | Avatar cards, listas (32–64px) |
| `yanagi-extend.webp` | Fondos decorativos de modal (full-height) |
| `ellen-ico.webp` / `ellen-extend.webp` | ídem |
| `yixuan-ico.webp` / `yixuan-extend.webp` | ídem |
| `burnice-ico.webp` / `burnice-extend.webp` | ídem |
| `caesar-ico.webp` / `caesar-extend.webp` | ídem |

### Logos de facción (4 facciones)
| Archivo | Facción |
|---------|---------|
| `faction-section6.webp` | Hollow Special Operations Section 6 |
| `faction-victoria.webp` | Victoria Housekeeping |
| `faction-yunkui.webp` | Yunkui Summit |
| `faction-calydon.webp` | Sons of Calydon |

> Cada logo tiene identidad visual única del juego — NO rediseñar ni uniformar estilo.

### Logos de sets de discos (7 sets usados por los 5 PJs)
`set-jazz-caotico.webp` · `set-blues-libre.webp` · `set-puffer-electro.webp` · `set-balada-rama.webp` · `set-fabula-yunkui.webp` · `set-punk-primitivo.webp` · `set-sacudestrellas.webp`

### Logos de engines (1 por PJ)
`engine-llanto-mielgo.webp` · `engine-visitante-altamar.webp` · `engine-caldero-claridad.webp` · `engine-coctelera.webp` · `engine-proyector.webp`

---

## 3. Cinco personajes ejemplo — usar en TODOS los mockups

> **Usar exactamente estos datos. No inventar PJs ni stats.**

| PJ | Elem | Rol | M | Facción | Engine (R) | Set 4pc | Set 2pc |
|----|------|-----|---|---------|------------|---------|---------|
| **Yanagi** | Eléctrico | Anomalía | 0 | Section 6 | Llanto mielgo R1 | Jazz Caótico | Blues Libre |
| **Ellen** | Hielo | Ataque | 0 | Victoria | Visitante altamar R1 | Puffer Electro | Balada rama |
| **Yixuan** | Éter | Disruptivo | 0 | Yunkui | Caldero claridad R1 | Fábula Yunkui | Balada rama |
| **Burnice** | Fuego | Anomalía | 0 | Sons of Calydon | Coctelera R3 | Jazz Caótico | Blues Libre |
| **Caesar** | Físico | Defensa | 2 | Sons of Calydon | Proyector R5 | Punk Primitivo | Sacudestrellas |

### Stats clave por PJ
| PJ | PV | ATK | CR% | CDmg% | Especial |
|----|-----|-----|-----|-------|---------|
| Yanagi | 10,680 | 2,690 | 21.8 | 64.4 | AnomMaestría **329** · ER 1.20 |
| Ellen | 11,248 | 2,667 | **72.2** | **171.6** | Bono Hielo 30% |
| Yixuan | **17,245** | 1,907 | 65.0 | 162.0 | Bono Éter 30% (Sheer DMG escala con HP) |
| Burnice | 10,674 | 2,601 | — | — | AnomMaestría **398** · ER 1.56 · Bono Fuego 30% |
| Caesar | 13,155 | 1,891 | 48.2 | 78.8 | DEF 1,256 · Impact **170** · M2 |

### Paletas de modal por PJ (se usa en modales de detalle individuales)
| PJ | Primario | Secundario | Terciario |
|----|----------|------------|-----------|
| Yanagi | `#1E3A8A` azul | `#7C3AED` violeta | `#0F172A` slate |
| Ellen | `#DC2626` rojo | `#0A0A0A` negro | `#F5F5F5` blanco |
| Yixuan | `#D4AF37` dorado | `#0A0A0A` negro | `#8B6914` dorado oscuro |
| Burnice | `#FF6B47` naranja | `#FFCB05` amarillo | `#7A1F0F` borgoña |
| Caesar | `#FFCB05` amarillo | `#D4AF37` dorado | `#0A0A0A` negro |

> **Regla de paleta en modales:** solo cambia borde/glow del modal, gauges de stats, hexágono de slots, botones primarios y gradiente del header. El fondo sigue siendo `#0a0a0a`.

---

## 4. Arquitectura de la app (3 superficies)

### 4a. Toast flotante (380×116px · always-on-top · esquina inferior derecha)

5 variantes de acción + 3 estados (idle / hover-congelado / expanding-al-panel):

```
┌─────────────────────────────────────────┐
│ [●EQUIPAR]  Tecno Pícido · Slot 4 · 4s ↗│  ← borde/glow por variante
│ ATK% 30.0%  →  [ico] Yanagi M2   87.3 ▲12 │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░ URGENCIA ALTA  [thr 0.75]│
└─────────────────────────────────────────┘
```

| Variante | Color borde/glow | Badge | Timer |
|----------|-----------------|-------|-------|
| 🟢 Equipar | `#7BC91F` verde | EQUIPAR | 4s |
| 🔵 Mejorar | `#5BC0EB` cyan | MEJORAR | 3s |
| 🟡 Reserva | `#FFCB05` amarillo | RESERVA | 5s |
| 🔴 Descartar | `#FF6B47` rojo · 70% opacidad | DESCARTAR | 2s |
| 📊 Lategame | `#9D4EDD` púrpura | RUN | 4s |

**Lategame** (variante distinta): equipo 3 PJs (icos 20px) + estrellas ★★★ + tiempo `1:48` + `DMG 67% Yanagi`.

**Hover:** barra de timer se pausa, opacidad sube a 100%, aparece botón `[↗ PANEL]`.  
**Click:** animación de expansión hacia el panel principal.

---

### 4b. Panel principal (1320×820px)

```
┌─[TitleBar 40px: ⬡ DaniBOD ZZZ Analytics · — □ ✕]──────────────────────────────────────────────────┐
│ [Sidebar]  [Contenido del tab activo — 1264px de ancho]                                           │
│  56px                                                                                             │
│                                                                                                   │
│ [StatusBar 24px: ● MONITOREANDO · SQLITE 18.4 MB · OCR TESSERACT 5.4 ES · CICLO 12/28D · UID…]  │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Sidebar** (56px ancho, vertical, iconos + label 9px):
```
⚡ LIVE      ← tab activo: borde izq 3px #FFCB05 + bg rgba(255,203,5,0.08)
📋 HIST
👥 ROSTER
💿 DISCOS
🤝 EQUIPOS
🏆 LATEGAME
⚔️ ARMAS
📚 CATÁL
⚙️ CONFIG
```

**Hotkey widget** (overlay esquina inf-izquierda, sobre el contenido, 10px from edge):
`F8 CAP` · `F9 PANEL` · `F10 PAUSA` · `F11 RUN` · `CTRL+SHIFT+Z SALIR`  
Fondo `rgba(0,0,0,0.6)` · texto `#6b6b6b` · separadores `|` · font mono 9px.

---

## 5. Especificación de cada pestaña

---

### Tab LIVE — Captura en vivo *(referencia: ya implementada)*

Disco capturado esta sesión. Layout 2 columnas:
- **Izq (480px):** hexágono de 6 slots con el slot nuevo resaltado + carta de disco con main/subs/nivel.
- **Der:** desglose scoring línea a línea + gauge de score vs threshold + sección "Alternativas compatibles" (lista de 4 PJs con score y delta usando los 5 PJs ejemplo).

**Ejemplo de alternativas compatibles:**
```
Yanagi M0   87.3  ▲ 0.0   ⭐ MEJOR   [badge ANOMALY]
Burnice M0  81.4  ▲-5.9              [badge ANOMALY]
Ellen M0    64.8  ▲-22.5             [badge ATK_DPS]
Caesar M2   41.7  ▲-45.6             [badge DEFENSE]
```

---

### Tab HIST — Histórico de evaluaciones

Tabla paginada de todas las evaluaciones registradas. Filtros sticky encima:
`Set` · `Slot` · `Acción` · `PJ asignado` · `Rango de fechas` · `Ciclo`

**Columnas:**
`#ID` · `Set (logo 16px)` · `Sl` · `Main` · `Score` · `Acción (badge color)` · `PJ asignado (ico 16px + nombre)` · `Fecha` · `Ciclo`

Click en fila → abre modal "Detalle evaluación" (mismo layout que LIVE pero read-only, con label "HISTÓRICO").

---

### Tab ROSTER — Los 45 agentes

**Grid de cards** (5 columnas × 9 filas ≈ 140×90px c/u):

```
┌─[faction-logo 16px]─────────[engine-logo 16px]─┐
│  [splash-ico 56px]  YANAGI                      │
│                     M0 · Eléctrico · Anomalía   │
│  ▓▓▓▓▓▓▓▓▓░░  82% build  [color del elemento]  │
└─────────────────────────────────────────────────┘
```

Filtros encima: `Elemento` · `Rol` · `Facción` · `Build` (✅ / 🟡 / 🔴)

**Modal de detalle PJ** (1000×640px · backdrop blur 4px):
- **Header con paleta del PJ:** gradiente del color primario → `#0a0a0a` + `yanagi-extend.webp` en baja opacidad como fondo decorativo.
- Splash ico 96×96 + nombre grande + `M0` badge + rol / elem / facción (con logo 20px).
- Stats 2 columnas con gauges coloreados con paleta del PJ (barra horizontal, línea threshold amarilla).
- Hexágono interactivo 6 slots con logos de sets en cada slot (círculos con `set-*.webp` 32px).
- Awakening: nivel indicador + texto (Burnice: "Boiling Point Party nv6").
- Botones pie: `OPTIMIZAR BUILD` · `OPTIMIZAR ARMA` · `SUGERIR EQUIPO` · `VER RUNS` (todos con paleta del PJ).

---

### Tab DISCOS — Inventario completo (332 discos)

**Filtros sticky (horizontal, 1 línea):**
`Set ▾` · `Slot 1-6` · `Main ▾` · `Score ─●─` · `Asignado a ▾` · `Estado ▾` · `🔍 #ID`
Toggle vista derecha: `☰ Tabla` · `▦ Grid`

**Vista tabla** (default):
```
#ID    | Set          | Sl | Main stat    | Top subs         | Nv | Score | Asignado a   |
-------|--------------|----|--------------|-----------------|----|-------|--------------|
00482  | 🎵Jazz Caót  | 4  | ATK% 30.0%   | CR ×3  DC ×2    | 15 | 87.3S | [ico]Yanagi  |
00471  | ❄️Polar Met  | 5  | DMG Eléc 30% | CR ×2  ATK% ×1  |  9 | 76.8S | [ico]Burnice |
00465  | 🎵Jazz Caót  | 6  | Maestría Anom| Anom×2 ATK×1    |  3 | 62.4A | sin asignar  |
00463  | 🌀Caos Gas   | 2  | DEF% 20%     | DEF×2  HP×1     | 15 | 23.1C | — descartado |
```
Clic en fila resalta con borde amarillo. Doble-clic abre modal.

**Vista grid:** cards 140×185px por disco. Logo set 48px centrado + slot badge + main stat grande + 4 subs pequeñas + score badge esquina.

**Modal de disco** (1100×700px · 3 columnas):

```
┌─── Col A: DISCO ─────────────────┬─── Col B: PJs COMPATIBLES ──────┬─── Col C: VALOR FUTURO ──────┐
│ [set-jazz-caotico.webp 64px]      │ Rankeados por score:             │ Arquetipo: ANOMALY           │
│ Jazz Caótico · Slot 4 · Nv 15    │                                  │                              │
│                                  │ [yanagi-ico] Yanagi  87.3 ▲12   │ Score proyectado:            │
│ ── MAIN ──                        │   [Equipar] [Comparar]          │  Nv actual (15): 87.3        │
│ ATK%  30.0%                       │                                  │  Este disco ya está en MAX   │
│                                  │ [burnice-ico] Burnice 81.4 ▲9   │                              │
│ ── SUBSTATS ──                    │ [ellen-ico]   Ellen   64.8 ▲-23 │ Match set 4pc:               │
│ Prob. Crítica  2.4% [▓▓▓ ×3]     │ [caesar-ico]  Caesar  41.7 ▲-46 │  Jazz Caótico → ANOMALY S+  │
│ Daño Crítico   9.6% [▓▓ ×2]      │                                  │                              │
│ Ataque         38   [▓ ×1]       │ ── ALTERNATIVAS EN INVENTARIO ──│ Recomendación final:         │
│ Maestría Anom  27   [▓▓ ×2]      │ Otros Slot 4 Jazz Caótico:      │  ⭐ MANTENER · ya óptimo    │
│                                  │  #00521: score 79 (inferior)    │  para Yanagi y Burnice       │
│ ── EFECTOS SET ──                 │  #00638: score 84 (cercano)     │                              │
│ 2pc: ATK +10%                    │                                  │                              │
│ 4pc: …(descripción)              │ [ Solo PJs con slot libre ]     │                              │
└──────────────────────────────────┴─────────────────────────────────┴──────────────────────────────┘
     [BLOQUEAR]    [DESCARTAR]    [REASIGNAR PJ ▾]    [MEJORAR +N]    [CERRAR]
```

---

### Tab EQUIPOS — RF-12

**Sub-tabs internos:** `MATRIZ` · `TOP-N` · `🧠 IA`

#### MATRIZ (45×45 triángulo superior)
Heatmap de pares. Scroll horizontal + vertical. Cabeceras: nombres de PJs en 9px rotados 45°.

Colores de celda por confianza:
- 🟢 `rgba(123,201,31,0.9)` ≥ 0.85 — sinergia fuerte
- 🟩 `rgba(123,201,31,0.45)` 0.70–0.84 — sinergia confirmada
- ⬜ `rgba(255,255,255,0.08)` 0.40–0.69 — sinergia débil
- ⬛ vacío — sin datos / sin sinergia

Hover celda → tooltip: `Yanagi + Burnice · tipo: disorder_element · confianza 0.91 · "Anomalía eléctrico+fuego genera Disorder x2.4 DMG"`.  
Click celda → modal de par (2 avatares 64px lado a lado + stats sinergia + historial de runs).

#### TOP-N (composiciones por PJ)
Selector `Para [Yanagi ▾]` + `Contenido [Shiyu ▾]` → lista de top-5 composiciones de 3 PJs.

```
[yanagi-ico 64px]  +  [burnice-ico 64px]  +  [caesar-ico 64px]
SCORE CONJUNTO: 94.1 · Disorder · Def+Shield
▸ Justificación: Anomalía eléctrico+fuego → Disorder. Caesar provee…
[± RF-13 calibrado · 3 runs]
```

#### 🧠 IA Insights
```
┌── Gauge gasto mensual ─────────┐ ┌── Tabla catalogaciones recientes ──────────────────────────────────────────┐
│   $3.42                        │ │ Operación        │ Modelo          │ Tokens (cached+out) │ Costo │ Fecha   │
│   ────── de $5.00 cap ─────── │ │ Yanagi+Burnice   │ claude-sonnet   │ 2840+180            │$0.009 │ 02-may  │
│   [▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░] 68%   │ │ Ellen+Lycaon     │ claude-sonnet   │ 3100+210            │$0.010 │ 01-may  │
│   💡 32% disponible           │ │ …                │ …               │ …                   │ …     │ …       │
└────────────────────────────────┘ └────────────────────────────────────────────────────────────────────────────┘
┌── Queue pendiente ─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 44 pares pendientes para catalogar  ·  ETA estimado: 12 min  ·  [PAUSAR QUEUE]  [RECATALOGAR PAR…]  [VACIAR]   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Tab LATEGAME — RF-13

**Sub-tabs:** `RUNS` · `TIER LIST` · `VS PRYDWEN` · `HISTORIAL` · `CICLOS`

#### RUNS (tabla cronológica)
Cols: `Fecha` · `Contenido` · `Equipo (3 icos 20px)` · `★★★` · `Tiempo` · `DMG% PJ principal`

Ejemplo:
```
02-may  Deadly Assault Nodo 3   [yan][bur][cae]  ★★★  1:48   67% Yanagi
01-may  Shiyu Defense F12       [yan][bur][lyc]  ★★★  —      —
```

#### TIER LIST PERSONAL
Columnas S+ / S / A / B / C / D con cards de PJ (ico 48px + nombre):
```
S+: [miyabi] [ellen] [yixuan]
S:  [yanagi] [burnice] [caesar] [ye-shunguang]
A:  [lycaon] [qingyi] [evelyn] …
```
Read-only. Cada card muestra badge con cuenta de runs `×3`.

#### VS PRYDWEN
```
PJ       | Prydwen   | Personal  | Delta     | Runs
---------|-----------|-----------|-----------|-----
Yanagi   | S         | S         | =         | 3
Miyabi   | S+        | S+        | =         | 1
Burnice  | S         | S+        | 🟢 ▲1    | 5
Ellen    | S+        | S         | 🔴 ▼1    | 2
```

#### HISTORIAL
Gráfico de líneas (eje X: ciclos/tiempo · eje Y: tier S+/S/A/B/C/D). Toggle checkboxes para mostrar/ocultar cada PJ. Líneas coloreadas por elemento del PJ.

#### CICLOS
Cards por ciclo. Cada card: nombre ciclo + bosses + tus mejores resultados del ciclo.

---

### Tab ARMAS — RF-14

**Sub-tabs:** `RANKING PJ` · `BUILD FULL` · `CATÁLOGO` · `VS PRYDWEN`

#### RANKING PJ
Selector `PJ [Yanagi ▾]` + `Contenido [Shiyu ▾]` → tabla top-5 engines:
```
Rk | Engine                    | Logo              | Tier pers | Tier Pry | Score | R actual
---|---------------------------|-------------------|-----------|----------|-------|--------
1  | Llanto Mielgo             | [engine-ico 24px] | S+        | S+       | 94.2  | R1 (equipado)
2  | Compilador Quimérico      |                   | S         | S        | 88.7  | —
3  | Fusión + …                |                   | A         | S        | 79.3  | —
```

#### BUILD FULL
Selector PJ + Contenido → top-3 combinaciones arma + 6 discos:

```
[engine-ico 48px]  +  [hexágono 6 slots con logos de set]  =  Score 94.1
Llanto Mielgo R1        Jazz Caótico ×4 + Blues Libre ×2       ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░ (engine 38% | discos 62%)
```

#### CATÁLOGO (53 engines)
Grid o tabla. Por engine: logo 32px + nombre + `pasiva_tipo` + badge modelado (`🟢 completa / 🟠 parcial / 🔴 sin modelar`).

#### VS PRYDWEN
Mismo formato que LATEGAME > VS PRYDWEN pero para engines:
```
Engine             | Contenido  | Prydwen  | Personal | Delta
-------------------|------------|----------|----------|------
Llanto Mielgo      | Shiyu      | S+       | S+       | =
Fosil Preciado     | DA         | S+       | S+       | =
Fosil Preciado     | HZ         | S        | B        | 🔴 ▼2
```

---

### Tab CATÁL — Catálogos

3 secciones colapsables (acordeón con SectionHead):

**ARQUETIPOS (6)** — cada uno: nombre + descripción de 1 línea + pesos como barras horizontales:
```
ATK_DPS       ████████░░  ATK% 25  ██████░░░░  CR% 20  ████████░░  CDmg% 30  …
HP_DISRUPT    ██████████  HP%  30  ████░░░░░░  Impact 15  …
ANOMALY       …
STUN          …
SUPPORT_ER    …
DEFENSE       …
```

**SETS CLASIFICADOS (26)** — tabla: logo 20px · nombre · arquetipo primario (badge) · secundario (badge) · nº discos en inventario.

**SUBSTAT PREFERENCES (45 PJs)** — tabla editable inline:
```
PJ (ico 24px + nombre) | ATK% | CR% | CDmg% | AnomM | ER% | (suma = 100)
[yanagi-ico] Yanagi    |  20  |  25 |   30  |  20   |  5  |
[burnice-ico] Burnice  |  15  |  10 |   10  |  40   | 25  |
```
Inputs numéricos inline. Save on blur.

---

### Tab CONFIG — Configuración

Form vertical con `SectionHead` por bloque:

**THRESHOLDS GLOBALES**
- Equipar (default 0.75) — slider 0.0–1.0
- Reserva (default 0.50) — slider 0.0–1.0

**NOTIFICACIONES**
- Modo toast: radio (Accionables solamente / Todas / Silencioso)
- Duración auto-fade: slider 1–10s (default 5s)

**HOTKEYS** — tabla 5 filas:
```
F8   → Capturar disco     [Editar]
F9   → Abrir/cerrar panel [Editar]
F10  → Pausar captura     [Editar]
F11  → Registrar run      [Editar]
Ctrl+Shift+Z → Salir      [Editar]
```

**IA (RF-12)**
- Cap mensual USD: input numérico (default $5.00)
- Prompt caching: toggle ON/OFF

**OCR**
- Backend: radio (Tesseract / PaddleOCR)
- Botón `[CALIBRAR ROIs]` → lanza wizard de calibración

**SISTEMA**
- Autostart con Windows: toggle (default OFF)
- Carpeta DB: ruta + botón `[CAMBIAR]`

---

### Wizard primera ejecución (modal 600×450px · stepper 3 pasos)

Pasos con barra de progreso superior `─●────────`:

**Paso 1 — Carpeta DB**
File-picker para seleccionar `danibod_zzz_v2.db`. Muestra preview: tablas encontradas + nº de filas.

**Paso 2 — Calibrar ROIs OCR**
Captura de pantalla del juego (placeholder abstracto). Instrucción: "Dibuja un rectángulo alrededor de cada zona de texto en la pantalla de discos". Zonas: Set · Slot · Main stat · Sub 1-4.

**Paso 3 — Verificar Hotkeys**
Tabla de 5 hotkeys. Detector de conflictos (badge 🟢 libre / 🔴 conflicto). Botón `[FINALIZAR SETUP]`.

---

### Tray icon (menú contextual sistema)

Menú flotante estilo ZZZ, 200×160px, posición esquina inferior derecha sobre la barra de tareas:
```
┌────────────────────────────┐
│ ⬡ DaniBOD ZZZ Analytics   │  ← cabecera, no clickeable
│ ● MONITOREANDO             │
├────────────────────────────┤
│   ▶  Abrir panel           │
│   ⏸  Pausar captura        │
├────────────────────────────┤
│   ⚙  Configuración         │
│   ✕  Salir                 │
└────────────────────────────┘
```

---

## 6. Flujo de navegación entre pantallas

```
Toast (5 variantes)
  └─ click → Panel · Tab LIVE (disco expandido en contexto)
  └─ hover → congela timer · aparece [↗ PANEL]

Tab LIVE
  └─ click alternativa PJ → Modal PJ (con paleta del PJ)
  └─ click "Ver en Discos" → Tab DISCOS filtrado por ese disco

Tab ROSTER · card PJ
  └─ click → Modal PJ
       └─ [OPTIMIZAR BUILD] → Tab DISCOS (filtrado por PJ)
       └─ [SUGERIR EQUIPO]  → Tab EQUIPOS > TOP-N (PJ pre-seleccionado)
       └─ [OPTIMIZAR ARMA]  → Tab ARMAS > RANKING PJ (PJ pre-seleccionado)
       └─ [VER RUNS]        → Tab LATEGAME > RUNS (filtrado por PJ)

Tab DISCOS · modal disco
  └─ [REASIGNAR PJ] → selector inline → dispara recálculo de score
  └─ click PJ compatible → Modal PJ

Tab EQUIPOS · MATRIZ
  └─ click celda → Modal par (2 PJs + stats de sinergia)

Tab EQUIPOS · TOP-N
  └─ click composición → detalle expandido con justificación completa

Tab LATEGAME · TIER LIST
  └─ click card PJ → Modal PJ

Tab ARMAS · RANKING PJ
  └─ click row engine → Modal engine (pasiva estructurada + contextos de uso)

Tab ARMAS · BUILD FULL
  └─ click combo → expansión inline con detalle de cada disco del set
```

---

## 7. Datos de disco de ejemplo (para todos los mockups)

**Disco #00482** — estrella de los ejemplos (aparece en LIVE, DISCOS, Toast EQUIPAR):
- Set: Jazz Caótico · Slot 4 · Main: ATK% 30.0% · Nivel **15** · Score **87.3 (S)**
- Substats: Prob. Crítica 2.4% (×3 rolls) · Daño Crítico 9.6% (×2) · ATK 38 (×1) · Maestría Anomalía 27 (×2)
- Asignado a: Yanagi · Estado: equipado

**Disco #00471** — ejemplo de Mejorar:
- Set: Polar Metal · Slot 5 · Main: DMG Eléctrico 30% · Nivel **9** · Score **76.8 (S)**
- Substats: Prob. Crítica 5.6% (×2) · ATK% 9% (×1) · HP 806 (×1)
- Asignado a: Burnice · Estado: equipado

**Disco #00465** — ejemplo de Reserva:
- Set: Jazz Caótico · Slot 6 · Main: Maestría Anomalía 32 · Nivel **3** · Score **62.4 (A)**
- Substats: Tasa Anomalía 8% (×2) · ATK 38 (×1) · Prob. Crítica 1.2% (×1)
- Estado: suelto, sin asignar

---

## 8. Orden de generación sugerido

Generar en este orden (cada pantalla como artboard separado en el canvas):

1. **Toast × 5 variantes** (380×116px) + 3 estados (hover, expanding, fade)
2. **Toast in-situ** (1280×720px — toast flotando sobre gameplay abstracto)
3. **Panel · Tab LIVE** (1320×820px)
4. **Panel · Tab DISCOS** (1320×820px) — vista tabla + modal disco 3-col
5. **Panel · Tab ROSTER** (1320×820px) — grid + modal PJ (Yanagi, paleta azul)
6. **Panel · Tab EQUIPOS** (1320×820px) — sub-tabs Matriz + TOP-N + IA
7. **Panel · Tab LATEGAME** (1320×820px) — sub-tabs Runs + Tier List + vs Prydwen
8. **Panel · Tab ARMAS** (1320×820px) — sub-tabs Ranking + Build Full + Catálogo
9. **Panel · Tab HIST** (1320×820px)
10. **Panel · Tab CATÁL** (1320×820px)
11. **Panel · Tab CONFIG** (1320×820px) + Wizard 3 pasos (600×450px)
12. **Tray menu** (200×160px)

# DaniBOD ZZZ Analytics — Brief Claude Design (Sesión 2)

> **Pantallas restantes para completar el set de mockups** del standalone Windows (`.exe` PySide6).
> Sesión 1 cerró el sistema de toasts + pestaña LIVE + pestaña DISCOS + 5 modales de PJ.
> Esta sesión cierra: ROSTER, HIST, EQUIPOS, LATEGAME, ARMAS, CATÁL, CONFIG + Wizard, Tray.
>
> **Orden recomendado al subir a Claude Design:** este archivo + `BRIEF_COMPLETO.md` (referencia) + `Codigos-claude-desing/` completo (archivos jsx + tokens.css + assets/) + carpetas de logos (`Set_Discos_Logo/`, `Engines_icons/`, `Facciones_Logos/`, `splash_arts/`).

---

## 0. Contexto rápido — leer primero

- **No es una web app.** Es una aplicación standalone Windows (PySide6, distribuida como `.exe`). Los mockups generados en HTML/JSX **son contrato visual** — guían la implementación nativa pero no son la app real. Las animaciones/interacciones avanzadas se traducirán a Qt; lo importante es la composición, jerarquía, paleta y estados.
- **Usuario único** (DaniBOD): 45 PJs, 332 discos, ~50 W-Engines.
- **Tres superficies:** Tray icon · Toast flotante (380×116) · Panel principal (1320×820).
- **Latencia percibida < 500 ms** desde evento en juego hasta toast en escritorio. Diseñar pensando en información densa pero escaneable de un vistazo.
- **Tema único:** dark absoluto. No hacer variante clara.

---

## 1. Estado actual — qué quedó hecho en sesión 1 (NO regenerar)

### Archivos ya entregados en `Codigos-claude-desing/`

| Archivo | Contenido | Reutilización en sesión 2 |
|---------|-----------|--------------------------|
| `tokens.css` | Paleta, fuentes, sombras, glows, chamfers, patrón carbon-fiber | **No tocar** — extender solo si surge color nuevo |
| `design-canvas.jsx` | Wrapper Figma-ish con `<DesignCanvas>` / `<DCSection>` / `<DCArtboard>` / `<DCPostIt>` | **Usar tal cual** para nuevas secciones |
| `components.jsx` | Primitivos: `BlockBox`, `ChamferBox`, `Hexagon6`, `DiscSlot`, `DiscMark`, `ZButton`, `StatRow`, `ScoreGauge`, `Tag`, `Rarity`, `KPI`, `SectionHead`, `Icon` (30 SVG line-icons) | **Componer con esto antes de crear nada nuevo** |
| `data.jsx` | `PJS` (5), `SETS` (7), `DISCS` (24) en `window.*` | **Extender** — agregar más PJs/discos/runs/parejas según pestaña |
| `toasts.jsx` | `Toast` (5 variantes × 3 estados) | Cerrado |
| `panel.jsx` | `AppWindow` con TitleBar + Sidebar 9 pestañas + StatusBar + `LiveCaptureTab` (Disco/Scoring/Alternativas) | **Sidebar ya existe** — solo intercambiar contenido por tab activo |
| `discs-tab.jsx` | `DiscsTab` (FiltersBar + DiscsTable + DiscsSidebar con distribución y RF-12 insight) | Cerrado |
| `disc-modal.jsx` | `DiscModal` 1100×700 a 3 columnas | Cerrado |
| `pj-modal.jsx` | `PjModal` con paleta dinámica por PJ — 5 ejemplos: Yanagi, Ellen, Yixuan, Burnice, Caesar | Plantilla — los 40 PJs restantes son contenido |
| `agent-card.jsx` | `AgentStatsCard`, `FactionBadge`, `ReelAvatar` (info-panel estilo in-game) — **NO está incluido en el HTML actual** | **Recuperar y wirear en Tab ROSTER** |

### Pantallas verificadas en screenshots

`Toast-en-escritorio-contexto-real.png` · `Toast-en-escritorio-contexto-real-2.png` · `Toast-estados.png` · `equipar-card.png` · `mejorar-card.png` · `reserva_card.png` · `descartar-card.png` · `Run-lategame-card.png` · `Panel-principal.png` · `Inventario-discos-completo.png` · `modal-disco-detalle.png` · `Modal-PJ-{Yanagi,Ellen,Yixuan,Burnice,Caesar}.png`

### Convenciones consolidadas — respetar en sesión 2

- **Ventana del panel:** `1320×820` siempre. Sidebar `220` izquierda + contenido `1100` derecha + StatusBar `~28` abajo. TitleBar `~40` arriba.
- **Sidebar grupos:** MONITOREO (live, history, lateg) · BUILD (discs, roster, weapons, teams) · SISTEMA (catal, config). El bloque inferior con HOTKEYS ya está fijo.
- **Tipografía:** `Saira` cuerpo · `Saira Condensed` displays · `JetBrains Mono` IDs/scores. Tabular-nums siempre que aparezca un número.
- **Geometría:** `border-radius: 14px` paneles, `18px` heroes; chamfer `tl-br` para tarjetas grandes; `clip-path` ya está definido en tokens.css.
- **Color signature `#FFCB05`:** se usa para selección, números S-tier, gauges activos, focus ring. NO inundar la pantalla — solo destacar lo que el usuario debe mirar primero.
- **Acciones por color:** verde `#7BC91F` = positiva (equipar/MAX) · cyan `#5BC0EB` = info/mejorar · naranja `#FF6B47` = warning/descartar · violeta `#9D4EDD` = sinergias IA · rosa `#FF4D8A` = retro RF-13.
- **Patrón "datos densos pero escaneables":** tablas con filas `28–32px`, fuentes `10–11px` para datos secundarios, números importantes a `14–18px` con peso 700.

---

## 2. Pantallas pendientes — orden de prioridad

| # | Pantalla | Tamaño | Prioridad | Notas |
|---|----------|--------|-----------|-------|
| 1 | **Tab ROSTER · grid 45 cards** | 1320×820 | ALTA | Wirear `agent-card.jsx`. Cierra el flujo Roster → Modal-PJ. |
| 2 | **Tab HIST · histórico de evaluaciones** | 1320×820 | ALTA | Patrón "tabla densa" similar a DISCOS — reusar primitivos. |
| 3 | **Tab EQUIPOS · 3 sub-vistas** | 1320×820 | ALTA | MATRIZ 45×45 + TOP-N + 🧠 IA Insights (RF-12). |
| 4 | **Tab LATEGAME · 5 sub-vistas** | 1320×820 | MEDIA | Runs · Tier List · vs Prydwen · Histórico · Ciclos (RF-13). |
| 5 | **Tab ARMAS · 4 sub-vistas** | 1320×820 | MEDIA | Ranking · Build Full · Catálogo · vs Prydwen (RF-14). |
| 6 | **Tab CATÁL · 3 secciones** | 1320×820 | MEDIA | Arquetipos · Sets clasificados · Substat preferences (editable). |
| 7 | **Tab CONFIG + Wizard 3 pasos** | 1320×820 + 600×450 | MEDIA | Form vertical + wizard onboarding. |
| 8 | **Tray menu** | 200×160 | BAJA | Menú contextual de system tray. |
| 9 | **Modales PJ adicionales** (opcional) | 1000×640 c/u | BAJA | Solo si sobra capacidad — el sistema de paleta ya quedó probado con 5. |

---

## 3. Especificación detallada de las pantallas pendientes

### 3.1 — Tab ROSTER · grid 45 cards

**Layout** (1100 ancho dentro del Panel, sin contar Sidebar):
- **Filtros sticky arriba** (1 línea, mismo patrón que DISCOS): `Elemento ▾` · `Rol ▾` · `Facción ▾` · `Estado build` (chips: ✅ ≥85% / 🟡 60–84% / 🔴 <60%) · `🔍 nombre`. Toggle vista derecha: `▦ GRID` (default) · `☰ TABLA`.
- **Grid 5×9 = 45 cards** (`~200×130 px` cada una con gap 10px). Vertical scroll si baja ≥10 filas.

**Card de PJ** (extender `AgentStatsCard` de `agent-card.jsx`, versión compacta):
```
┌─[faction-logo 18px]──────────────[engine-logo 18px R3]──┐
│  [ico 56px  YANAGI · M0                                  │
│   redondo]  Eléctrico · Anomalía                         │
│             Section 6                                    │
│             ▓▓▓▓▓▓▓▓▓░ 87% build                         │
└──────────────────────────────────────────────────────────┘
```

Detalles:
- Card al hover: `box-shadow` glow de color del elemento del PJ + scale 1.02. Click → abre `PjModal`.
- Borde `1px var(--border-mid)` default; si build ≥ 85%, bordeg lima `var(--positive)`; si engine no equipado, badge naranja "ENGINE FALTA".
- Foto: `splash_arts/{slug}-ico.webp`. Si no existe, fallback al primer carácter del nombre en círculo amarillo.
- Nombre en `display caps` 14px peso 700; mindscape como pill negro/amarillo `M{0..6}`.
- Línea `Eléctrico · Anomalía` con `ElementGlyph` 12px + texto 10px.
- Barra `build %` 4px alto, color del elemento, fondo `rgba(255,255,255,0.06)`. Tooltip en hover muestra desglose: discos 6/6 · engine 1/1 · awakening n/6.

**Datos canónicos para el grid (45 PJs):** ya están los 5 ejemplo + extender en `data.jsx` con los 40 restantes. Para esta sesión basta nombrar **15 PJs adicionales** representativos para variedad visual:

| Nombre | Elem | Rol | M | Facción | Build% |
|--------|------|-----|---|---------|--------|
| Miyabi | Hielo | Anomalía | 0 | Section 6 | 96 |
| Lycaon | Hielo | Aturdidor | 0 | Victoria | 88 |
| Qingyi | Eléctrico | Aturdidor | 0 | CISRT | 84 |
| Evelyn | Fuego | DPS | 0 | Mountain Stronghold | 79 |
| Vivian | Éter | Anomalía | 0 | Mountain Stronghold | 73 |
| Astra Yao | Éter | Soporte | 0 | Stars of Lyra | 81 |
| Soldier 11 | Fuego | DPS | 0 | Section 6 | 67 |
| Zhu Yuan | Éter | DPS | 0 | CISRT | 72 |
| Jane Doe | Físico | Anomalía | 0 | CISRT | 76 |
| Harumasa | Eléctrico | DPS | 0 | Section 6 | 69 |
| Lighter | Fuego | Aturdidor | 0 | Mountain Stronghold | 64 |
| Pulchra | Físico | Anomalía | 0 | Sons of Calydon | 58 |
| Soukaku | Hielo | Soporte | 0 | Hares Conejas | 51 |
| Anby | Eléctrico | Aturdidor | 0 | Cunning Hares | 48 |
| Nicole | Éter | Soporte | 0 | Cunning Hares | 42 |

> El grid debe mostrar **mezcla de estados** (algunos ✅ verdes, mayoría amarillos, 2-3 rojos) para que se vea funcional el filtro `Estado build`.

**Modal de PJ:** ya generado para los 5 ejemplo. Para sesión 2 generar 1–2 modales nuevos para validar que el sistema de paleta funciona en otros elementos: **Miyabi (Hielo · blanco-celeste + dorado)** y **Astra Yao (Éter · lavanda + dorado pastel)**.

---

### 3.2 — Tab HIST · histórico de evaluaciones (RF-04)

Patrón "tabla + sidebar" idéntico al de DISCOS. Reusar `DiscsTable`/`DiscsSidebar` como base.

**Filtros sticky:**
`Set ▾` · `Slot 1-6` · `Acción ▾` (Equipar/Mejorar/Reserva/Descartar) · `PJ asignado ▾` · `Rango fechas` (date-picker `desde — hasta`) · `Ciclo ▾` (Shiyu C12, DA C8, etc.).

**Tabla — columnas (10):**
`#ID` · `Set (logo 16px + nombre)` · `Sl` · `Main` · `Score (con badge tier)` · `Acción (badge color)` · `PJ asignado (ico 18px + nombre · M)` · `Fecha (DD MMM HH:mm)` · `Ciclo` · `RF` (badge: 04 / 05 / 06).

Filas `28px`. Hover `bg-row-hover`. Click → modal "Detalle evaluación" (mismo layout que `LiveCaptureTab` pero **read-only**, con header que diga `📋 HISTÓRICO · captura del 02 may 14:33` y sin botones de acción al pie).

**Sidebar derecho (240px):** 3 cards apiladas:
- **"Distribución por acción"** — 4 mini-barras horizontales (verde/cyan/amarillo/naranja) con conteos.
- **"Top 5 PJs receptores"** — lista con ico + nombre + #evaluaciones recibidas en el filtro actual.
- **"Estadísticas del filtro"** — KPIs `score promedio`, `% S-tier`, `% acciones positivas`, `discos únicos vs evaluaciones`.

**Footer:** `1—50 de 1.247 · ordenado por Fecha ↓` + paginación `◀ 1 2 3 … 25 ▶` + botón `[EXPORTAR CSV]` a la derecha.

---

### 3.3 — Tab EQUIPOS · 3 sub-vistas (RF-12)

**Sub-tab nav** dentro del contenido (encima del scroll, no en el sidebar global):
```
┌─ MATRIZ DE PARES ─┬─ TOP-N COMPOSICIONES ─┬─ 🧠 IA INSIGHTS ─┐
```
Sub-tab activo con underline amarillo + bg `rgba(255,203,5,0.06)`.

#### A. MATRIZ (45×45 triángulo superior)

Heatmap denso. Cabeceras: nombres de PJs en `font-display 9px caps` rotados `-45°`, eje X arriba, eje Y izquierda. Diagonal en gris (mismo PJ).

**Colores celda según `confianza_sinergia ∈ [0..1]`:**
- ≥ 0.85 → `rgba(123,201,31,0.9)` verde lleno + glow positive
- 0.70–0.84 → `rgba(123,201,31,0.45)` verde tenue
- 0.40–0.69 → `rgba(255,255,255,0.08)` gris muy claro
- < 0.40 o sin datos → vacío (background base)
- **AI catalogada** → tick `✓` violeta `#9D4EDD` 8px en esquina celda

**Hover celda** → tooltip flotante `200×120 px`:
```
[yan-ico 24px] Yanagi  +  [bur-ico 24px] Burnice
─────────────────────────────────
Tipo: disorder_element   Confianza: 0.91
"Anomalía eléctrico+fuego genera Disorder con DMG ×2.4"
─────────────────────────────────
RF-12 IA · catalogado 28 abr · 3 runs validan
```

**Click celda** → modal de par 700×440px: 2 avatares 80px + stats sinergia detallados + historial de runs en los que aparecieron juntos + botón `[CATALOGAR DE NUEVO]`.

**Toolbar de filtro encima:** `Solo S-tier` toggle · `Solo catalogados IA` toggle · `Por contenido [Shiyu / DA / general]` selector · `[VER MAPA COMPLETO]` botón que abre el modal en tamaño grande.

#### B. TOP-N (composiciones por PJ)

```
PARA  [yanagi-ico] Yanagi ▾    EN  [Shiyu Critical ▾]    [BUSCAR]
```

Lista de **top 5 composiciones de 3 PJs**, cada una en card horizontal `1080×140 px`:

```
┌─────────────────────────────────────────────────────────────────┐
│ [yan 64] + [bur 64] + [cae 64]   SCORE 94.1   RF-13 ± 3 runs    │
│                                  ⭐ Disorder · Def+Shield        │
│ ▸ Anomalía eléctrico+fuego → Disorder. Caesar provee shield…    │
│ DPS 67% Yanagi · 24% Burnice · 9% Caesar                        │
│ [VER DETALLE]  [SIMULAR EN DA]  [GUARDAR FAVORITO]              │
└─────────────────────────────────────────────────────────────────┘
```

#### C. 🧠 IA Insights (RF-12)

Layout en 2 filas:

**Fila 1 — KPIs + queue (`flex` 3 columnas):**

Columna A (`gauge gasto mensual` 360×180):
- Donut `$3.42 / $5.00` con relleno violeta · 68% · etiqueta "32% disponible".
- Debajo: 4 mini-stats `tokens entrada` · `tokens salida` · `cache hits %` · `costo/hr promedio`.

Columna B (`tabla catalogaciones recientes` 460×180, scrollable):
| Operación | Modelo | Tokens (cache + out) | Costo | Fecha |
|-----------|--------|---------------------|-------|-------|
| Yanagi+Burnice | claude-sonnet-4-6 | 2 840 + 180 | $0.009 | 02 may 14:31 |
| Ellen+Lycaon | claude-sonnet-4-6 | 3 100 + 210 | $0.010 | 01 may 09:14 |
| Vivian+Astra | claude-haiku-4-5 | 1 920 + 95 | $0.002 | 30 abr 22:08 |

Columna C (`queue + acciones` 240×180):
- Card violeta: `44 pares pendientes para Lyra (PJ nuevo)` + ETA `~12 min`.
- Botones apilados: `[PAUSAR QUEUE]` · `[RECATALOGAR PAR…]` · `[INVALIDAR CACHE]` · `[VACIAR PENDIENTES]`.

**Fila 2 — Estadísticas globales (`grid` 4 KPIs + gráfico de costo diario):**

KPIs: `Pares totales` `990` · `Catalogados IA` `847 (85,6%)` · `Con sinergia` `412` · `Sin sinergia` `435`.

Gráfico de líneas debajo (1080×180 px): costo diario últimos 30 días, eje Y en `$`, línea violeta + área tinte. Banda horizontal punteada en `$0.17/día` (proyección al cap mensual). Tooltip por punto.

---

### 3.4 — Tab LATEGAME · 5 sub-vistas (RF-13)

**Sub-tab nav:** `RUNS RECIENTES` · `TIER LIST PERSONAL` · `VS PRYDWEN` · `HISTÓRICO` · `CICLOS`.

#### A. RUNS RECIENTES

Tabla cronológica `1080 × scroll`, columnas:
`Fecha (DD MMM HH:mm)` · `Contenido` (badge pintado: cyan Shiyu / rosa DA / gris HZ) · `Equipo (3 icos 24px)` · `★★★` · `Tiempo` (`mm:ss`, verde si récord personal) · `DMG % PJ principal` · `Δ vs promedio` (verde/rojo).

Sidebar derecho (240px): 3 cards con KPIs `runs últimos 7 días`, `mejor tiempo del ciclo actual`, `PJ con mayor DPS share global`. Botón `[+ REGISTRAR RUN MANUAL]` arriba a la derecha.

#### B. TIER LIST PERSONAL

6 columnas verticales `S+ / S / A / B / C / D` (cada una `~170 px ancho`). Columna S+ con borde glow amarillo. Cada PJ es una card `150×80 px`:
```
┌─────────────────────┐
│ [miyabi 32]  M0     │
│ Miyabi  ❄️           │
│ score 96.1  ×7 runs │
└─────────────────────┘
```

**Filtro encima:** `Por contenido [Shiyu / DA / HZ / general]`. Toggle `[ ] Mostrar solo PJs con ≥3 runs`.

Click card → modal "Detalle de tier" (700×400 px) con: score normalizado · métricas (`runs`, `win_rate`, `rate_3★`, `DPS share`) · comparación Prydwen · justificación textual del tier (`Sube 1 tier atribuible a M2…`) · botón `[VER RUNS DE ESTE PJ]`.

#### C. VS PRYDWEN

Tabla side-by-side `1080 × scroll`:

| PJ | Prydwen (Shiyu) | Personal | Δ | Runs | Tendencia 30d |
|----|----------------|----------|---|------|---------------|
| Yanagi | S | S | = | 17 | ━ |
| Burnice | S | S+ | 🟢 ▲1 | 12 | 📈 |
| Ellen | S+ | S | 🔴 ▼1 | 4 | 📉 |
| Miyabi | S+ | S+ | = | 7 | ━ |

Última columna `Tendencia 30d` con sparkline embebido (8 puntos de tier).

#### D. HISTÓRICO

Gráfico de líneas grande (`1080×460 px`):
- Eje X: ciclos numerados (`C1, C2, …, C12 (actual)`).
- Eje Y: tier discretizado (`D=0, C=1, B=2, A=3, S=4, S+=5`).
- Una línea por PJ, color = elemento del PJ. Punto grueso por ciclo. Hover punto → tooltip con score+runs.
- Panel lateral derecho `200 px` con checkboxes para mostrar/ocultar líneas individualmente, y atajos `[Solo S-tier]` `[Solo Anomalía]` `[Reset]`.

#### E. CICLOS

Cards horizontales por ciclo (Shiyu C12 actual + 3 anteriores). Cada card 1080×120:
```
┌─[CICLO C12 · Shiyu Critical · 22 abr–06 may]──────────────────────────────────┐
│ Boss A: Hexan-Lobo  ·  Boss B: Cinder Knight  ·  Reglas: ↑Eléctrico ↓Hielo    │
│ Tu mejor: ★★★ 1:48 · Yanagi+Burnice+Caesar  ·  promedio del ciclo: 2:14       │
│ Runs registrados: 17 · win_rate 100% · ratio 3★: 94%  [VER TODOS LOS RUNS]    │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.5 — Tab ARMAS · 4 sub-vistas (RF-14)

**Sub-tab nav:** `RANKING POR PJ` · `BUILD FULL` · `CATÁLOGO` · `VS PRYDWEN`.

#### A. RANKING POR PJ

Selectores arriba: `PJ [Yanagi ▾]` · `Contenido [Shiyu Critical ▾]` · `Solo en inventario [✓]`.

Tabla `1080 × scroll` top 8 engines por delta:
| Rk | Engine (logo 28px + nombre) | Tier pers. | Tier Prydwen | Δ | Score | R req | En inventario |
|----|----------------------------|-----------|-------------|---|-------|-------|---------------|
| 1 | 🎵 Llanto Mielgo | S+ | S+ | = | 94.2 | R1 | ✅ R1 (equipado) |
| 2 | 🛠 Compilador Quimérico | S | S | = | 88.7 | R1 | ✅ R3 |
| 3 | 🔧 Anhelo Marcato | A | S | 🔴 ▼1 | 79.3 | R5 | ❌ |
| 4 | … | … | … | … | … | … | … |

Click row → modal Engine 800×500 px con desglose:
- Header: logo 64px + nombre + rareza + ataque base + stat secundario.
- Pasiva estructurada: condición · efecto · uptime contextual (`60% en Shiyu vs 35% en HZ`).
- Comparación contra arma actual equipada (delta numérico).
- Sparkline de DPS share simulado en Shiyu/DA/HZ con esta arma.

#### B. BUILD FULL

Selector PJ + Contenido. Top 3 combinaciones **engine + 6 discos** mostradas como cards `1080×220 px`:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [engine-ico 64px]  +  [hexágono 220px con 6 logos de set]   SCORE 94.1   │
│  Llanto Mielgo R1     Jazz Caótico ×4 + Blues Libre ×2                   │
│                                                                          │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  Engine 38%  ·  Discos 62%  ·  Sinergia +6%           │
│  ATK 2 690 → 3 124  CR 21.8 → 28.3  CDmg 64.4 → 89.1   AnomM 329 → 364   │
│  [VER EN MIS DISCOS]    [SIMULAR EN DA]    [GUARDAR PRESET]              │
└──────────────────────────────────────────────────────────────────────────┘
```

3 cards apiladas. La primera con borde glow yellow (mejor build encontrada).

#### C. CATÁLOGO

Toggle vista `▦ GRID` (default) · `☰ TABLA`.

**Grid:** cards `200×130` por engine. Logo `48px` centrado arriba + nombre + `pasiva_tipo` (etiqueta breve: `crit_dmg_dps`, `disorder_anomaly`, etc.) + badge esquina `🟢 modelado completo / 🟠 parcial / 🔴 sin modelar`. Filtro arriba: `Tipo de pasiva ▾` · `Estado modelado ▾` · `🔍`.

**Tabla:** `Logo 24` · `Nombre` · `Rareza (S/A/B)` · `ATK base` · `Stat secundario` · `Pasiva tipo` · `Estado` · `# PJs que lo usan idealmente`.

#### D. VS PRYDWEN

Mismo formato que Lategame VS PRYDWEN pero por engine + contenido:
| Engine | Contenido | Prydwen | Personal | Δ | Notas |
|--------|-----------|---------|----------|---|-------|
| Llanto Mielgo | Shiyu | S+ | S+ | = | — |
| Fósil Preciado | DA | S+ | S+ | = | — |
| Fósil Preciado | HZ | S | B | 🔴 ▼2 | "uptime bajo en HZ" |

---

### 3.6 — Tab CATÁL · 3 secciones colapsables

Acordeón vertical con `<SectionHead>` por sección. Una expandida a la vez (default: la primera).

#### A. ARQUETIPOS (6)

Card por arquetipo `1080×100 px`:
```
┌── ATK_DPS ──────────────────────────────────────────────────────────────┐
│ "Crit-driven, escala con ATK% y CDmg. Set 4pc Puffer Electro / Polar."   │
│ ATK%  ▓▓▓▓▓▓▓▓░░ 25   CR%  ▓▓▓▓▓▓▓░░░ 20   CDmg%  ▓▓▓▓▓▓▓▓▓▓ 30        │
│ HP%   ░░ 0       DEF% ░░ 0       AnomM ░░ 0      ER% ▓ 5                │
│ PJs canónicos: Ellen · Zhu Yuan · Soldier 11 · Harumasa · Evelyn         │
└─────────────────────────────────────────────────────────────────────────┘
```

6 arquetipos: `ATK_DPS` · `HP_DISRUPT` · `ANOMALY` · `STUN` · `SUPPORT_ER` · `DEFENSE`. Cada uno con su set de pesos y PJs canónicos.

#### B. SETS CLASIFICADOS (26)

Tabla `1080 × scroll`:
| Logo 20 | Nombre | Arquetipo primario | Secundario | Discos en inventario | Cobertura PJs |
|---------|--------|-------------------|------------|----------------------|---------------|
| 🎵 | Jazz Caótico | ANOMALY | ATK_DPS | 64 | Yanagi · Burnice · Jane Doe |
| ❄️ | Polar Metal | ATK_DPS | — | 48 | Ellen · Lycaon |
| ⚡ | Puffer Electro | ATK_DPS | — | 42 | Ellen · Burnice |
| … | … | … | … | … | … |

#### C. SUBSTAT PREFERENCES (45 PJs · editable inline)

Tabla con header sticky:
| PJ (ico 24) | ATK% | CR% | CDmg% | HP% | DEF% | AnomM | Impact | ER% | Σ |
|-------------|------|-----|-------|-----|------|-------|--------|-----|---|
| Yanagi | `[20]` | `[25]` | `[30]` | 0 | 0 | `[20]` | 0 | `[5]` | **100** ✅ |
| Burnice | `[15]` | `[10]` | `[10]` | 0 | 0 | `[40]` | 0 | `[25]` | **100** ✅ |
| Caesar | 0 | 0 | 0 | `[15]` | `[40]` | 0 | `[35]` | `[10]` | **100** ✅ |

Inputs numéricos inline. Save on blur. La columna `Σ` en verde si =100, rojo si ≠100. Botón `[VALIDAR & GUARDAR TODOS]` al final. Cuando se guarda, toast: `✅ Preferences de Yanagi actualizadas. 3 alternativas re-rankeadas.`

---

### 3.7 — Tab CONFIG + Wizard onboarding

#### A. Tab CONFIG (1320×820)

Form vertical en 2 columnas (cada una `~520 px`), agrupado por `<SectionHead>`:

**Columna izquierda:**
- `THRESHOLDS GLOBALES` — Equipar (slider 0–1, default 0.75) · Reserva (default 0.50) · Descartar (default 0.25). Cada slider muestra el valor actual a la derecha.
- `NOTIFICACIONES` — Modo toast (radio: `Accionables solamente` / `Todas` / `Silencioso`) · Duración auto-fade (slider 1–10s, default 5s) · `[ ] Sonido al aparecer` toggle.
- `HOTKEYS` — tabla 5 filas con botón `[Editar]` por fila (al click, captura próxima combinación). Detector de conflictos.

**Columna derecha:**
- `IA (RF-12)` — Cap mensual USD (input numérico, default `$5.00`) · Modelo default (radio: `claude-sonnet-4-6` / `claude-haiku-4-5`) · Prompt caching toggle.
- `OCR` — Backend (radio: Tesseract / PaddleOCR) · Idioma (`es-ES` / `en-US`) · Botón `[CALIBRAR ROIs]` que lanza wizard.
- `SISTEMA` — Autostart Windows (toggle, default OFF) · Carpeta DB (ruta + `[CAMBIAR]`) · Tema (radio: `Dark` / `Dark + acento PJ`) · Botón rojo `[RESET A DEFAULTS]`.

Sticky abajo: barra `[GUARDAR CAMBIOS]` (verde, deshabilitado si no hay diff) + `[DESCARTAR]`.

#### B. Wizard primera ejecución (modal 600×450)

Stepper superior `─●────●────●─` 3 pasos.

**Paso 1 — Carpeta DB.** File-picker para seleccionar `danibod_zzz_v2.db`. Preview tras seleccionar: tablas encontradas + filas (`agents 45 · discs 332 · runs 184 · …`). Botón `[SIGUIENTE]` deshabilitado hasta seleccionar.

**Paso 2 — Calibrar ROIs OCR.** Captura placeholder de la pantalla de discos del juego. Instrucción: `Dibuja un rectángulo alrededor de cada zona de texto`. Zonas a marcar: `Set` · `Slot` · `Main stat` · `Sub 1-4`. Lista a la derecha con check verde tras dibujar cada una.

**Paso 3 — Verificar Hotkeys.** Tabla de 5 hotkeys con detector de conflictos en sistema (`🟢 libre` / `🔴 conflicto: ya usado por <X>`). Botón `[FINALIZAR SETUP]` cuando todas en verde.

**Wizards de Onboarding adicionales** (accesibles desde CONFIG → "Wizards"):
- `Agregar PJ nuevo` — 4 pasos: datos básicos · stats efectivos · override arquetipo · confirmación + catalogación IA con progress bar `[████░░░░] 4/8 — Catalogando sinergias IA (12/44 pares)…`.
- `Agregar W-Engine nuevo` — 3 pasos: datos básicos · pasiva estructurada · contextos de uso.
- `Agregar Set de discos nuevo` — 2 pasos: nombre + 2pc/4pc · clasificación arquetipo.
- `Agregar Facción nueva` — 1 paso: nombre + logo + PJs miembros.

---

### 3.8 — Tray menu (200×160)

Menú flotante posición esquina inferior derecha sobre la barra de tareas:
```
┌────────────────────────────┐
│ ⬡ DaniBOD ZZZ Analytics   │  ← cabecera (no clickeable)
│ ● MONITOREANDO             │  ← estado en lima `var(--positive)`
├────────────────────────────┤
│   ▶  Abrir panel       F9  │
│   ⏸  Pausar captura    F10 │
├────────────────────────────┤
│   ⚙  Configuración         │
│   ✕  Salir       Ctrl+⇧+Z │
└────────────────────────────┘
```

Estilo: `bg-panel-solid` + chamfer `tl-br` 12px + sombra deep + borde `1px var(--border-subtle)`. Items con padding `8px 14px`, hover `bg-row-hover`. Hotkey en mono 9px alineado a la derecha en gris.

**Variante "pausada":** estado lima → `⏸ PAUSADA` en `var(--text-muted)`. Item `Pausar captura` cambia a `▶ Reanudar captura`.

---

## 4. Convenciones técnicas para esta sesión

### 4.1 Reusar primitivos antes de crear nada

Antes de definir un componente nuevo, revisar `components.jsx`:
- ¿Es un panel con depth/glow? → `<BlockBox>` o `<ChamferBox>`.
- ¿Es una tabla con header sticky? → wrap en `<ChamferBox cut={14} cutCorners="tl-br" pattern="carbon">`.
- ¿Es un score/tier badge? → `<Tag>` o `<Rarity>`.
- ¿Es un KPI de header? → `<KPI>`.
- ¿Es un botón? → `<ZButton variant="primary|ghost|danger" size="sm|md" icon="...">`.
- ¿Es un score con threshold? → `<ScoreGauge>`.
- ¿Es un section divider con título? → `<SectionHead>`.
- ¿Es un icono SVG? → `<Icon name="...">` (30 disponibles, agregar al switch si falta).

### 4.2 Estructura de archivos a entregar

Crear un archivo `.jsx` por nueva pestaña:
```
roster-tab.jsx       → exporta RosterTab y wirea con AgentStatsCard
hist-tab.jsx         → exporta HistTab
teams-tab.jsx        → exporta TeamsTab (con sub-tabs internos)
lategame-tab.jsx     → exporta LategameTab (con sub-tabs internos)
weapons-tab.jsx      → exporta WeaponsTab (con sub-tabs internos)
catal-tab.jsx        → exporta CatalTab (acordeón)
config-tab.jsx       → exporta ConfigTab y OnboardingWizard
tray-menu.jsx        → exporta TrayMenu
```

Wirearlos en `DaniBOD ZZZ Analytics.html`:
- Agregar `<script type="text/babel" src="...jsx">` en el head.
- Agregar nuevas `<DCSection>` en `App()` con `<DCArtboard>` por pestaña.
- Cada artboard usa `<div className="zzz-root">` como wrapper para que tokens.css aplique.

### 4.3 Extender `data.jsx`, no rehacerlo

Agregar los nuevos arrays/objetos a `window` desde cada archivo de pestaña (no tocar `data.jsx` directamente):
```js
// hist-tab.jsx
const EVALUATIONS = [/* … 40 ejemplos cubriendo las 4 acciones × varios PJs */];

// teams-tab.jsx
const SYNERGY_PAIRS = [/* … 25 pares con confianza variada */];

// lategame-tab.jsx
const RUNS = [/* … 18 runs cronológicos */];
const TIER_DATA = {/* … por PJ */};

// weapons-tab.jsx
const ENGINES = [/* … 38 engines */];

Object.assign(window, { EVALUATIONS, SYNERGY_PAIRS, RUNS, TIER_DATA, ENGINES });
```

### 4.4 Datos canónicos a respetar

- **No inventar PJs nuevos sin facción/elemento real del juego.** La tabla del §3.1 lista los 15 nuevos PJs aprobados; usar solo esos + los 5 ya canónicos.
- **No inventar nombres de engines.** Usar los presentes en `Engines_icons/` (versión slug español, ej. `llanto_mielgo.webp`).
- **Sets:** los 26 oficiales ya están en `Set_Discos_Logo/` (versión slug español, ej. `jazz_caotico.webp`).
- **Facciones:** las 13 oficiales en `Facciones_Logos/`. Mapeo nombre español ↔ archivo en `Facciones_Logos/README.md`.
- **Stats numéricos:** mantener los del §3 del brief original (`BRIEF_COMPLETO.md`).

---

## 5. Tabla de assets requeridos por pantalla

| Pantalla | Assets que necesita |
|----------|---------------------|
| Tab ROSTER | 20 splash arts `*-ico.webp` (los 5 canónicos + 15 nuevos del §3.1) · 9–10 logos de facción · 20 logos de engine |
| Tab HIST | Los 7 set logos canónicos · los 5 PJ icos canónicos |
| Tab EQUIPOS · MATRIZ | 20 splash arts `*-ico.webp` (mini, 24px) |
| Tab EQUIPOS · TOP-N | Los 5 PJ icos canónicos |
| Tab EQUIPOS · IA Insights | Ningún asset extra |
| Tab LATEGAME · todos | Splash arts + content badges (Shiyu/DA/HZ) — generar SVG inline |
| Tab ARMAS · todos | 12+ engine logos (ya disponibles en `Engines_icons/`) |
| Tab CATÁL | 6 engine logos · 26 set logos · 5 PJ icos |
| Tab CONFIG · Wizard | Captura placeholder pantalla de discos (generar abstracta) |
| Tray menu | Solo el logo `⬡ DaniBOD ZZZ Analytics` (ya existe en TitleBar de panel.jsx) |

---

## 6. Orden de generación sugerido (sesión 2)

Generar como `<DCSection>` separadas en este orden:

1. **`section: roster`** — ROSTER grid completo + 1 ejemplo de hover-state + 2 modales PJ nuevos (Miyabi, Astra Yao).
2. **`section: hist`** — HIST tabla + sidebar + 1 ejemplo modal "Detalle evaluación".
3. **`section: teams`** — 3 artboards: matriz, TOP-N, IA Insights.
4. **`section: lategame`** — 5 artboards: runs, tier list, vs prydwen, histórico, ciclos.
5. **`section: weapons`** — 4 artboards: ranking, build full, catálogo, vs prydwen.
6. **`section: catal`** — 1 artboard con los 3 acordeones expandidos.
7. **`section: config`** — 2 artboards: tab CONFIG completo + Wizard 3 pasos.
8. **`section: tray`** — 1 artboard 200×160 + variante pausada.

**Si los tokens se acaban antes de terminar, priorizar 1-3 (cierran los flujos más usados día a día).**

---

## 7. Checklist final antes de cerrar la sesión

- [ ] Cada pantalla pendiente tiene su `<DCArtboard>` etiquetado.
- [ ] No se duplicaron primitivos ya existentes en `components.jsx`.
- [ ] Sidebar del panel es **el mismo** en todas las pestañas (importar desde `panel.jsx`, no recrear).
- [ ] StatusBar es **la misma** en todas las pestañas.
- [ ] Cada nueva pestaña respeta `1320×820` exactos para el panel.
- [ ] No se introdujeron colores fuera de `tokens.css` (si hace falta, agregarlo a tokens.css con justificación).
- [ ] Datos mockeados extraídos a `window.*` para que sean reusables entre pestañas (un PJ nombrado en HIST debe tener el mismo ico que en ROSTER).
- [ ] Cada modal abre por click documentado en el flujo (§6 del brief original).
- [ ] Screenshots PNG de cada artboard exportadas a `Screenshot_mockups/` para documentación.

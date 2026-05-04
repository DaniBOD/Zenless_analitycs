# Interfaz — Pantallas + flujos de navegación

Catálogo de pantallas del `.exe` (RF-11) + **mapa de flujos de usuario** que documenta cómo se navega entre vistas. Sirve como contrato visual para implementación PySide6 y para los mockups en Claude Design.

## Documentos en esta carpeta

- **`README.md`** (este archivo) — pantallas + flujos + hotkeys + principio rector.
- **[`Brief_Claude_Design.md`](./Brief_Claude_Design.md)** — brief para usar con Claude Design (prompt + paleta + iconos por contexto + pantallas pendientes).
- **[`referencias_visuales/`](./referencias_visuales/)** — 6 capturas del juego ZZZ + paleta extraída píxel a píxel.
- **[`splash_arts/`](./splash_arts/)** — destino para splash arts oficiales de los 45 PJs (script de descarga incluido).
- **[`Facciones_Logos/`](./Facciones_Logos/)** — 13 logos canónicos de facciones del roster + 2 extras.
- **[`Set_Discos_Logo/`](./Set_Discos_Logo/)** — 26 logos de drive discs renombrados a slug español.
- **[`Engines_icons/`](./Engines_icons/)** — 38 logos de W-Engines (31 confirmados + 7 tentativos).
- **`mockups/`** — exports de Claude Design (toast variantes + panel Captura en vivo ya generados).

---

## Arquitectura — 3 superficies

```
┌─ TRAY (siempre visible) ──────────────────────────────────────────────┐
│   Icono en system tray + menú: Abrir panel · Pausar · Config · Salir  │
└─────────────────────────────────────────────────────────────────────────┘
                ▲                          ▲
                │                          │
                │  click derecho           │  hotkey F9 / click toast
                │                          │
┌─ TOAST FLOTANTE ─────────────────┐    ┌─ PANEL PRINCIPAL ──────────────┐
│  380×116 px, esquina BR          │    │  1320×820 px, ventana con      │
│  always-on-top · auto-fade 5 s   │───▶│  sidebar (9 pestañas)          │
│  5 variantes por color de acción │    │  + status bar abajo            │
└──────────────────────────────────┘    └────────────────────────────────┘
```

## Pestañas del Panel Principal — 9 pestañas

| # | Pestaña | RF | Propósito |
|---|---------|-----|-----------|
| 1 | **Captura en vivo** | RF-04/05/06 | Último disco capturado + desglose scoring + alternativas (3 columnas). |
| 2 | **Histórico** | RF-04 | Tabla navegable de `inventory_disc_evaluations` con filtros (fecha, recomendación, PJ, set). |
| 3 | **Roster** | — | 45 PJs en grid de cards (foto + nombre + mindscape + rol + elemento + facción + % build completado). Filtros por rol/elemento/facción/estado. Click → modal con detalle. |
| 4 | **Discos** ⭐ NUEVA | RF-04/06 | **Inventario completo de 332 discos.** Tabla/grid con filtros (set, slot, main stat, score, asignado a PJ). Click en un disco → vista detallada con: PJs compatibles + score por arquetipo + valor a futuro + alternativas en inventario. |
| 5 | **Equipos** | RF-12 | Sub-pestañas: (a) Matriz de pares con sinergia (45×45), (b) Top-N composiciones por PJ, (c) **🧠 IA Insights** (NUEVA — `ai_catalog_runs`, costo mensual, sinergias recientes, queue de catalogación). |
| 6 | **Lategame** | RF-13 | 5 sub-vistas: Runs recientes / Tier List Personal / Comparativo Prydwen / Histórico / Ciclos. |
| 7 | **Armas** | RF-14 | 4 sub-vistas: Ranking por PJ / Build Full / Catálogo W-Engines / Comparativo Prydwen. |
| 8 | **Catálogos** | RF-04/06 | 3 secciones: Arquetipos (6) / Sets clasificados (26) / Substat preferences por PJ (45 — editable). |
| 9 | **Configuración** | RF-11 | Thresholds, modo toast, hotkeys, tema, autostart, calibración OCR, **wizards de Onboarding** (PJ / W-Engine / Set / Facción). |

---

## 🗺 Mapa de flujos de usuario — 12 escenarios típicos

### Flujo 1 — Captura automática de disco nuevo (el caso de uso central)

```
[Daniel está jugando ZZZ — pantalla completa]
  ↓ farmea un disco en Patrulla de Área / Tienda de Música
[RF-04 detecta cambio en inventario vía polling 500 ms]
  ↓ OCR híbrido extrae set + slot + main + 4 substats
[scoring engine evalúa contra 45 PJs y arquetipos]
  ↓ score ≥ threshold_equip → recomendación EQUIPAR
[💚 TOAST aparece esquina BR, always-on-top, 5 s auto-fade]
  ├─ Hover  → barra de progreso pausa, opacidad 100%
  ├─ Click  → expande al Panel Principal pestaña "Captura en vivo"
  └─ No interacción → fade-out a los 5 s, queda registrado en Histórico
```

### Flujo 2 — Ver detalle del disco recién capturado

```
[Toast EQUIPAR Tecno Pícido → Yanagi M2 score 87.3 △12]
  ↓ click en el toast
[Panel Principal se abre en pestaña "Captura en vivo"]
  ┌─ Columna 1: Disco capturado #00482
  │  • Visualización hexágono (slot 4 destacado)
  │  • Set + slot + nivel
  │  • Atributo principal + 4 substats con badges +N
  │  • Efecto de conjunto 2pc/4pc
  ├─ Columna 2: Desglose de scoring → Yanagi (M2)
  │  • Score final 87.3 △12.4 con gauge vs threshold
  │  • Desglose por substat (positivos × rolls, perjudiciales × rolls)
  │  • Bonus main + level + set match
  │  • Botones: BLOQUEAR · DESCARTAR · EQUIPAR A YANAGI
  └─ Columna 3: Alternativas compatibles (RF-12)
     • Top 5 PJs por delta de score
     • Sinergia sugerida si aplica (RF-12 IA)
     • Retro RF-13 si hay datos
```

### Flujo 3 — Quiero ver TODOS mis discos del slot 4 con ATK% (caso del usuario) ⭐

```
[Tray] → click "Abrir panel"
[Panel Principal]
  ↓ click pestaña "Discos" (4ª en sidebar)
[Inventario: tabla/grid de 332 discos con filtros arriba]
  ┌─ Filtros: set | slot | main_stat | score | asignado_a | descartado
  └─ Vista por defecto: ordenado por score descendente
  ↓ usuario filtra: slot=4, main=ATK%
[Resultado: ~30 discos]
  ↓ click en un disco específico (ej. Tecno Pícido slot 4 #00482)
[Vista detallada del disco — modal o panel lateral]
  ├─ Stats completos del disco
  ├─ "PJs compatibles" — lista rankeada por score
  │   • Yanagi M2: 87.3 ▲12 (mejor opción) [Equipar]
  │   • Burnice M1: 81.4 ▲9 [Comparar]
  │   • Piper M6: 76.2 ▲5
  │   • ...
  ├─ "Valor a futuro" — análisis por arquetipo + main + subs
  │   • Arquetipo dominante: ANOMALY (2 substats positivos × 3 rolls)
  │   • Si subes el nivel: proyección de score a +3, +6, +9, +12, +15
  │   • Set match: 4pc Tecno Pícido (excelente para Yanagi/Burnice)
  └─ "Alternativas" — otros discos similares en tu inventario
      • Comparación side-by-side con los 3 mejores Tecno Pícido slot 4
```

### Flujo 4 — Ver mi mejor build para un PJ específico (RF-06)

```
[Panel Principal] → pestaña "Roster"
  ↓ grid de 45 cards
  ↓ click en card de Yanagi
[Modal de PJ — 800×600 px]
  ├─ Header: foto splash + nombre + mindscape + rol + elemento + logo facción
  ├─ Stats actuales vs thresholds (gauge por cada stat)
  ├─ Build actual: 6 slots equipados (hexágono interactivo)
  ├─ Awakening: nivel + descripción del efecto
  └─ Botones:
      • OPTIMIZAR BUILD → modal con top 3 builds (RF-06)
      • OPTIMIZAR ARMA → cambia a pestaña "Armas" pre-seleccionado
      • SUGERIR EQUIPO → cambia a pestaña "Equipos" pre-seleccionado
      • VER RUNS LATEGAME → cambia a pestaña "Lategame" filtrada
```

### Flujo 5 — Optimizar arma para Yanagi en Deadly Assault (RF-14)

```
[Panel Principal] → pestaña "Armas"
  ↓ sub-pestañas: Ranking por PJ · Build Full · Catálogo · Comparativo Prydwen
  ↓ click "Ranking por PJ"
  ↓ selector PJ: Yanagi · selector contenido: Deadly Assault
[Tabla con top-N W-Engines]
  ┌─ Columnas: rank | arma (con icono) | tier personal | tier Prydwen | delta | score | refinamiento req | en inventario
  └─ Click en un arma → modal con desglose de scoring
      • score_atk_base + stat_secundario
      • score_pasiva (con uptime contextual del content_profile)
      • score_synergy_pj
      • Comparación contra arma actual equipada
```

### Flujo 6 — Registrar un run de Shiyu Critical recién terminado (RF-13)

```
[Daniel termina su run en Shiyu, está en pantalla de resumen del juego]
  ↓ presiona F11 (hotkey global)
[Captura 1: pantalla resumen — equipo + estrellas + tiempo]
[Toast: "📋 Navegá a Battle Stats para capturar breakdown DMG"]
  ↓ Daniel navega in-game al breakdown
[Captura 2: breakdown DMG por agente]
[OCR híbrido extrae: equipo, contenido, ciclo, estrellas, tiempo, %DMG por PJ]
[Validación de consistencia: ΣDMG≈100, PJs match roster]
[INSERT en lategame_runs + lategame_run_damage]
[💛 TOAST RUN LATEGAME REGISTRADA]
  ┌─ Yanagi + Burnice + Lighter
  ├─ DEADLY ASSAULT - NODO 3 ⭐⭐⭐
  ├─ TIEMPO 1:48 (-14s vs promedio)
  └─ DPS SHARE 67% Yanagi
[Si runs_nuevos ≥ 3, encolar recálculo de tier list automáticamente]
```

### Flujo 7 — Ver mi tier list personal vs Prydwen (RF-13)

```
[Panel Principal] → pestaña "Lategame"
  ↓ sub-pestañas internas: Runs recientes · Tier List Personal · Comparativo Prydwen · Histórico · Ciclos
  ↓ click "Tier List Personal"
[Vista de columnas S+/S/A/B/C/D]
  ┌─ Cards de PJs distribuidos en cada columna
  ├─ Cada card muestra: foto + nombre + mindscape + score numérico
  └─ Filtro arriba: "Por contenido" (Shiyu Critical / DA / general)
  ↓ click en card de Yanagi
[Modal de detalle de tier]
  ├─ Score normalizado: 93.2 (S+)
  ├─ Métricas: 17 runs · win_rate 100% · rate_3★ 94% · DPS share 56.7%
  ├─ Comparación con Prydwen: tier S → +1 a S+
  └─ Justificación: "Sube 1 tier atribuible a M2 (Prydwen asume M0)..."
```

### Flujo 8 — Ver costo mensual de IA + queue de catalogación (RF-12)

```
[Panel Principal] → pestaña "Equipos"
  ↓ sub-pestañas: Matriz de pares · Top-N composiciones · 🧠 IA Insights
  ↓ click "🧠 IA Insights"
[Dashboard de uso de Claude API]
  ┌─ Gauge: $3.42 / $5.00 (cap mensual) · 68% usado
  ├─ Gráfico de costo diario (últimos 30 días)
  ├─ Tabla de últimas 20 catalogaciones (operacion, modelo, tokens, costo, fecha)
  ├─ Queue pendiente: "44 pares pendientes para Lyra (PJ nuevo) — ETA 12 min"
  ├─ Botones: PAUSAR QUEUE · RECATALOGAR PAR... · INVALIDAR CACHE
  └─ Estadísticas globales: pares totales catalogados / con sinergia / sin sinergia
```

### Flujo 9 — Agregar un PJ nuevo del patch v2.9 (Onboarding)

```
[Panel Principal] → pestaña "Configuración"
  ↓ scroll hacia "Wizards de Onboarding"
  ↓ click "Agregar PJ nuevo"
[Wizard modal 600×500 px — 4 pasos]
  ├─ Paso 1: Datos básicos (nombre, rango, elemento, rol, facción, mindscape, versión)
  ├─ Paso 2: Stats efectivos (form numérico O botón "Importar HoYoLAB screenshot")
  ├─ Paso 3: Override de arquetipo (checkbox "¿Escala con HP?" + dropdown)
  └─ Paso 4: Confirmación con preview
  ↓ click "Confirmar y catalogar"
[Progress bar — 8 pasos automáticos]
  [████░░░░] 4/8 — Catalogando sinergias IA (12/44 pares)...
  ↓ ~5-15 minutos (mayoría espera IA)
[Toast: "✅ PJ agregado: Lyra (S · Hielo · Ataque · Section 6)"]
```

### Flujo 10 — Cambiar threshold de equipar para un PJ

```
[Panel Principal] → pestaña "Catálogos"
  ↓ scroll a sección "Substat preferences por PJ"
  ↓ buscar PJ → editar inline
[Editor de pesos por substat]
  ├─ Tabla: substat | peso (slider -1 a +1) | fuente
  └─ Click "Guardar" → invalida weapon_evaluations + inventory_disc_evaluations del PJ
[Recálculo automático en background]
[Toast: "✅ Preferences de Yanagi actualizadas. 3 alternativas re-rankeadas."]
```

### Flujo 11 — Pausar captura mientras juego algo casual

```
[Tray icon] → click derecho
[Menú contextual: Abrir panel · ▶ Pausar captura · Configuración · Salir]
  ↓ click "Pausar captura"
[Tray icon cambia color (gris) · toast "⏸ Captura pausada"]
[F10 también funciona como toggle]
[Para reanudar: misma vía, click "Reanudar captura" o F10 de nuevo]
```

### Flujo 12 — Ver runs históricos de un equipo específico

```
[Panel Principal] → pestaña "Lategame" → sub-tab "Runs recientes"
  ↓ filtros: PJ principal = Yanagi · contenido = Shiyu Critical
[Tabla de runs cronológica]
  ┌─ Columnas: fecha | equipo | contenido + ciclo | estrellas | tiempo | DPS share
  └─ Click en un run específico
[Modal de detalle del run]
  ├─ Screenshots adjuntos (resumen + breakdown)
  ├─ Equipo completo con stats
  ├─ Comparación contra promedio del PJ
  └─ Botón "ELIMINAR RUN" (si hubo error de captura)
```

---

## Hotkeys globales

| Hotkey | Acción | Notas |
|--------|--------|-------|
| `F8` | Captura manual de disco | Fuerza análisis del frame actual |
| `F9` | Toggle panel principal | Abre/cierra desde cualquier estado |
| `F10` | Pausar/reanudar captura | Toggle |
| `F11` | Registrar run lategame | Inicia flujo de §6 (RF-13) |
| `Ctrl+Shift+Z` | Salir de la app | Emergencia |

## Status bar (footer del panel principal)

```
SQLITE 18.4 MB · OCR TESSERACT 5.4 ES · CICLO ACTUAL 12 / 28D · MONITOREANDO · UID 1006860143
```

Indicadores constantes: tamaño DB, backend OCR + idioma, ciclo activo Shiyu, estado de captura, UID del jugador.

## Principio rector

**Latencia percibida < 500 ms** desde que el evento ocurre en pantalla del juego hasta que el toast aparece en escritorio. Si la UI llega tarde, no tiene valor — Daniel sube discos a nivel 15 en pocos segundos.

## Color theming por personaje (modales de detalle)

Cuando se abre el **modal de detalle de un PJ específico** (desde Roster, desde "Alternativas compatibles" en Captura en vivo, desde la pestaña Equipos, desde el wizard de onboarding, etc.), la paleta del modal **se adapta a la identidad visual del personaje**:

- **Yixuan** → dorado + negro (Yunkui Summit, identidad imperial)
- **Ellen Joe** → rojo + negro + blanco (identidad tiburón)
- **Yanagi** → azul oscuro + violeta (paleta eléctrica canónica de ZZZ)
- **Caesar** → amarillo + dorado + negro (físico = amarillo signature ZZZ)
- **Miyabi** → blanco-celeste + dorado (Hoshimi family, hielo aristocrático)
- ... etc para los 45 PJs

**Paletas base por elemento (ajustadas a ZZZ canónico abril 2026):**

| Elemento | Color signature |
|----------|-----------------|
| 🔥 Fuego | rojo-naranja `#FF6B47` |
| ❄️ Hielo | cian `#5BC0EB` |
| ⚡ Eléctrico | **azul oscuro** `#1E3A8A` (no púrpura) |
| 🥊 Físico | **amarillo signature** `#FFCB05` (mismo accent de la app) |
| 🌌 Éter | lavanda `#A78BFA` |

El resto de la UI (sidebar, toast, paneles, status bar, otras pestañas) **mantiene la paleta default** negro `#0a0a0a` + amarillo signature `#FFCB05`. La excepción del PJ refuerza identidad sin romper coherencia general.

Sistema de 2 niveles: **paleta base por elemento** (Físico/Fuego/Hielo/Eléctrico/Éter) como fallback automático + **overrides personalizados** por PJ con identidad visual fuerte. Tabla completa con hex codes en [`Brief_Claude_Design.md` §Color theming por personaje](./Brief_Claude_Design.md#color-theming-por-personaje-modales-de-detalle-de-pj).

A nivel DB, futuras columnas en `agents`: `accent_primary`, `accent_secondary`, `accent_tertiary` (TEXT hex). Si NULL, fallback a la paleta del elemento.

## Estado actual de mockups (Claude Design)

| Pantalla | Estado | Archivo en `mockups/` |
|----------|--------|----------------------|
| Toast EQUIPAR (variante 1/5) | ✅ generado | `01_toast_equipar.png` (sugerido) |
| Toast MEJORAR (variante 2/5) | ✅ generado | `02_toast_mejorar.png` |
| Toast RESERVA (variante 3/5) | ✅ generado | `03_toast_reserva.png` |
| Toast DESCARTAR (variante 4/5) | ✅ generado | `04_toast_descartar.png` |
| Toast RUN LATEGAME (variante 5/5) | ✅ generado | `05_toast_run_lategame.png` |
| Toast estados (hover/expanding/fade-out) | ✅ generado | `06_toast_estados.png` |
| Toast en contexto real (sobre juego) | ✅ generado | `07_toast_contexto.png` |
| Panel Principal · Captura en vivo | ✅ generado | `08_panel_captura_viva.png` |
| Panel · Histórico | ⏳ pendiente | — |
| Panel · Roster | ⏳ pendiente | — |
| Panel · Discos ⭐ | ⏳ pendiente | — |
| Panel · Equipos (3 sub-vistas incl. IA Insights) | ⏳ pendiente | — |
| Panel · Lategame (5 sub-vistas) | ⏳ pendiente | — |
| Panel · Armas (4 sub-vistas) | ⏳ pendiente | — |
| Panel · Catálogos | ⏳ pendiente | — |
| Panel · Configuración | ⏳ pendiente | — |
| Wizard Onboarding (4 modos × 4 pasos) | ⏳ pendiente | — |
| Tray icon + menú contextual | ⏳ pendiente | — |

> ⚠️ **Documento histórico — snapshot de mayo 2026, NO es el estado actual.**
>
> Este era el `README.md` de la raíz hasta el 2026-08-28. Se archivó acá cuando el README pasó a
> ser una portada del repositorio: sus 1214 líneas describían la Fase 1 (diseño cerrado, cero
> código del `.exe`) y varias secciones —sobre todo §2 *Estado Actual* y §12 *Estructura de
> Archivos*— quedaron desactualizadas o describen una estructura que se planificó y después
> cambió.
>
> Se conserva porque §3 (requerimientos), §5 (roster), §6 (thresholds) y §9 (rotaciones) siguen
> siendo la redacción original de esos análisis, y varios docs apuntan acá por sección. Para el
> estado real: [`../README.md`](../README.md) y [`../project-context-IA.md`](../project-context-IA.md).
> Para el diseño de cada RF manda el doc de `RF_*/`, no este archivo.

---

# Proyecto ZZZ — Analizador de Cuenta DaniBOD

**UID:** 1000860143 | **Servidor:** America | **Top 6% global**  
**Fecha inicio:** Abril 2026  
**Herramientas:** SQLite · Python · VS Code · Claude Code

---

## 1. Visión General

Sistema completo de análisis y optimización de cuenta para Zenless Zone Zero, construido porque el juego carece de herramientas de calidad de vida para:

- Evaluar discos al momento de obtenerlos (¿lo guardo o lo borro?)
- Comparar builds contra thresholds óptimos por personaje
- Planificar equipos para Shiyu Defense y Deadly Assault
- Detectar automáticamente discos via screenshot sin interactuar con el proceso del juego
- **Visualizar matemáticamente el mejor equipo para un personaje seleccionado**, considerando sinergias de elemento, rol, facción, buffs y thresholds cubiertos
- **Analizar rotaciones de personajes** para maximizar DPS en combate real (visión a futuro — requiere datos de gameplay)

---

## 2. Estado Actual

### ✅ Completado (Fase 1 — Estado de Personajes)

- Base de datos SQLite completa (`danibod_zzz_v2.db`) con integridad OK y 0 errores de foreign key
- 45/45 agentes cargados con stats reales de HoYoLAB
- 49 W-Engines con pasivas semi-estructuradas (fuente: Prydwen.gg)
- **26 disc sets** con bonuses 2pc y 4pc exactos (post-merge de duplicados id=47→40 y id=50→35)
- 93 thresholds cargados para 45/45 agentes (al menos 1 stat por agente)
- Análisis automático de qué agentes están bajo umbral
- **`agent_discs` poblada al 100%** — 270 filas (6 slots × 45 agentes). Incluye casos especiales: Antón y Ben con 6 slots EMPTY, builds 3+3 sin 4pc (Piper, Nekomata, Manato, Corin), Seth con build mixto sin bono de set, y todos los badges de upgrade (`subN_up` 0-4) registrados donde estaban visibles
- **`inventory_discs`** creada y poblada con **257 discos equipados** del roster (`equipado=1`). Schema completo con `set_id`, `slot`, `main_stat`+4 substats con rolls, `nivel`, `agente_asignado`, `score_evaluacion`, `descartado`, `notas`
- **`inventory_weapons`** creada y poblada con **40 W-Engines equipadas** (5 agentes con weapon_id=45 'Sin arma' no inventariados). Schema: `weapon_id`, `nivel`, `refinamiento`, `agente_asignado`, `equipado`, `fecha_obtencion`, `notas`
- Fusión de set duplicado id=50 → id=35 renombrado a "Nana a la luz cenicienta" (nombre oficial v2.6 de Moonlight Lullaby, confirmado con screenshot: 2pc Recuperación Energía +20%, 4pc soporte +18% DMG equipo 25s)
- Fusión de set duplicado id=47 (Tecno tetraodóntido) → id=40 (Puffer Electro)
- 45/45 screenshots de `Pj_stats/` renombrados al nombre del personaje (de `WhatsApp Image ...jpeg` → `{Nombre}.jpeg`)
- Clasificación correcta del rol Disruptivos para Yixuan, Ye Shunguang y Manato (antes agrupados erróneamente en Ataque)

### ✅ Cerrado (Fase 1.5 — Inventario completo, abril 2026)

- `inventory_discs` cerrado: **332 discos** (257 equipados + 75 no equipados cargados desde `Discos_Inventario_faltantes/`).
- `inventory_weapons` cerrado: **50 W-Engines** (40 equipadas + 10 no equipadas).
- Integridad OK, foreign keys validadas.

### ✅ Cerrado (Fase 1.6 — Schema arquetipos + scoring, abril 2026)

- Migración `2026-04-24_01_archetypes_and_scoring.sql` aplicada con éxito (resuelto bloqueo virtiofs vía scratch local + raw write).
- **6 arquetipos** definidos (ATK_DPS, HP_DISRUPT, ANOMALY, STUN, SUPPORT_ER, DEFENSE) con pesos JSON por substat.
- **26 disc sets** clasificados (8 con dual archetype primary/secondary).
- **45 PJs** con thresholds de equip (default 0.75) y stock (default 0.50).
- Tabla `inventory_disc_evaluations` lista para alojar el histórico del scoring engine.

### ✅ Cerrado (Fase 1.7 — Migraciones 02-05 aplicadas + seeds iniciales, abril 2026)

- **4 migraciones nuevas aplicadas** (`02_optimizer_pending`, `03_team_synergies`, `04_lategame_validation`, `05_weapon_optimizer`) — DB pasó de 13 a **31 tablas**.
- **`enemies` poblada** con 12 enemigos lategame: 5 notorious hunters (Wandering Hunter, Sacrifice Bringer, Sanguine Sweeper, Ye Shiyuan the Thrall, Dead End Butcher) + 3 bosses (Twin Marionettes, Pompey, Nineveh) + 3 elites comunes + 1 training dummy.
- **`enemy_resistances` poblada** con 72 filas (12 enemigos × 6 elementos) basadas en datos de Fandom Wiki + Game8.
- **`content_profiles` poblada** con 4 perfiles seed (Shiyu Critical, DA, Hollow Zero, general).
- **`pj_weapon_synergy` poblada** con 270 filas (45 PJs × 6 tipos de pasiva relevantes) usando matriz rol×tipo basada en conocimiento del juego (Yanagi → AP 1.5 / ER 1.2 / dmg_boost 0.7; Lycaon → ATK 0.8 / ER 1.0; Astra Yao → ER 1.5; etc.).
- Integridad: `PRAGMA integrity_check = ok`, **0 violations** en `foreign_key_check`.

### 🟦 Diseño cerrado (abril 2026 — implementación pendiente)

| RF | Nombre | Documento de diseño |
|----|--------|---------------------|
| **RF-04** | Captura tras cambio de equipamiento (modal/tienda) | [`Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md`](./Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md) |
| **RF-05** | Captura tras upgrade de disco (PRE/POST) | (mismo doc; cubre §upgrade) |
| **RF-06** | Optimizador de build por personaje (greedy + bonus pass) | [`Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md`](./Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md) |
| **RF-09** | Análisis de imagen de disco (OCR híbrido Tesseract + PaddleOCR) | RF-04 doc + RF-09 §3.1 README |
| **RF-11** | UI/UX standalone `.exe` (PySide6 + PyInstaller) | §3.1 RF-11 README + §7 RF-09 |
| **RF-12** | Optimizador team-aware con IA catalogadora (Claude API) | [`Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md`](./Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md) |
| **RF-13** | Validación lategame + tier list personal + retro-feedback bayesiano | [`Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md`](./Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md) |
| **RF-14** | Optimizador de armas (W-Engines) con scoring contextual + build full | [`Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md`](./Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md) |

### ✅ Cerrado (Fase 1 — refinamientos abril 2026)

- **Thresholds:** revisión fina completada. Los 10 gaps propuestos en §6.2 se aplicaron en batch (`agent_thresholds` pasó de 93 → 103 filas). Las 3 imprecisiones detectadas (Miyabi `prob_critico` 65%, Grace/Vivian `tasa_perforacion` 24%, Burnice `maestria_anomalia` cap 350) quedan documentadas como notas operativas para el motor de evaluación futuro.
- **RNF-06 — Responsividad:** consolidado como RNF formal en §3.2 con tabla de presupuestos de latencia por superficie (toast <500ms, optimizador <500ms, lookup RF-12 <50ms, recálculo tier list <3s, etc.) + recursos en idle (RAM <200MB, CPU <3% polling).

### 🔄 En progreso (cierre de Fase 1 — único pendiente)

- **Awakenings:** 1/7 con texto verificado (Burnice nv6 *"Boiling Point Party"*) + 4 confirmados Agotado en tienda con placeholder `pending_capture` (Lycaon, N.° 0: Anby, Ellen, Grace) — falta capturar texto in-game de cada nivel 1-6 y reemplazar placeholder. Harumasa y N.° 11 sin insertar hasta confirmar nivel exacto. Es trabajo manual del usuario; bloquea solo la activación completa del bono de awakening en el scoring engine futuro (RF-06/RF-14).

### 📋 Pendiente (Fases 2-5 — implementación)

- **Implementación de RF-04/05/06/09/11** (Fase 2 — primer hito de codeo del `.exe`).
- **Implementación de RF-12** (Fase 4.5 — migración `2026-04-XX_03_team_synergies.sql` + cliente Claude API + lookups runtime).
- **Implementación de RF-13** (Fase 5 — migración `2026-04-XX_04_lategame_validation.sql` + scrapers Hakush.in/Prydwen + pipeline F11 + tier list calculator + retro-feedback bayesiano).
- **Implementación de RF-14** (Fase 5.5 — migración `2026-04-XX_05_weapon_optimizer.sql` + modelado de pasivas estructuradas + scraper Prydwen weapons + scoring contextual + build full coordinado con RF-06).
- **Implementación móvil del dashboard** (post-v1, requiere arquitectura de sync DB).

> **Nota — RFs descartados de v1 (decisión abril 2026, DaniBOD):** RF-07 (farmeo diario gacha), RF-08 (analítica predictiva sets/armas) y RF-10 (Additional Abilities formales) quedan **fuera del alcance** del proyecto. Justificación: el farmeo diario lo cubre el usuario manualmente sin necesidad de automatización; la analítica predictiva queda funcionalmente cubierta por RF-13 (tier list calibrada de PJs) + RF-14 (rankings de armas) + RF-06 (rankings de discos); RF-10 queda subsumido por RF-12 (IA catalogadora cubre tanto Additional Abilities oficiales como sinergias emergentes con `fuente='ai_claude'`). Se preservan los IDs RF-07/08/10 vacíos para no renumerar los demás.

---

## 3. Requerimientos del Sistema

Esta sección consolida los requerimientos funcionales y no funcionales explícitamente solicitados por el usuario durante la fase de planificación del proyecto. Cada requerimiento incluye su justificación, alcance y dependencias.

> **Nota de alcance — Fase de planificación activa.** Los requerimientos RF-01, RF-02 y RF-03 son los cimientos de todo el sistema. No se avanza a Fase 2 hasta que estos tres estén **cerrados, validados y reforzados** (decisión explícita del usuario, abril 2026). Esta sección se actualiza conforme se refinan estos tres pilares.

### 3.1 Requerimientos Funcionales

#### RF-01 — Estado completo del roster (Fase 1)

- **Descripción:** El sistema mantiene el estado real de los 45 agentes: stats, arma equipada, 6 discos por agente, despertares desbloqueados y thresholds personalizados.
- **Alcance:** Cubre agentes, armas, sets, discos equipados, despertares, umbrales y el inventario equipado derivado.
- **Awakenings — semántica de la tienda Silueta Potencial:**
  - La tienda Silueta Potencial es donde se compran las siluetas para desbloquear niveles de awakening (los niveles 1-6 se activan conforme se acumulan siluetas).
  - Los awakenings son buffs aditivos que **sí impactan el daño/valor efectivo del agente** y deben considerarse en el scoring futuro.
  - **"Agotado"** en la tienda del jugador DaniBOD = silueta de ese agente comprada al límite máximo = **awakening completado (nivel 6 desbloqueado).**
  - **"Límite xN"** = awakening parcial, faltan N siluetas por comprar para completar.
  - **"En existencia" / "Límite alcanzado"** en ítems genéricos (Florescencia aurífera, Céfiros florecidos) = no son awakenings de agente, son ítems wildcard — se omiten de `agent_awakenings`.
  - **Bangbupón** = ítem wildcard, tampoco es awakening.
- **Estado de awakenings en roster DaniBOD (abril 2026):**
  - ✅ Completo (nv6): Burnice (cargado en DB), Lycaon, N.° 0: Anby, Ellen, Grace (pendientes de cargar)
  - 🔶 Parcial: Asaba Harumasa, N.° 11 (pendiente definir nivel exacto)
  - ⏳ El resto del roster S-rank con awakening disponible aparecerá en futuras rotaciones de la tienda
- **Estado:** ✅ Stats/armas/discos/thresholds completos. 🔄 Awakenings: 1/7 con texto verificado (Burnice nv6 *"Boiling Point Party"*) + 4 con placeholder `pending_capture` (Lycaon, Ellen, Grace, N.° 0: Anby — confirmados Agotado en tienda); falta capturar texto in-game de los 4 placeholders y resolver nivel exacto de Harumasa y N.° 11.

#### RF-02 — Inventario completo de discos (equipados + no equipados)

- **Descripción:** El sistema almacena cada disco en poder del usuario en `inventory_discs`, distinguiendo discos equipados (`equipado=1` + `agente_asignado` FK) de discos sueltos (`equipado=0` + `agente_asignado=NULL`).
- **Alcance:** Incluye metadatos completos por disco (set, slot, main stat, 4 substats con rolls, nivel), score de evaluación, lista de agentes compatibles en JSON, flag `descartado` y `notas` libres.
- **Fuente de datos:** Screenshots del usuario. El usuario está armando una carpeta externa con los discos no equipados para cargarlos en lote.
- **Criterios de cierre (todos deben cumplirse):**
  1. Total de filas en `inventory_discs` ≈ capacidad total visible en el inventario del juego (límite actual ZZZ: 1500 discos).
  2. `SELECT COUNT(*) FROM inventory_discs WHERE equipado=1` debe coincidir exactamente con `SELECT COUNT(*) FROM agent_discs WHERE main_stat <> 'EMPTY'` (= 257 hoy).
  3. Cada disco equipado debe tener `agente_asignado` no nulo y FK válida.
  4. Integridad referencial: 0 errores de FK, 0 violaciones de CHECK.
  5. Campos `score_evaluacion` y `agentes_compatibles` pueden quedar NULL en esta fase (se poblarán en Fase 2).
- **Estado:** Equipados ✅ 257/257. No equipados ✅ 75/75 cargados desde `Discos_Inventario_faltantes/` (abril 2026). Total `inventory_discs` = 332. Integridad OK. Score y compatibilidad: schema listo tras la migración `2026-04-24_01` (tabla `inventory_disc_evaluations` creada); cálculo automático pendiente del scoring engine de RF-06.

#### RF-03 — Inventario completo de W-Engines (equipadas + no equipadas)

- **Descripción:** Equivalente a RF-02 pero para armas. `inventory_weapons` trackea cada copia en inventario con su nivel, refinamiento y asignación.
- **Alcance:** Incluye fecha de obtención, notas, flag de equipado y asignación al agente actual si aplica.
- **Fuente de datos:** Screenshots del inventario de armas del usuario.
- **Criterios de cierre (todos deben cumplirse):**
  1. Total de filas en `inventory_weapons` = cantidad real de W-Engines que posee el usuario en su inventario (incluyendo duplicados, ya que cada copia puede tener distinto refinamiento o estar en distinto agente).
  2. `SELECT COUNT(*) FROM inventory_weapons WHERE equipado=1` ≤ 45 (un arma por agente máximo) y coincide con agentes que tienen weapon_id ≠ 45.
  3. Cada fila con `equipado=1` debe tener `agente_asignado` único (un arma no puede estar en dos agentes).
  4. `refinamiento` entre 1 y 5 (CHECK constraint).
  5. Integridad referencial: 0 errores de FK.
- **Estado:** Equipadas ✅ 40/40. No equipadas ✅ 10/10 cargadas desde `Armas_Inventario_faltantes/` (abril 2026). Total `inventory_weapons` = 50. 4 nuevas W-Engines añadidas al catálogo (Street Superstar, Florescencia aurífera, Wild Gastronome, Hertz Transit).

#### RF-04 — Sincronización automática al cambiar discos en el juego ⭐

- **Descripción:** Cuando el usuario equipa/desequipa un disco en un agente dentro de ZZZ, el sistema detecta el cambio y actualiza `inventory_discs.agente_asignado`, `inventory_discs.equipado` y `agent_discs` en consecuencia, sin intervención manual.
- **Mecanismo propuesto:** Detección por screenshot periódico de la pantalla de "Drive Discs" + diff contra el estado conocido en DB. Alternativa: escaneo bajo demanda activado por hotkey.
- **Reglas:**
  - Si un disco pasa de `agente_asignado=X` a `agente_asignado=Y`, actualizar `agent_discs` de ambos agentes (Y recibe, X queda con slot EMPTY hasta nueva asignación).
  - Si un disco se desequipa sin reemplazo, el agente pierde ese slot (`agent_discs.main_stat='EMPTY'`).
  - Cada cambio registra timestamp en columna de auditoría.
- **Estado:** 🟦 Diseño cerrado (abril 2026) — `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` define máquina de estados, polling adaptativo (500 ms detalle / 2-5 s menús), pipeline de evaluación §11 y diagramas v2 (`RF-04_v2_captura_discos.svg` con nodos build-match → arquetipo → recomendación). Implementación pendiente bajo `app/core/sync_equip.py` (RF-11).

#### RF-05 — Sincronización automática al mejorar discos ⭐

- **Descripción:** Cuando el usuario sube el nivel de un disco (0→3→6→9→12→15), los substats ganan rolls nuevos o aumentan valor. El sistema detecta el cambio de nivel y actualiza `inventory_discs` (substats, rolls, nivel) y `agent_discs` si está equipado, sin intervención manual.
- **Reglas:**
  - Nivel `n→n+3` añade/mejora un substat. Si era un `subN` vacío, se popula. Si ya tenía 4 substats, incrementa `rollsN` de alguno existente.
  - Cambios se propagan automáticamente a cualquier evaluación/score dependiente.
- **Estado:** 🟦 Diseño cerrado (abril 2026) — `RF-Logic_Captura_Discos.md` cubre los dos orígenes (modal desde Agente/Inventario vs. pantalla completa Tienda Música), decisión "¿sub4 ya estaba desbloqueada al PRE?" y diff PRE/POST con tres salidas (sub_unlocked, sub_rolled, multi_rolls); diagrama `RF-05_v2_upgrade_disco.svg`. Implementación pendiente bajo `app/core/sync_upgrade.py` (RF-11).

#### RF-06 — Optimizador de build por personaje (Fase 2)

- **Descripción:** Dado un PJ del roster, retorna las **top 3 builds** rankeadas (combinaciones de 6 discos del inventario) con score numérico, desglose por categoría y delta vs build actual.
- **Documento de diseño completo:** [`Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md`](./Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md) — cubre algoritmo, scoring, triggers, performance y output.
- **Decisiones cerradas (abril 2026):**
  - **Alcance:** build completa de 6 slots desde cero. Swap individual se deriva como caso particular del output.
  - **Exclusividad:** propone discos equipados en otros PJs marcados como "swap entre PJs" con `delta` dual (qué pierde el PJ origen, qué gana el PJ destino, neto). Cadenas de swap longitud 1 en v1.
  - **Algoritmo:** greedy por slot (top-K candidatos por score local) + bonus pass para optimizar set bonus (4pc / 2+2+2 / 3+3). Latencia esperada <500 ms para inventario actual (332 discos), <1 s para 1500.
  - **Trigger:** manual desde panel del PJ + automático tras captura de RF-04 cuando un disco con `score ≥ threshold_equip` cambia la mejor build. Debounce 2 s por PJ.
  - **Output:** top 3 builds en JSON con desglose por slot, set bonus aplicado, swaps requeridos y delta vs build actual.
- **Scoring engine compartido con RF-04 §11** — misma fórmula `positivos × (1 + rolls·0.25) − |perjudiciales| × (1 + rolls·0.5) + bonus_main_arquetipo + bonus_nivel`. Vive en `app/core/scoring.py`, invocado por evaluador de capturas y por optimizador.
- **Tabla nueva pendiente:** `optimizer_pending_actions` (migración `2026-04-XX_02_optimizer_pending.sql`) para "marcar build como TODO" hasta que RF-04 confirme su aplicación en el juego.
- **Estado:** 🟦 **Diseño cerrado (abril 2026)**. Implementación pendiente:
  1. Seed de `agent_substat_preferences` desde Prydwen (~225 filas, 45 PJs × ~5 substats)
  2. Migración `2026-04-XX_02_optimizer_pending.sql`
  3. `app/core/scoring.py` (engine compartido)
  4. `app/core/optimizer.py` (greedy + bonus pass)
  5. `app/ui/build_optimizer_view.py` (modal con tabs por build)
  6. Integración auto-trigger con RF-04

#### RF-09 — Análisis de imagen de disco (módulo intercambiable)

- **Descripción:** Módulo de visión que recibe un screenshot de un disco y retorna su data estructurada (set, slot, main stat, substats, nivel).
- **Requerimiento arquitectónico:** el backend de visión debe ser intercambiable (Claude API / GPT-4o / Tesseract / PaddleOCR) vía interfaz abstracta.
- **Estado:** 🟦 Decisión tomada (abril 2026) — backend OCR híbrido **Tesseract** (texto: nombre del set, slot, nombres de stat) + **PaddleOCR** (números: valores de main/sub, rolls `+N`), expuestos vía interfaz abstracta (`app/core/ocr_backend.py` con implementaciones `ocr_tesseract.py` y `ocr_paddle.py`). Permite swap futuro a Claude/GPT-4o vision si la precisión no alcanza. Implementación pendiente — primer hito de RF-11.

#### RF-11 — UI/UX del programa standalone (.exe)

- **Descripción:** Aplicación de escritorio unificada que consume el pipeline de captura/evaluación (RF-04/05/06/09) y presenta al usuario en tiempo real las recomendaciones sobre discos, además de alojar el dashboard histórico y la configuración. Es la única superficie que Daniel ve mientras juega.
- **Principio rector:** **latencia percibida < 500 ms** desde que el disco aparece en pantalla del juego hasta que el toast aparece en el escritorio. Daniel sube discos a nivel 15 en pocos segundos; si la UI llega tarde, no tiene valor.
- **Stack técnico — Python + PySide6 (Qt) empaquetado con PyInstaller (decisión abril 2026):**
  - Permite el pipeline completo dentro del mismo proceso: captura (`mss`), OCR (Tesseract/Paddle), SQLite, scoring, UI. Sin IPC entre procesos separados.
  - Qt provee widgets nativos para overlay semitransparente, tray icon, atajos globales (`QShortcut` + `pynput` para hotkeys fuera de foco), tablas grandes (`QTableView` con modelos), gráficos (`QtCharts` o `pyqtgraph`).
  - Binario esperado ~60-80 MB tras PyInstaller (incluye modelos OCR). Arranque frío < 2 s.
  - Alternativas evaluadas y descartadas: Tkinter (UX pobre), Electron (binario grande, RAM alta compitiendo con ZZZ), Rust+Python sidecar (complejidad de IPC no justificada en v1).
- **Arquitectura de la UI — tres superficies:**
  1. **Tray persistente (siempre):** ícono en system tray. Menú: *Abrir panel · Pausar captura · Configuración · Salir*. La app vive aquí mientras ZZZ esté corriendo.
  2. **Toast flotante (disparo por evento):** widget `QFrame` sin bordes, always-on-top, esquina inferior derecha del monitor principal. Tamaño ~360×110 px. Contenido: icono de recomendación (🟢 Equipar / 🔵 Mejorar / 🟡 Reserva / 🔴 Descartar), set + slot + main stat, PJ target o arquetipo, score, barra de urgencia. Auto-fade a los 5 s; click lo expande al panel de detalle, hover lo congela.
  3. **Panel de detalle / dashboard (on demand):** ventana principal con pestañas. Se abre al click en el toast, desde el tray, o con hotkey `F9`. Pestañas:
     - **Captura en vivo** — último disco capturado con desglose completo del scoring (positivos × rolls, perjudiciales × rolls, threshold del PJ, alternativas).
     - **Histórico** — tabla navegable de `inventory_disc_evaluations` con filtros (fecha, recomendación, PJ, set, arquetipo), paginación y búsqueda.
     - **Roster** — vista resumen de los 45 PJs: thresholds cumplidos, slots que necesitan upgrade, % de build completado.
     - **Catálogos** — arquetipos, sets clasificados, substat preferences por PJ (editable).
     - **Configuración** — todo lo del punto siguiente.
- **Criterio de disparo del toast — solo acciones rentables (decisión abril 2026):**
  - ✅ Dispara toast: `Equipar`, `Mejorar` (con delta positivo), `Reserva` con `score ≥ threshold_stock` del arquetipo.
  - 🔕 Silencia toast: `Descartar`, `Reserva` marginal (score entre 0.5× y 1× threshold). Estas quedan en el histórico sin interrumpir.
  - Esta política se puede relajar en Configuración (ver más abajo) si Daniel quiere modo "ver todo".
- **Configuración del usuario (persistida en `user_config.toml`):**
  - `threshold_equip` / `threshold_upgrade` por PJ (override sobre `agent_score_thresholds`).
  - `substat_preferences` por PJ editables inline (fuente `daniel` vs. `prydwen` / `default_archetype`).
  - Modo de toast: `accionables` (default) / `todas` / `silencioso` (solo tray badge).
  - Posición del toast: esquina (`bottom-right` default), monitor destino.
  - Hotkeys reasignables: captura manual (F8), abrir panel (F9), toggle pausa (F10).
  - Autostart con Windows (opcional, off por default).
  - Tema oscuro/claro (default: oscuro para no quemar vista durante juego).
- **Hotkeys globales (funcionan aunque ZZZ tenga el foco):**
  - `F8` — captura manual (forzar análisis del frame actual).
  - `F9` — alternar panel de detalle.
  - `F10` — pausar/reanudar captura automática.
  - `Ctrl+Shift+Z` — emergencia: cerrar la app desde cualquier estado.
- **Arranque y ciclo de vida:**
  - Lanzar `.exe` → inicializa DB, carga catálogos, arranca loop de captura, aparece icono tray + splash silencioso 1 s.
  - Detecta `ZenlessZoneZero.exe` como proceso → activa polling adaptativo (500 ms en pantallas de disco, 2-5 s en menús). Si ZZZ no está corriendo, captura en pausa.
  - Cerrar ventana → va al tray (no termina). Salir real sólo desde menú tray o `Ctrl+Shift+Z`.
- **Performance objetivo:**
  - Latencia detección → toast visible: **< 500 ms** (presupuesto: captura 50 ms + clasificador 80 ms + OCR 180 ms + scoring 20 ms + render 50 ms + margen).
  - RAM residente en idle: < 200 MB. Mientras procesa un disco: pico < 400 MB.
  - CPU en polling: < 3 % single core idle, < 15 % pico durante OCR.
- **Accesibilidad:**
  - Textos escalables (Qt `QSettings.fontPointSize`).
  - Atajos de teclado para todas las acciones (sin requerir ratón).
  - Feedback sonoro opcional al disparar toast (wav corto, togglable).
- **Empaquetado y distribución:**
  - `pyinstaller --onefile --windowed --icon=icon.ico main.py` con spec-file para incluir templates OCR, catálogos seed y schema.
  - Instalador liviano NSIS opcional (para registrar el arranque con Windows y crear accesos directos); si no, el `.exe` único es portable.
  - Primera ejecución: asistente de 3 pasos (seleccionar carpeta DB, calibrar ROIs de OCR capturando ejemplo, registrar hotkeys).
- **Dependencias con otros RF:**
  - Consume: RF-04 (captura), RF-05 (upgrade), RF-06 (optimizador de build), RF-09 (OCR), más las 5 tablas de scoring creadas en la migración `2026-04-24_01_archetypes_and_scoring.sql`.
  - Provee: superficie única de I/O para el usuario (no hay CLI ni web separada en v1).
- **Alcance explícitamente diferido a v2+:**
  - Versión móvil del dashboard (requiere sincronización de DB, arquitectura distinta).
  - Integración con Discord/Telegram para alertas remotas.
  - Temas comunitarios / skins.
  - Modo multi-cuenta (otros UIDs además de DaniBOD).
- **Estado:** 📋 Diseño cerrado (abril 2026). Implementación pendiente — arranca una vez que RF-09 tenga el backend OCR elegido y que los evaluadores de RF-06 estén implementados.

#### RF-12 — Optimizador de build con contexto de equipo (IA catalogadora)

- **Descripción:** Extensión de RF-06 que ajusta la build óptima de un PJ en función de los compañeros del equipo. La composición puede modificar **(a)** los pesos de substats, **(b)** el set recomendado o **(c)** sugerir directamente el equipo óptimo donde un PJ rinde mejor. Caso paradigmático: **Ellen Joe** se juega normalmente con *Tecno Pícido* (Polar Metal en EN) por daño de hielo; pero al pairing con **Dialyn**, el set óptimo cambia a **Puffer Electro** porque la Core Skill de Dialyn otorga una Ultimate adicional que se beneficia del bonus de energía/electric del set.
- **Documento de diseño completo:** [`Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md`](./Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md) — cubre alcance v1, modelo de datos (3 tablas nuevas), prompts a Claude API, runtime, costos y output JSON.
- **Decisiones cerradas (abril 2026):**
  - **Alcance v1 — 3 capas:** *(1)* override de pesos de substats por composición, *(2)* override del set recomendado, *(3)* sugerir el equipo óptimo donde un PJ específico rinde mejor (top-N composiciones).
  - **Rol de la IA — catalogadora, no decisora:** Claude API (sonnet para pares, opus para composiciones complejas) puebla las tablas de sinergias y composiciones offline. El optimizador en runtime es 100% determinista — solo lee la DB. Esto mantiene el algoritmo predecible, cacheable y barato (<$10/mes esperado para uso normal).
  - **Refresh:** *on-demand* desde panel de equipo + *automático* cuando se detecta un PJ nuevo en el roster o un set nuevo en el catálogo. Cap de costo configurable en `user_config.toml` (default $5/mes).
  - **Modelo IA + RAG:** Claude API con prompt caching (sistema cacheable: roster completo + catálogo de sets + descripciones de habilidades) y RAG sobre Prydwen.gg para reducir alucinaciones. Modelo de sinergias también responde "no hay sinergia" cuando aplica (flag `sinergia_existe=0`).
- **Modelo de datos — 3 tablas nuevas (migración `2026-04-XX_03_team_synergies.sql`):**
  - `team_synergies` — pares ordenados (pj_a_id < pj_b_id) con flag `sinergia_existe`, `tipo` (`disorder_elemento` / `additional_ability_faccion` / `core_passive_ult` / etc.), set recomendado por PJ, override JSON de pesos de substats, descripción del buff, `confianza`, `fuente`, `modelo_version`. UNIQUE(pj_a, pj_b). Espacio: 990 pares posibles (C(45,2)), expectativa ~300 con sinergia activa.
  - `team_compositions` — top-N composiciones de 3 PJs por personaje principal con `score_composicion`, `rank_para_principal`, `contenido_optimo` (Shiyu/Hollow Zero/...), `justificacion`, `sinergias_activadas`, `requiere_stunner`, `flag_anti_shill` (true cuando la composición es objetivamente mejor que la "shilleada" por la comunidad).
  - `ai_catalog_runs` — auditoría de cada llamada a la IA: `operacion`, `modelo`, `pj_ids`, `prompt_hash`, `tokens_input/output`, `costo_usd`, `duracion_ms`, `exito`, `error_msg`, `response_json`. Permite calcular costo acumulado y detectar retries.
- **Algoritmo runtime — 3 capas sobre RF-06:**
  1. Recibir `pj_id` + `team_context` (lista de hasta 2 compañeros).
  2. Capa A: buscar overrides en `team_synergies` para los pares (pj, comp1) y (pj, comp2). Aplicar override de pesos al scoring engine; si dos pares overridean la misma stat, ponderar por `confianza`.
  3. Capa B: buscar override de set en los mismos pares. Si existe y `confianza ≥ umbral`, sustituir el set objetivo del optimizador.
  4. Capa C (nuevo flujo "sugerir equipo"): consulta `team_compositions` por `pj_principal_id = pj_id`, retorna top-N rankeadas con justificación.
  5. Invocar RF-06 con los pesos y set ya ajustados → top 3 builds.
- **Trigger y refresh:**
  - **On-demand:** botón "Recatalogar sinergias de [PJ]" en panel de equipo (cost preview antes de confirmar).
  - **Automático:** cuando RF-04 detecta un PJ nuevo en el roster o se inserta un set nuevo, encolar refresh para los 44 pares afectados (queue persistente, batched para reusar prompt caching).
  - **Cap de costo:** lee `user_config.toml::ai_catalog.cap_usd_mensual`; si se excede, pausa la cola y notifica.
- **Performance y costos esperados:**
  - Latencia runtime con DB poblada: < 50 ms (dos lookups a `team_synergies` + lookup a `team_compositions`).
  - Costo por par sinergia: ~$0.012 (sonnet, ~3K tokens cached + ~500 nuevos). 990 pares ≈ $12 one-time.
  - Costo por composición top-5: ~$0.18 (opus, prompt más complejo). 45 PJs × top-5 ≈ $8 one-time.
  - Refresh trimestral completo (rebalance del juego): ~$21 cada vez. Uso normal proyectado < $10/mes con prompt caching activo.
- **UI integration:**
  - Nueva pestaña "Equipos" en el panel de RF-11 con: vista de pares con/sin sinergia (filtros por elemento/facción), top-N composiciones por PJ, justificaciones expandibles.
  - Toggle en el optimizador de build (RF-06): *"Considerar equipo: [PJ1] + [PJ2]"* con autocomplete del roster. Sin selección, opera como RF-06 base.
- **Dependencias:** consume RF-06 (scoring engine + optimizador base), RF-04 (detección de PJ nuevo en roster), RF-11 (superficie UI). Cubre tanto Additional Abilities oficiales como sinergias emergentes (combos de elementos, ult-stacking, etc.) con `fuente='ai_claude'` en `team_synergies`. Subsume al ex-RF-10 (descartado en v1).
- **Estado:** 🟦 **Diseño cerrado (abril 2026)**. Implementación pendiente:
  1. Migración `2026-04-XX_03_team_synergies.sql` (3 tablas + índices)
  2. `app/core/ai_catalog.py` (cliente Claude API + prompt caching + retries)
  3. `app/core/team_optimizer.py` (lookups + integración con RF-06)
  4. `app/ui/teams_view.py` (nueva pestaña + toggle en build_optimizer_view)
  5. Seed inicial: 990 llamadas a `team_synergy_pair` + 45 a `team_composition_topN` (~$21)
  6. Integración del cap de costo + dashboard de uso de IA (lee `ai_catalog_runs`)
  7. Auto-encolado al detectar PJ/set nuevo desde RF-04
  8. Caso de prueba documentado: Ellen + Dialyn → Puffer Electro debe aparecer en `team_synergies` con `confianza ≥ 0.85` y `tipo='core_passive_ult'`.

#### RF-13 — Validación lategame + tier list personal calibrado

- **Descripción:** Registra runs reales de **contenido lategame** (Shiyu Defense Critical, Deadly Assault) mediante captura manual + OCR del breakdown DMG, deriva una **tier list personal calibrada** comparada contra Prydwen, y cierra el loop con RF-12 ajustando `team_synergies.confianza` por evidencia bayesiana. Resuelve el gap "Prydwen asume M0/build óptima/composición canónica; mi cuenta diverge en múltiples ejes simultáneos".
- **Documento de diseño completo:** [`Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md`](./Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md) — cubre las 3 capas, modelo de datos (8 tablas), pipeline de captura, algoritmo del tier list, retro-feedback bayesiano, scrapers, output y log de decisiones.
- **Decisiones cerradas (abril 2026):**
  - **Granularidad de captura:** *Resultado + breakdown DMG* — hotkey `F11` captura resumen + Battle Stats; OCR híbrido (Tesseract texto + PaddleOCR números) extrae equipo, estrellas, tiempo y % DMG por agente.
  - **Modelo de enemigos:** *Tabla rica + scraping* (`enemies`, `enemy_resistances`, `shiyu_cycles`, `da_cycles`) poblados desde Hakush.in (datamine cuantitativo) y Prydwen Shiyu Analytics (ciclos activos). Refresh: enemies cada patch (~6 sem), ciclos cada 2 sem.
  - **Tier list output:** *Por contenido + delta vs Prydwen* — un ranking por Shiyu, otro por DA, opcional por elemento del frente. Cada PJ muestra delta vs Prydwen con justificación textual autogenerada (ej. *"Yanagi sube de S a S+ atribuible a M2 + Tecno Pícido 4pc, rate 3★ 94% vs típico 80%"*).
  - **Feedback loop:** *Loop completo bayesiano* — runs reales ajustan `team_synergies.confianza` con prior IA + likelihood empírica capada en 1.5. Sinergias mal validadas dejan de aplicarse automáticamente al cruzar `confianza < 0.70`. Override manual con flag `congelado=1`.
  - **Buckets de tier:** **fijos** (S+ ≥90, S 80-89, A 65-79, B 50-64, C 30-49, D 0-29) — no cuartiles, para que el tier refleje progresión real del meta sin deformación por curve fitting.
  - **Trigger del recálculo:** N=3 runs nuevos + semanal (domingos 03:00) + on-demand desde panel.
  - **Snapshots atómicos** del tier list: cada recálculo genera nuevo `snapshot_id`, no UPDATE. Permite auditar evolución temporal sin pérdida.
- **Modelo de datos — 8 tablas nuevas (migración `2026-04-XX_04_lategame_validation.sql`):**
  - `enemies` + `enemy_resistances` — catálogo de bosses/notorious con HP base, escalado por dificultad, resistencias por elemento.
  - `shiyu_cycles` + `da_cycles` — ciclos rotativos con frentes/entidades en JSON, fuente, fechas.
  - `lategame_runs` + `lategame_run_damage` — registro primario de evidencia: equipo, contenido, ciclo, estrellas, tiempo, breakdown DMG por agente.
  - `tier_list_personal` — tabla calculada (no view) con histórico atómico de snapshots. Campos: tier, score_normalizado, métricas agregadas, delta_vs_prydwen, justificacion.
  - `prydwen_tier_snapshots` — snapshots semanales de la tier list general de Prydwen para comparativos históricos.
  - `team_synergy_adjustments` — auditoría del retro-feedback: cada ajuste de `team_synergies.confianza` queda trazado con motivo bayesiano + métricas que lo justificaron.
- **Pipeline de captura:** Daniel termina un run → `F11` → 2 screenshots (resumen + Battle Stats) → OCR + validación de consistencia (suma DMG ≈ 100%, PJs coinciden con roster) → insert en `lategame_runs` + `lategame_run_damage` → toast confirma → si `runs_nuevos ≥ 3`, dispara recálculo de tier list → notificación de cambios.
- **Algoritmo tier list calibrado:** sobre los últimos K=20 runs (mín K_min=3), calcula `rate_3star`, `win_rate`, `avg_dmg_share` (normalizado por rol esperado), `avg_tiempo_normalizado`. Score = combinación lineal (pesos: 3★ 0.45 / win 0.20 / dmg 0.20 / tiempo 0.15). Asigna tier por buckets fijos. Calcula delta vs `prydwen_tier_snapshots` más reciente. Genera justificación con plantilla parametrizada según el delta.
- **Retro-feedback bayesiano:** cuando un equipo recomendado por RF-12 acumula ≥3 runs, recalcula `confianza_post = peso_prior × confianza_ai + peso_evidencia × likelihood_observada`, donde `peso_prior = 1/(1 + 0.3 × runs_evidencia)`. Caso ejemplo Ellen+Dialyn: confianza IA=0.85, 5 runs con rate_3★=0.20 → confianza_post=0.50 → RF-12 deja de aplicar override automáticamente.
- **Performance:** OCR + insert <1.5s; recálculo full tier list (45 PJs × 3 contenidos) <3s; lookup retro-feedback <200ms. Sin requerimientos de tiempo real (RF de análisis, no de toast crítico).
- **Dependencias:** consume RF-12 (modifica `team_synergies.confianza`), RF-09 (reutiliza backend OCR), RF-11 (hotkey F11 + nueva pestaña "Lategame" con 5 subpestañas: Runs recientes, Tier List Personal, Comparativo Prydwen, Histórico, Ciclos).
- **Estado:** 🟦 **Diseño cerrado (abril 2026)**. Implementación pendiente:
  1. Migración `2026-04-XX_04_lategame_validation.sql` (8 tablas + índices + flag `congelado` en `team_synergies`).
  2. `app/scripts/scrape_enemies.py` (Hakush.in + Prydwen) + carga inicial ~80 enemigos.
  3. `app/scripts/scrape_prydwen_tierlist.py` + snapshot inicial (45 PJs × 3 contenidos).
  4. `app/core/lategame_capture.py` — pipeline OCR del breakdown DMG.
  5. `app/core/tier_list_calculator.py` — algoritmo de scoring + buckets + delta vs Prydwen.
  6. `app/core/retro_feedback.py` — ajuste bayesiano de confianza.
  7. `app/ui/lategame_view.py` — pestaña con 5 subpestañas + indicador `±RF-13` en panel de Equipos.
  8. Hotkey global F11 + asistente "calibrar ROIs del breakdown DMG" en primer uso.
  9. Tests E2E + validación cruzada con 20 runs reales antes de soltar el retro-feedback automático.

#### RF-14 — Optimizador de armas (W-Engines) con scoring contextual

- **Descripción:** Cierra el repertorio del optimizador (junto a RF-06 discos / RF-12 equipo / RF-13 validación). Para cada PJ produce un **ranking ideal** del catálogo completo (49 W-Engines) y un **ranking disponible** sobre el inventario real, con scoring sensible al contenido (Shiyu / DA / Hollow Zero / general). Resuelve el caso "la roca" (Núcleo Fosilizado Precioso, S-rank Stunner con +Impact% mientras HP enemigo > 50%): Prydwen la marca como "S general", pero su uptime real es 95% en DA (S+ personal) y 30% en Hollow Zero (B personal). Sin contexto, el ranking pierde su valor principal.
- **Documento de diseño completo:** [`Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md`](./Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md) — cubre alcance, modelo de datos (5 tablas nuevas), algoritmo de scoring, build full RF-06+RF-14, integración con RF-12/13, scraping Prydwen, output JSON y log de decisiones.
- **Decisiones cerradas (abril 2026):**
  - **Alcance v1:** *Ranking ideal + ranking disponible + build full coordinada con RF-06* (3 entregables).
  - **Modelado de pasivas:** *híbrido estructurado + texto fallback* — `weapon_passives_structured` con `trigger_tipo` (15 categorías: `always`, `enemy_hp_above`, `on_chain_attack`, `team_has_element`, etc.) + `modifier_stat` + `modifier_value_r1/r5` + `uptime_base`. Pasivas no modeladas usan `score_pasiva_textual` con override manual del usuario.
  - **Contexto del contenido:** *por contenido + delta vs Prydwen* — perfiles `content_profiles` con TTL boss promedio, uptime HP>50%, chain attacks/min, skills/min, ultimates/min, anomalies/min. Uptime real de cada pasiva se calcula contra el perfil del contenido.
  - **Integración:** *coordinada con RF-06 (build full)* + hooks con RF-12 (uptime de triggers `team_has_*`) y RF-13 (recalibración bayesiana de `content_profiles` desde runs reales).
  - **Pesos del scoring:** ATK 25 / stat secundario 15 / pasiva estructurada 40 / pasiva textual 10 / sinergia con habilidades core 10 = 100 pts. La pasiva pesa más porque define la identidad del W-Engine.
  - **Refinamiento:** interpolación lineal R1↔R5 (error <5%, override manual disponible para escalados no-lineales).
- **Modelo de datos — 5 tablas nuevas + extensión a `weapons` (migración `2026-04-XX_05_weapon_optimizer.sql`):**
  - `weapon_passives_structured` — modelado formal de cada efecto de pasiva (trigger + modifier + valor R1/R5 + uptime base). UNIQUE(weapon_id, modifier_stat, trigger_tipo) permite pasivas multi-efecto.
  - `content_profiles` — caracteriza Shiyu/DA/Hollow Zero/general con TTL boss, uptime HP>50%, frecuencias de eventos. Seed inicial calibrada manualmente, recalibrable por RF-13.
  - `weapon_evaluations` — cache + histórico de scores por (pj, weapon, refinamiento, contenido, snapshot_id). Lookup directo <5 ms.
  - `prydwen_weapon_recommendations_snapshots` — snapshot semanal de recomendaciones de armas por PJ desde Prydwen, para cálculo de delta.
  - `pj_weapon_synergy` — seed manual ~180 filas (45 PJs × 4 tipos de pasiva relevantes) con `bonus` y `razon`. Carga inicial asistida por Claude API (~$3 estimado).
  - `weapons` extendida con `pasiva_modelada` (0/1/2) y `sensibilidad_contexto` (baja/media/alta).
- **Algoritmo de scoring (`app/core/weapon_scoring.py`):**
  ```
  score = score_atk_base + score_stat_secundario
        + Σ (modifier × stat_impact_for_pj × uptime_contextual)
        + score_pasiva_textual + score_synergy_pj
  ```
  donde `uptime_contextual` se deriva del `trigger_tipo` y `content_profile` (ej. `enemy_hp_above 50` → `profile.hp_boss_uptime_above_50pct`).
- **Build full (`app/core/weapon_optimizer.py`):** pre-rank de 49 armas → top 3 candidatas → para cada una, RF-06 optimiza 6 discos → `score_combinado` con interacciones (CRIT overflow, thresholds de soporte, ER para Awakenings condicionales). Latencia <1.5 s.
- **Performance:** ranking 49 armas / 1 PJ / 1 contenido <100 ms; recálculo full (45 PJs × 49 armas × 4 contenidos = 8.820 evaluaciones) <8 s.
- **Dependencias:** consume `weapons` (RF-03, ya poblada con 49 entradas), `inventory_weapons` (50 cargadas), `agents` + `agent_thresholds`. Se coordina con RF-06 (build full), RF-12 (team-aware uptime), RF-13 (recalibración + retro-feedback). Sirve a RF-11 vía nueva pestaña "Armas" + toggle en build optimizer.
- **Estado:** 🟦 **Diseño cerrado (abril 2026)**. Implementación pendiente:
  1. Migración `2026-04-XX_05_weapon_optimizer.sql` (5 tablas + extensiones + seed `content_profiles`).
  2. Modelado inicial de pasivas (~80 filas en `weapon_passives_structured`) — carga manual asistida por Claude API one-time.
  3. Seed de `pj_weapon_synergy` (~180 filas) — Claude API one-time.
  4. `app/scripts/scrape_prydwen_weapons.py` + snapshot inicial.
  5. `app/core/weapon_scoring.py` (fórmula + uptime contextual).
  6. `app/core/weapon_optimizer.py` (rankings + build full).
  7. `app/ui/weapons_view.py` (4 subpestañas: Ranking por PJ, Build full, Catálogo, Comparativo Prydwen).
  8. Toggle "Optimizar también el arma" en `build_optimizer_view.py`.
  9. Editor admin de pasivas estructuradas.
  10. Hooks de integración con RF-12 (lectura `team_synergies` para uptime) y RF-13 (recalibración `content_profiles` + ajuste tier personal).
  11. Tests E2E: caso "la roca" debe rankear S+ en DA y B en HZ; armas con `trigger_tipo='always'` deben rankear igual en todos los contenidos.

### 3.2 Requerimientos No Funcionales

#### RNF-01 — ETL sin fallas

- **Regla de proyecto explícita.** Toda carga, migración o modificación de datos debe preservar integridad referencial, no perder información histórica y ser idempotente cuando sea posible.
- **Prácticas obligatorias:** `PRAGMA foreign_key_check` + `PRAGMA integrity_check` tras cada cambio masivo, backups puntuales antes de merges de IDs, `BEGIN TRANSACTION` + `COMMIT/ROLLBACK` en operaciones multi-tabla.
- **Evidencia requerida:** cada merge y carga debe dejar rastro auditable en este README (qué filas se afectaron, qué IDs se consolidaron).

#### RNF-02 — Análisis minucioso de datos

- **Regla de proyecto explícita.** No se aceptan shortcuts ni valores inventados. Cuando un dato no esté confirmado se marca como tentativo con fuente, o se deja NULL hasta validar.
- **Fuentes autorizadas:** Prydwen.gg, HoYoLAB (screenshots oficiales del jugador), Game8, IcyVeins, 141store, Fandom oficial.
- **Caso paradigmático:** la validación del set id=50 "Nana luz cenicienta" se resolvió cruzando screenshot del jugador contra 4 fuentes externas antes del merge final.

#### RNF-03 — Compatibilidad con ToS de HoYoverse

- El sistema NO inyecta código en el proceso del juego, NO lee memoria del juego, NO simula inputs, NO automatiza gameplay.
- Solo consume pixels visibles en pantalla (equivalente a Inventory Kamera para Genshin).

#### RNF-04 — Portabilidad

- DB en SQLite monolítica → permite sincronizar con móvil copiando un solo archivo.
- Código en Python puro donde sea posible para minimizar dependencias nativas.

#### RNF-05 — Extensibilidad por versiones del juego

- Awakenings tienen campo `version_juego` → cada patch puede añadir nuevos sin romper los anteriores.
- Sets y armas nuevas se agregan con nuevos `id` sin renumerar existentes.
- Thresholds aceptan valores `NULL` en `valor_maximo` cuando no hay cap útil.

#### RNF-06 — Responsividad del sistema

- **Regla de proyecto explícita.** Toda interacción del usuario con el sistema debe respetar presupuestos de latencia que mantengan la experiencia fluida durante el juego. La responsividad es una cualidad transversal: si la app llega tarde con la recomendación, no tiene valor.
- **Presupuestos de latencia por superficie (consolidados desde los RFs):**

  | Superficie | Latencia objetivo | Definido en |
  |-----------|-------------------|-------------|
  | Disco aparece en pantalla → toast visible (RF-04/05/09/11) | **< 500 ms** | RF-11 §Performance |
  | Captura → OCR de disco → scoring → render | < 380 ms (presupuesto interno) | RF-11 |
  | Optimizador de build (greedy + bonus pass, 332 discos) | **< 500 ms** | RF-06 |
  | Optimizador de build (proyectado a 1500 discos) | < 1 s | RF-06 |
  | Lookup runtime de RF-12 (`team_synergies` + `team_compositions`) | **< 50 ms** | RF-12 |
  | Captura + OCR del breakdown DMG (RF-13, manual) | < 1.5 s | RF-13 |
  | Recálculo full tier list personal (45 PJs × 3 contenidos) | **< 3 s** | RF-13 |
  | Snapshot de Prydwen (scrape + parse + insert) | < 5 s (background) | RF-13 |
  | Snapshot enemies/cycles (Hakush.in + Prydwen) | < 30 s (background, cada 2 sem) | RF-13 |
  | Score de 1 arma para 1 PJ en 1 contenido (RF-14) | **< 5 ms** | RF-14 |
  | Ranking de 49 armas para 1 PJ en 1 contenido (RF-14) | **< 100 ms** | RF-14 |
  | Build full RF-06+RF-14 (3 armas × 3 builds) | **< 1.5 s** | RF-14 |
  | Recálculo full weapon_evaluations (45 PJs × 49 × 4) | < 8 s (background) | RF-14 |
  | Snapshot Prydwen weapons (45 PJs) | < 90 s (background, semanal) | RF-14 |

- **Consumo de recursos en idle (RF-11):**
  - RAM residente: **< 200 MB** en idle, pico **< 400 MB** procesando un disco.
  - CPU en polling: **< 3%** single core idle, **< 15%** pico durante OCR.
  - Arranque frío del `.exe`: **< 2 s** desde double-click hasta tray icon visible.

- **Estrategias para sostener la responsividad:**
  - Polling adaptativo (500 ms en pantallas de disco, 2-5 s en menús; pausa total si ZZZ no está en foreground).
  - Lookups de RF-12 indexados (UNIQUE en pares ordenados, índice compuesto `(pj_principal, pj_companion_1, pj_companion_2)`).
  - Prompt caching de Claude API (RF-12) para reducir tanto costo como latencia de catalogación batch.
  - Recálculos pesados (tier list, retro-feedback bayesiano) corren fuera del thread de UI.
  - Scrapers (RF-13) son background jobs schedulados, jamás bloquean al usuario.

- **Evidencia requerida:** cada RF que toque el thread de UI debe documentar su presupuesto de latencia y, en implementación, exponer métricas (`latency_p50_ms`, `latency_p99_ms`) consultables desde un panel de diagnóstico.

### 3.3 Mapa Requerimientos ↔ Fases del Roadmap

| Fase | Nombre | Requerimientos involucrados | Estado |
|------|--------|-----------------------------|--------|
| **Fase 1** | Estado de personajes (discos, armas, habilidades) | RF-01, RF-02 (equipados), RF-03 (equipadas) | ✅ Completa (gaps menores en awakenings/thresholds) |
| **Fase 1.5** | Inventario completo equipado + no equipado | RF-02 (cierre), RF-03 (cierre) | ✅ Cerrada abril 2026 — 332 discos, 50 armas |
| **Fase 1.6** | Schema arquetipos + scoring + histórico de evaluaciones | Migración `2026-04-24_01` | ✅ Cerrada abril 2026 — 6 arquetipos, 26 sets clasificados, 45 thresholds |
| **Fase 2** | Captura automática + optimización de build de discos | RF-02, RF-03, RF-04, RF-05, RF-06, RF-09 | 🟦 Diseño cerrado (abril 2026), implementación pendiente |
| **Fase 3** | Optimizador team-aware con IA catalogadora | RF-12 | 🟦 Diseño cerrado (abril 2026), implementación pendiente |
| **Fase 4** | Validación lategame + tier list personal + retro-feedback bayesiano | RF-13 | 🟦 Diseño cerrado (abril 2026), implementación pendiente |
| **Fase 5** | Optimizador de armas (W-Engines) con scoring contextual + build full | RF-14 | 🟦 Diseño cerrado (abril 2026), implementación pendiente |
| **Transversal** | UI standalone `.exe` (PC) + futura móvil | RF-11 | 🟦 Diseño cerrado (abril 2026), implementación pendiente |
| ~~**Descartado**~~ | ~~Farmeo diario / Analítica predictiva / Additional Abilities formales~~ | ~~RF-07, RF-08, RF-10~~ | ❌ Fuera de alcance v1 (decisión abril 2026) |

### 3.4 Dependencias Críticas

```
RF-01 ──┬──► RF-02 ──► RF-04 ──► RF-06 ──┬──► RF-12 ──► RF-13
        │                │                │
        ├──► RF-03 ──────┤                ├──► RF-14
        │                │                │
        ├──► Thresholds ─┤                │
        │                │                │
        └──► Awakenings ─┘                └──► RF-11 (UI)

RF-09 (Análisis imagen) es precondición de RF-04 y RF-05
Migración 2026-04-24_01 (arquetipos + scoring) es precondición del scoring engine de RF-06/RF-11
RNF-01/02/06 son transversales (aplican a todos los RF; RNF-06 fija presupuestos de latencia para cada superficie)
RF-11 (UI standalone .exe) consume RF-04/05/06/09 + tablas de scoring; única superficie de I/O al usuario en v1
RF-12 (optimizador team-aware) extiende RF-06 con 3 tablas nuevas pobladas por Claude API; runtime determinista (lookup) usa RF-06 como motor base
RF-13 (validación lategame) cierra el loop sobre RF-12: runs reales en Shiyu/DA ajustan team_synergies.confianza por bayesiano y producen tier list personal calibrada vs Prydwen
RF-14 (optimizador de armas) coordina con RF-06 (build full = arma + 6 discos), lee team_synergies de RF-12 para uptime de triggers contextuales, y RF-13 recalibra sus content_profiles desde runs reales

Onboarding de PJ nuevo (Documentacion/Onboarding_Nuevo_PJ.md) atraviesa todas las capas: agents → thresholds → pj_weapon_synergy → team_synergies (44 pares IA) → splash art → wizard RF-11
```

---

## 4. Base de Datos — `danibod_zzz_v2.db`

### 4.1 Schema Completo

**`disc_sets`** — Catálogo de sets de discos (26 sets, post-merge)

Almacena todos los sets disponibles en el juego con sus bonuses estandarizados. Fuente: Prydwen.gg (última actualización 23/03/2026).

Campos: `id`, `nombre` (español), `nombre_en` (inglés), `bonus_2p_stat`, `bonus_2p_valor`, `bonus_4p_desc` (descripción completa del 4pc, texto libre porque es muy variable entre sets).

Sets incluidos: Voz Astral, Balada rama/espada, Conejo en el país de las maravillas, Jazz Caótico, Metal Caótico, Floración del alba, Metal Colmilludo, Blues Libre, Punk Hormonal, Metal Infernal, Monarca del Pináculo, Melodía lunar, Notas encadenadas, Melodía de Faetón, Polar Metal, Punk Primitivo, Puffer Electro, Armonía umbría, Aria brillante, Disco Sacudestrellas, Soul Rock, Jazz Oscilante, Metal Eléctrico, Tecno Pícido, Fábula Yunkui, Nana luz cenicienta, Balada de aguas blancas, y variantes localizadas.

---

**`weapons`** — Catálogo de W-Engines (49 armas)

Pasivas modeladas de forma semi-estructurada para permitir queries por tipo de efecto, no solo búsqueda textual.

Campos: `id`, `nombre`, `nombre_en`, `rareza` (S/A/B), `tipo_especialidad` (Ataque/Anomalía/Soporte/Defensa/Aturdimiento/Ruptura), `atk_base`, `stat_secundario`, `stat_secundario_valor`, `pasiva_tipo` (categoría: dmg_boost / anomaly_proficiency / energy_regen / crit / pen_ratio / atk_boost / mixed), `pasiva_condicion` (cuándo activa), `pasiva_valor` (valores clave resumidos), `pasiva_descripcion` (texto completo como fallback).

S-Rank incluidas: Flamemaker Shaker, Hailstorm Shrine, Fusion Compiler, Deep Sea Visitor, The Restrained, Timeweaver, Cloudcleave Radiance, Cannon Rotor, Practiced Perfection, Roaring Fur-nace, Half-Sugar Bunny, Thoughtbop, Bellicose Blaze, Heartstring Nocturne, Neon Fantasies, Elegant Vanity, Dreamlit Hearth, Spectral Gaze, Severed Innocence, Riot Suppressor Mk VI, Myriad Eclipse, Angel in the Shell, Flight of Fancy, Sharpened Stinger, Metanukimorphosis, Kraken's Cradle, Qingming Birdcage, Blazing Laurel, Cordis Germina, Steel Cushion, The Brimstone, y más. A-rank relevantes también incluidas.

---

**`agents`** — Agentes del roster (45/45)

Stats efectivos tomados directamente de HoYoLAB con screenshots del jugador. No son stats base — incluyen el efecto del arma y los discos equipados.

Campos de identificación: `id`, `nombre`, `rango` (S/A), `nivel`, `mindscape` (0-6), `elemento`, `rol`, `faccion`.

Campos de stats: `pv`, `ataque`, `defensa`, `impacto`, `prob_critico`, `dano_critico`, `tasa_anomalia`, `maestria_anomalia`, `tasa_perforacion`, `perforacion`, `rec_energia`, `bono_dano_elemento`.

Equipo: `weapon_id` (FK → weapons), `weapon_nivel`, `weapon_rango` (refinamiento), `set_4p_id` (FK → disc_sets), `set_2p_id` (FK → disc_sets), `disco6_main`, `notas`.

---

**`agent_awakenings`** — Visiones de Despertar / Potencial

Los despertares son buffs que los devs agregan a personajes existentes en cada versión del juego (sistema implementado en v2.5). Son escalables — cada versión puede agregar nuevos a más personajes. El campo `version_juego` permite trackear cuándo se incorporó cada uno y facilita actualizaciones futuras.

Campos: `id`, `agente_id` (FK), `nivel` (1-6), `nombre`, `descripcion` (efecto completo), `tipo_efecto` (stat_boost / cooldown_reduction / new_mechanic), `activo` (bool), `version_juego`.

Cargado actualmente: Burnice nivel 6 — *"Boiling Point Party"* (v2.5): Con ER inicial ≥1.8, cada 0.1 extra de ER otorga +2.5 Anomaly Mastery y +2% DMG (máx +25 AM / +20% DMG). Afterburn interval reducido a 1.35s.

**Criterio de carga:** Un awakening se carga en DB cuando el usuario confirma el contenido textual desde el menú de awakening del agente (screenshot). No se infieren efectos desde guías externas a menos que el usuario lo apruebe explícitamente — aplica **RNF-02 (análisis minucioso, cero shortcuts)**.

Pendiente de carga (DaniBOD tiene awakening completo nv6, falta data textual):
- Lycaon
- N.° 0: Anby
- Ellen
- Grace

Pendiente de carga (DaniBOD tiene awakening parcial, falta definir nivel + data):
- Asaba Harumasa
- N.° 11

Impacto en el modelo: los awakenings contribuyen al scoring efectivo del agente (RF-06/RF-14). El motor de evaluación futuro debe leer `agent_awakenings.activo=1` para sumar el bono al valor calculado del agente.

---

**`agent_thresholds`** — Umbrales de stats por agente (93 registros)

Tabla central del sistema de evaluación de discos. Define para cada agente qué valor mínimo, óptimo y máximo debe tener cada stat relevante, y por qué existe ese umbral (con fuente citada).

Campos: `id`, `agente_id` (FK), `stat` (nombre del campo en agents), `valor_minimo`, `valor_optimo`, `valor_maximo` (cap útil si existe), `descripcion` (explicación del threshold), `fuente` (Prydwen / 141store / IcyVeins / etc.).

Fuentes utilizadas: Prydwen.gg (builds y guías), 141store Hidden Mechanics Threshold Analysis, IcyVeins, Game8.

---

**`agent_discs`** — Detalle por slot de disco (270/270 filas, 100% poblada)

Tabla que registra los discos actualmente equipados en cada agente, slot por slot. Poblada manualmente a partir de los 45 screenshots de HoYoLAB. Incluye slots vacíos (EMPTY) para agentes sin build terminado.

Campos: `id`, `agente_id` (FK), `slot` (1-6), `set_id` (FK → disc_sets, nullable para EMPTY), `nivel`, `main_stat`, `main_valor`, 4 substats con estructura `subN`, `valN`, `subN_up` (badge de upgrade: 0-4 rolls extra).

Cobertura: Anomalía 10 agentes · Ataque 14 · Aturdimiento 5 · Defensa 6 · Disruptivos 3 · Soporte 7.

---

**`inventory_discs`** — Inventario de discos obtenidos (257 equipados cargados)

Tabla espejo de lo que tiene el jugador como discos. Actualmente contiene los 257 discos actualmente equipados en los 43 agentes con build (se excluyen Antón y Ben que están con 6 slots EMPTY). Cuando se implemente RF-09 (análisis de imagen), esta tabla pasará a llenarse desde screenshots también con los discos sueltos (`equipado=0`, `agente_asignado=NULL`).

Campos: `id`, `fecha_obtencion`, `set_id` (FK → disc_sets, nullable), `slot` (1-6), `main_stat`, `main_valor`, 4 substats con `subN`/`valN`/`rollsN`, `nivel`, `agente_asignado` (FK → agents, nullable), `equipado` (bool), `score_evaluacion` (0/1/2), `agentes_compatibles` (JSON), `screenshot_path`, `descartado` (bool), `notas`.

---

**`inventory_weapons`** — Inventario de W-Engines (40 equipadas cargadas)

Tabla espejo del inventario de armas del jugador. Solo 40 entradas porque 5 agentes del roster no tienen arma equipada (weapon_id=45 "Sin arma").

Campos: `id`, `weapon_id` (FK → weapons), `nivel`, `refinamiento` (1-5), `agente_asignado` (FK → agents, nullable), `equipado` (bool), `fecha_obtencion`, `notas`.

---

### 4.2 Relaciones del Schema

```
disc_sets ←── agents ──→ weapons
                │             ↑
                ├──→ agent_awakenings
                ├──→ agent_thresholds
                ├──→ agent_discs ──→ disc_sets
                ├──→ inventory_discs ──→ disc_sets
                └──→ inventory_weapons ──→ weapons
```

---

## 5. Roster Completo — DaniBOD

### Resumen General

| Stat | Valor |
|------|-------|
| Total agentes | 45 |
| S-Rank | ~33 |
| A-Rank | ~12 |
| Nivel 60 | 41 |
| Nivel 55 | 4 (Harumasa, Seth, Ben, Antón, Corin) |
| Días activos | 657 |
| Defensa Shiyu | 94,809 (top 31.35%) |
| Simulación Umbral | 185,006 (top 43.21%) |

**Distribución por elemento:** Físico 13 · Eléctrico 11 · Fuego 9 · Éter 7 · Hielo 5

**Distribución por rol:** Ataque 16 · Anomalía 10 · Soporte 7 · Defensa 7 · Aturdimiento 5

---

### Anomalía

| Agente | M | Elemento | Arma | Set 4p | Set 2p | Disco 6 |
|--------|---|----------|------|--------|--------|---------|
| Burnice | 0 | Fuego | Coctelera incandescente (S) | Jazz Caótico | Blues Libre | Tasa Anomalía 30% |
| Miyabi | 0 | Hielo | Templo a la granizada (S) | Balada rama/espada | Tecno Pícido | ATK 30% |
| Yanagi | 0 | Eléctrico | Llanto mielgo (A) | Jazz Caótico | Blues Libre | Tasa Anomalía 30% |
| Grace | 3 | Eléctrico | Compilador quimérico (S) | Blues Libre | Jazz Caótico | Tasa Anomalía 30% |
| Jane | 0 | Físico | Aguijón agudo (A) | Metal Colmilludo | Jazz Caótico | Tasa Anomalía 30% |
| Vivian | 0 | Éter | Llanto mielgo (A) | Melodía de Faetón | Jazz Caótico | Tasa Anomalía 30% |
| Alice | 0 | Físico | Llanto mielgo (A) | Metal Colmilludo | Melodía de Faetón | Tasa Anomalía 30% |
| Nangong Yu | 0 | Éter | Fósil preciado (S) | Melodía de Faetón | Jazz Caótico | Tasa Anomalía 30% |
| Piper | 6 | Físico | Viaje estruendoso (A) | Blues Libre | Jazz Oscilante | Tasa Anomalía 30% |

### Ataque

| Agente | M | Elemento | Arma | Notas build |
|--------|---|----------|------|-------------|
| Manato | 6 | Fuego | Rompecabeza ilusorio (S) | HP scaling · PV 16,362 · M6 |
| N.º 11 | 2 | Fuego | Motor estelar (S) | CRIT 56.2/117.2 · M2 |
| Evelyn | 0 | Fuego | Petrazufre (A) | ATK 3,230 · CRIT 56.2/157.2 |
| Ellen | 0 | Hielo | Visitante de altamar (S) | CRIT 72.2/171.6 · Ice DMG 30% |
| N.º 0: Anby | 0 | Eléctrico | Rotor de cañón (S) | CRIT 53.8/176.4 · Electric DPS |
| Sporos | 0 | Eléctrico | Rotor de cañón (S) | CRIT 66.6/184.4 · ATK 2,836 |
| Harumasa | 0 | Eléctrico | Sin arma | Nivel 55 · en desarrollo |
| Zhu Yuan | 0 | Éter | Rotor de cañón (S) | ATK 3,073 · PEN 8% |
| Yixuan | 0 | Éter | Caldero de la claridad (S) | PV 17,245 · Sheer DMG |
| Dialyn | 0 | Físico | Engranaje infernal (A) | CRIT Rate 89.8% |
| Ye Shunguang | 0 | Físico | Esplendor surcanimbos (S) | PEN 32% · CRIT DMG 208% |
| Orfia y Magas | 0 | Fuego | Anhelo marcato (S) | ER 2.8 · Fire DPS |
| Nekomata | 2 | Físico | Sin arma | M2 · en desarrollo |
| Billy | 6 | Físico | Réplica motor estelar (A) | CRIT 48.2/112.4 · M6 |
| Corin | 6 | Físico | Amo de llaves (A) | CRIT 41.8/83.6 · M6 |

### Aturdimiento

| Agente | M | Elemento | Arma | Impact | Notas |
|--------|---|----------|------|--------|-------|
| Lycaon | 4 | Hielo | Última cena (S) | 169 | M4 · CRIT 55.4% |
| Koleda | 3 | Fuego | Última cena (S) | 166 | M3 · CRIT 55.4% |
| Qingyi | 0 | Eléctrico | Última cena (S) | 168 | ER 1.8 |
| Gatillo | 0 | Eléctrico | Hellfire Gears (S) | 154 | CRIT 75.4% |
| Anby | 6 | Eléctrico | Sin arma | 160 | M6 · Electric DMG 30% |
| Pulchra | 6 | Físico | Cúter (A) | 189 | M6 · CRIT 55.4% |

### Soporte y Defensa

| Agente | M | Elemento | Rol | Arma | Stat destacado |
|--------|---|----------|-----|------|----------------|
| Astra Yao | 0 | Éter | Soporte | Demonio cohibido (B) | ATK 3,222 → cerca umbral buff |
| Lucy | 6 | Fuego | Soporte | Sin arma | ATK 1,774 → bajo umbral 2,000 |
| Soukaku | 6 | Hielo | Soporte | Sin arma | ATK 1,378 → bajo umbral 2,200 |
| Nicole | 6 | Éter | Soporte | Cámara acorazada (A) | ER 2.96 · DEF shred |
| Rina | 2 | Eléctrico | Soporte | Lapso de tiempo (S) | PEN 66.4% · ER 1.92 |
| Sunna | 0 | Físico | Soporte | Cañón bombástico (A) | ER 2.5 |
| Yuzuha | 0 | Físico | Soporte | Cañón bombástico (A) | ATK 3,014 |
| Ju Fufu | 0 | Fuego | Soporte | Caldero ardiente (S) | ATK 3,286 → cerca umbral 3,400 |
| César | 2 | Físico | Defensa | Proyector de celuloide (S) | PV 13,155 · M2 |
| Seth | 6 | Eléctrico | Defensa | Pacificador especializado (A) | ER 2.8 · M6 |
| Pan Yinhu | 6 | Físico | Defensa | Primavera termal (A) | ATK 3,347 |
| Zhao | 0 | Hielo | Defensa | Transmorfer original (S) | PV 28,512 |
| Lucía | 0 | Éter | Defensa | Cañón bombástico (A) | PV 23,214 |

---

## 6. Análisis de Thresholds

### 6.1 Resultado Inicial — Estado Actual

**🔴 Bajo umbral mínimo (requieren atención)**

| Agente | Stat | Actual | Mínimo | Por qué importa |
|--------|------|--------|--------|-----------------|
| Miyabi | CRIT Rate | 51.4% | 65% | Core Passive no activa al máximo (Fallen Frost) |
| Burnice | Energy Regen | 1.56 | 1.8 | Despertar "Boiling Point Party" completamente inactivo |
| Harumasa | CRIT Rate | 39.4% | 55% | Sin arma ni discos completos, nivel 55 |
| Harumasa | ATK | 1,388 | 2,000 | Sin arma, en desarrollo |
| N.º 0: Anby | CRIT Rate | 53.8% | 55% | Muy cerca, fácil de resolver con substats |
| Soukaku | ATK | 1,378 | 2,200 | Sin arma → no bufféa al máximo al equipo |
| Lucy | ATK | 1,774 | 2,000 | Sin arma → buff al equipo incompleto |
| Nekomata | CRIT Rate | 24.2% | 55% | Sin arma, subdesarrollada |
| Nekomata | ATK | 1,621 | 2,200 | Sin arma |
| Ye Shunguang | CRIT Rate | 48.2% | 50% | Justo por debajo, se puede resolver fácil |
| Antón | ATK | 827 | 1,500 | Sin discos, sin inversión |

**✅ En óptimo**

Burnice (AP 398 → cap 300), Ellen (CRIT Rate 72.2%), Evelyn (ATK 3,230), Grace (PEN 24% + AP 358), Koleda (Impact 166), Lycaon (Impact 169), Manato (PV 16,362), Orfia y Magas (ER 2.8), Pulchra (Impact 189), Rina (PEN Ratio 66.4%), Seth (ER 2.8), Sporos (CRIT DMG 184.4%), Sunna (ER 2.5), Vivian (PEN 24%), Yuzuha (ER 2.0), Zhao (PV 28,512).

### 6.2 Revisión Fina — Gaps Identificados (abril 2026)

Tras pasar los 93 thresholds por revisión contra guías actualizadas (Prydwen, IcyVeins, 141store), el estado es: **45/45 agentes cubiertos con al menos 1 stat**, pero hay gaps razonables para enriquecer el modelo de evaluación. Se listan a continuación los candidatos a sumar; no se agregan automáticamente hasta validación caso por caso con el usuario.

**Gaps propuestos (pendientes de confirmación):**

| Agente | Stat faltante | Valor mín / óptimo | Justificación |
|--------|---------------|---------------------|---------------|
| Orfia y Magas | `ataque` | 2800 / 3200 | Fire DPS principal sin ATK threshold definido |
| Astra Yao | `rec_energia` | 1.8 / 2.0 | Soporte que depende de rotación de EX |
| Ju Fufu | `rec_energia` | 1.8 / 2.2 | Soporte Fuego, rotación constante |
| Nicole | `ataque` | 2000 / 2400 | DEF-shred, su ATK impacta daño aplicado |
| Soukaku | `rec_energia` | 1.2 / 1.5 | Off-field Hielo requiere EX frecuente |
| Yanagi | `rec_energia` | 1.6 / 1.8 | On-field Electric, EX + ult cycle |
| Nangong Yu | `ataque` | 2400 / 2800 | Ether off-field, ATK escala instancias |
| Pulchra | `ataque` | 2000 / 2400 | Stun híbrido con daño físico visible |
| Alice | `rec_energia` | 1.5 / 1.8 | Physical Anomaly on-field |
| Vivian | `ataque` | 2400 / 2800 | Ether Anomaly off-field — ATK escala daño |

**Thresholds a revisar por posible imprecisión (descripción refinada abril 2026, valores intactos):**

- **Miyabi `prob_critico` 65%** → descripción actualizada: benchmark de build (Prydwen), no hard-threshold mecánico. Core Passive (Iai) escala con Ice DMG, no con CRIT directamente. Tratarlo como meta de scaling.
- **Grace / Vivian `tasa_perforacion` 24%** → descripción actualizada: el valor coincide con el base del arma (Compilador quimérico / Llanto mielgo). Threshold opera como "mantener", no como "superar". Si cambia de W-Engine sin PEN innato vuelve a ser meta activa.
- **Burnice `maestria_anomalia` 300/350** → descripción actualizada: cap DURO en 300. DaniBOD ya está en 398 (sobre cap útil). Motor de scoring debe considerar AP>300 como stat wasted salvo rebalance futuro.

**Thresholds que ya cumplen óptimo:**

Burnice AM (398), Ellen CRIT (72.2%), Evelyn ATK (3230), Grace PEN (24%), Koleda Impact (166), Lycaon Impact (169), Manato PV (16362), Orfia ER (2.8), Pulchra Impact (189), Rina PEN (66.4%), Seth ER (2.8), Sporos CRIT DMG (184.4%), Sunna ER (2.5), Vivian PEN (24%), Yuzuha ER (2.04), Zhao PV (28512), Dialyn CRIT Rate (89.8%).

**Thresholds ajustados en esta revisión (abril 2026):** Los 10 gaps propuestos se aplicaron en batch previa confirmación del usuario. `agent_thresholds` pasó de 93 → 103 filas. Los 3 thresholds "por imprecisión" (Miyabi prob_critico, Grace/Vivian tasa_perforacion, Burnice AM cap 350) quedan sin cambios hasta nueva revisión; se documentan aquí como nota operativa para el motor de evaluación.

**Awakenings cargados (abril 2026):**

- Burnice nv6 — *"Boiling Point Party"* (v2.5) — contenido textual verificado
- Lycaon, Ellen, Grace, N.º 0: Anby → nv6 placeholder, `activo=1`, `descripcion='pending_capture'`. El usuario confirmó en shop Silueta Potencial que los 4 están **Agotado** (completados). Solo falta capturar el texto de cada nivel 1–6 desde el menú in-game y reemplazar el placeholder.
- Harumasa, N.º 11 → **parciales**, NO se insertaron filas hasta que el usuario indique a qué nivel llegó (1–5). Evita pollution de datos.
- Resto del roster → según el usuario todos tienen awakening disponibles; la carga se hará agente por agente con validación textual para respetar RNF-02.

---

## 7. Sistema de Detección de Discos (RF-09, RF-04, RF-05)

### 7.1 Problema que resuelve

Cuando se farmea un disco, el juego lo muestra brevemente antes de que el jugador decida guardarlo o borrarlo. En ese momento no existe forma rápida de saber si ese disco sirve para algún otro personaje del roster. El jugador termina borrando discos que podrían haber sido útiles, o guardando basura por miedo a equivocarse.

### 7.2 Flujo del sistema

```
[Farmeo un disco en ZZZ]
        ↓
[Script detecta la pantalla de resultados]
        ↓
[Captura screenshot automático]
        ↓
[Módulo de análisis extrae stats del disco]
        ↓
[Motor de evaluación compara contra thresholds de cada agente]
        ↓
[Overlay flotante muestra resultado]
  ✅ Verde  → Óptimo para [agente X]
  🟡 Amarillo → Aceptable para [agente Y, Z]
  🔴 Rojo   → Descartar
        ↓
[Si verde/amarillo → INSERT en inventory_discs]
[Si rojo → el jugador lo borra en el juego]
```

### 7.3 Módulos del script

El script corre en background como proceso independiente mientras ZZZ está abierto. No interactúa con el proceso del juego en ningún momento.

**`monitor.py`** — Proceso principal. Mantiene el loop activo, detecta si la ventana de ZZZ está en foco, coordina los demás módulos.

**`detector.py`** — Trigger de captura. Usa template matching (OpenCV) sobre una región fija de píxeles para detectar cuándo aparece la pantalla de resultados de un disco. También puede usar detección por color/región como fallback. Las imágenes de referencia (templates) se guardan en `templates/`. Trigger pendiente de definir — requiere screenshots de las pantallas específicas del juego.

**`capturer.py`** — Toma el screenshot de la región exacta donde aparecen los stats del disco. La región se define una sola vez por resolución de pantalla.

**`analyzer.py`** — Recibe el screenshot y extrae los datos del disco: nombre del set, slot, main stat y valor, 4 substats con sus valores y cantidad de rolls. **La IA/API a usar para este análisis está por definir** (ver sección 7.4).

**`evaluator.py`** — Toma los datos extraídos y los compara contra la tabla `agent_thresholds`. Determina para qué agentes es útil el disco y con qué nivel de prioridad. Genera el score final y la lista de agentes compatibles.

**`overlay.py`** — Toast flotante always-on-top con la recomendación. *Implementación final movida a `app/ui/toast.py` (PySide6) bajo RF-11; el módulo en `scripts/` queda como prototipo legacy.*

### 7.4 Módulo de análisis de imagen — API por definir

El análisis visual del disco (OCR + interpretación de stats) requiere un modelo de visión. Hay varias opciones con distintos tradeoffs:

| Opción | Pro | Contra |
|--------|-----|--------|
| Claude API (vision) | Alta precisión, entiende contexto del juego | Costo por token, requiere internet |
| GPT-4o vision | Alta precisión | Costo por token, requiere internet |
| Tesseract OCR (local) | Gratuito, sin internet, sin latencia | Requiere preprocesamiento de imagen, más frágil |
| PaddleOCR (local) | Mejor que Tesseract, gratuito | Más complejo de configurar |
| Modelo local fine-tuned | Sin costo, offline | Requiere entrenamiento con datos del juego |

**Decisión pendiente.** Se evaluará considerando: frecuencia de uso, costo acumulado, precisión necesaria, y si se quiere una solución 100% offline. Por ahora el módulo `analyzer.py` tendrá una interfaz abstracta para que el backend de IA sea intercambiable.

### 7.5 Tabla `inventory_discs` (ya implementada)

```sql
CREATE TABLE inventory_discs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_obtencion     DATETIME DEFAULT CURRENT_TIMESTAMP,
    set_id              INTEGER REFERENCES disc_sets(id),
    slot                INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 6),
    main_stat           TEXT,
    main_valor          REAL,
    sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0,
    sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0,
    sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0,
    sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0,
    nivel               INTEGER DEFAULT 0,
    agente_asignado     INTEGER REFERENCES agents(id),
    equipado            INTEGER DEFAULT 0 CHECK(equipado IN (0,1)),
    score_evaluacion    INTEGER,
    agentes_compatibles TEXT,
    screenshot_path     TEXT,
    descartado          INTEGER DEFAULT 0 CHECK(descartado IN (0,1)),
    notas               TEXT
)
```

**Filas actuales:** 257 (todos con `equipado=1`, del roster equipado).

### 7.6 Tabla `inventory_weapons` (ya implementada)

```sql
CREATE TABLE inventory_weapons (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id           INTEGER NOT NULL REFERENCES weapons(id),
    nivel               INTEGER DEFAULT 0,
    refinamiento        INTEGER DEFAULT 1 CHECK(refinamiento BETWEEN 1 AND 5),
    agente_asignado     INTEGER REFERENCES agents(id),
    equipado            INTEGER DEFAULT 0 CHECK(equipado IN (0,1)),
    fecha_obtencion     DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas               TEXT
)
```

**Filas actuales:** 40 (todas con `equipado=1`, excluidos 5 agentes con "Sin arma").

### 7.7 Consideraciones TOS

Este sistema es compatible con los términos de servicio de HoYoverse porque no inyecta código en el proceso del juego, no lee memoria del juego, no simula inputs ni automatiza gameplay, y solo captura lo que el usuario ve en pantalla. Es equivalente a herramientas como Inventory Kamera para Genshin Impact, que la comunidad usa sin problemas desde hace años.

---

## 8. Optimizador de Equipos por Personaje (RF-12)

> **Nota de evolución (abril 2026):** RF-12 absorbe lo que originalmente se planteaba como RF-10 (Additional Abilities). RF-10 quedó descartado de v1 (ver §3.1 nota final); la catalogación IA-driven de RF-12 cubre tanto Additional Abilities oficiales como sinergias emergentes (combos de elementos, ult-stacking — ej. Ellen+Dialyn → Puffer Electro). El scoring y los outputs descritos abajo siguen siendo válidos como **especificación funcional**; la implementación opera sobre las tablas y el algoritmo definidos en [`Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md`](./Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md).


### 8.1 Problema que resuelve

Dado un personaje seleccionado como DPS principal, ¿cuál es matemáticamente el mejor equipo posible con los agentes disponibles en el roster? Esta pregunta tiene muchas variables: sinergias de elemento para Disorder, cobertura de roles (DPS + Stun + Soporte/Defensa), buffs que se apilan, thresholds que se activan entre sí, y restricciones de contenido (anti-shill en Shiyu).

El objetivo es que el sistema genere una respuesta con un score numérico fundamentado, no solo una recomendación subjetiva.

### 8.2 Variables del modelo

**Sinergias de elemento**

Algunos pares de elementos generan Disorder al combinar dos Anomalías distintas, lo que multiplica el daño. El sistema debe conocer qué combinaciones son válidas y cuáles no (ej: dos agentes del mismo elemento no generan Disorder entre sí).

Combinaciones relevantes para el roster de DaniBOD:
- Fuego + Eléctrico → Disorder (Burnice + Yanagi / Grace)
- Hielo + Eléctrico → Disorder (Miyabi + Yanagi / Grace)
- Físico + cualquier otro → Disorder via Assault (Jane, Piper, Alice)
- Hielo + Hielo → Freeze/Shatter (no Disorder, pero válido para Ellen)

**Sinergias de facción**

Algunos agentes activan Additional Abilities entre sí si comparten facción, otorgando buffs pasivos que no aparecen en el panel de stats. Ejemplos relevantes: Miyabi y Yanagi (Section 6), Burnice y Lucy (Sons of Calydon), Jane y César (Criminal Investigation).

**Cobertura de roles**

Un equipo de 3 agentes idealmente cubre DPS principal + Aturdimiento (para chain attacks) + Soporte o Defensa (para buffs o shields). El sistema penaliza equipos con roles redundantes o sin Stun cuando el contenido lo requiere.

**Buffs apilables y thresholds cruzados**

Algunos soportes tienen thresholds de ATK que cuando se alcanzan buffean al equipo entero. El sistema calcula si con los stats actuales de cada soporte se activan esos thresholds:

| Soporte | Umbral ATK | Efecto si se alcanza |
|---------|-----------|----------------------|
| Astra Yao | 3,429 | +1,200 ATK al equipo |
| Ju Fufu | 3,400 | Buff máximo al equipo |
| Soukaku | 2,500 | +1,000 ATK al equipo |
| Lucy | 2,000 | +600 ATK al equipo |

**Pasivas de armas y sets activos en equipo**

El sistema considera si las pasivas de armas y sets de los agentes se activan entre sí. Ej: Proto Punk activa su buff cuando hay un Defensive Assist — solo es útil si el equipo tiene un agente de Defensa. Swing Jazz activa con Chain Attack o Ultimate — requiere que alguien lo trigguee frecuentemente.

**Restricciones de contenido**

Shiyu Defense tiene mecánicas anti-shill que penalizan ciertos elementos en ciertos frentes. El optimizador recibe como parámetro el tipo de contenido y ajusta el score en consecuencia.

### 8.3 Modelo de scoring

Para cada combinación posible de 3 agentes del roster (con el personaje seleccionado fijo en slot 1):

```
Score_equipo =
    Score_DPS_base
  + Bonus_sinergia_elemento        (Disorder posible: alto impacto)
  + Bonus_sinergia_faccion         (Additional Ability activa: impacto medio)
  + Bonus_cobertura_roles          (Stun presente: alto; Soporte presente: medio)
  + Bonus_thresholds_activos       (por cada threshold de soporte cumplido)
  + Bonus_pasivas_compatibles      (por cada pasiva de arma/set que se activa en equipo)
  - Penalizacion_roles_redundantes
  - Penalizacion_antishill         (si el contenido lo requiere)
```

Los pesos de cada bonus se definirán y calibrarán durante el desarrollo, ajustados comparando contra resultados conocidos de Shiyu y Deadly Assault.

### 8.4 Output esperado

Al seleccionar un personaje, el sistema retorna los mejores equipos rankeados con su justificación matemática:

```
🏆 Mejor equipo para Miyabi (M0)

1. Miyabi + Yanagi + Astra Yao       Score: 94/100
   ✓ Disorder Hielo+Eléctrico
   ✓ Facción Section 6 (Additional Ability activa)
   ✓ Astra Yao ATK 3,222 → cerca umbral (falta 207 ATK)
   ⚠ Sin Stun — riesgo en Shiyu con enemigos resistentes

2. Miyabi + Yanagi + Lycaon           Score: 89/100
   ✓ Disorder Hielo+Eléctrico
   ✓ Lycaon M4 Impact 169 — Stun rápido y consistente
   ✓ Roles: Anomalía + Anomalía + Stun cubiertos

3. Miyabi + Burnice + Astra Yao       Score: 85/100
   ✓ Disorder Hielo+Fuego
   ✓ Burnice off-field no compite por tiempo en campo
   ⚠ Burnice ER 1.56 < 1.8 → Despertar inactivo (-DMG)
   ⚠ Sin Stun
```

### 8.5 Estado

🟦 **Diseño cerrado (abril 2026)** vía RF-12. Ver [`Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md`](./Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md) para el plan de implementación detallado (3 tablas nuevas, prompts a Claude API, runtime determinista, costos esperados <$10/mes). Implementación pendiente — arranca tras la migración `2026-04-XX_03_team_synergies.sql`.

---

## 9. Análisis de Rotaciones (Visión a Futuro)

### 9.1 Qué es una rotación en ZZZ

Una rotación es la secuencia óptima de habilidades y swaps entre los 3 agentes del equipo para maximizar el DPS en un intervalo de tiempo. A diferencia de otros gacha, ZZZ es acción en tiempo real — las rotaciones dependen de ventanas de buff, cooldowns de Energy, timing de Chain Attacks y el estado de recursos de cada agente (Heat de Burnice, Fallen Frost de Miyabi, Venom de futuros agentes, etc.).

### 9.2 Por qué es visión a futuro

Hay variables que el sistema actual no puede modelar sin datos de gameplay real:

- Duración exacta de cada animación de habilidad en frames
- Ventana de Quick Assist y cuándo es óptimo triggearla vs. continuar on-field
- Cómo varía la rotación si el Stun ocurre antes o después de lo esperado
- Diferencias de rotación entre distintos Mindscape del mismo personaje
- Interacciones de timing entre el off-field de Burnice y el on-field de otro agente

Por esto el módulo se clasifica como visión a futuro — requiere datos que solo se obtienen midiendo gameplay real, ya sea manualmente o capturando timestamps durante combate.

### 9.3 Approach de implementación posible

Una vez que el sistema de screenshots esté funcionando para discos, el mismo mecanismo podría extenderse para capturar pantallas durante combate y registrar: qué habilidad se usó, en qué timestamp, con qué agente. Con suficientes datos se podría modelar la rotación óptima como un problema de optimización (similar a cómo funcionan las calculadoras de Genshin del grupo KQM).

### 9.4 Alcance realista de versión inicial

La primera versión no intentaría modelar rotaciones frame-perfect. El objetivo sería más simple y ya muy útil: dado un equipo, sugerir el orden de entrada de los agentes y la habilidad prioritaria en cada fase. Ejemplo:

```
Rotación sugerida: Burnice + Yanagi + Lycaon

1. Entra Burnice on-field → acumula Heat con Charged Attack
2. Swap a Lycaon → EX Special para iniciar Stun
3. Durante Stun → Chain Attack con Yanagi (EX Special: Disorder)
4. Swap a Burnice off-field → Afterburn se trigguea por ataques de Yanagi
5. Yanagi on-field → mantiene Shock + genera Fallen Frost para Miyabi si aplica
```

Esto no requiere datos de frames — se puede modelar con las pasivas y mecánicas conocidas de cada agente.

### 9.5 Estado

En diseño conceptual. No se implementa hasta que el optimizador de equipos (sección 8) esté funcionando y validado con resultados reales de Shiyu y Deadly Assault.

---

## 10. Próximos Pasos

### Inmediato (cierre de gaps de Fase 1)

- [ ] Cargar `agent_awakenings` para los 4 agentes con awakening completo confirmado (Lycaon, N.° 0: Anby, Ellen, Grace) — capturar texto in-game.
- [ ] Resolver nivel exacto de awakening de Asaba Harumasa y N.° 11.
- [ ] Cerrar revisión fina de thresholds agente por agente (gaps en §6.2).

### Operación continua — extensibilidad por patches

- [x] Documentar **flujo de Onboarding de PJ nuevo** (abril 2026) — ver [`Documentacion/Onboarding_Nuevo_PJ.md`](./Documentacion/Onboarding_Nuevo_PJ.md). Define 8 pasos end-to-end (carga base → arquetipo → seed `pj_weapon_synergy` → scraping Prydwen → catalogación IA 44 pares → splash art → notificación → wizard) + checklist operativo "TL;DR por patch" + costo esperado ~$0.50/PJ.
- [x] Documentar **flujo de Onboarding de assets nuevos** (abril 2026) — ver [`Documentacion/Onboarding_Nuevos_Assets.md`](./Documentacion/Onboarding_Nuevos_Assets.md). Cubre los otros 3 tipos de assets: W-Engines (4 pasos + recálculo `weapon_evaluations`), Sets de discos (5 pasos + re-evaluación `inventory_discs`), Facciones (3 pasos + actualización de logos). Wizard unificado en RF-11 con 4 modos (PJ / W-Engine / Set / Facción).
- [ ] Implementar el **wizard "Agregar PJ nuevo"** en pestaña Configuración (RF-11) — modal 600×500 px con 4 pasos según `Onboarding_Nuevo_PJ.md` §11.
- [ ] Implementar los **3 wizards adicionales** (W-Engine / Set / Facción) según `Onboarding_Nuevos_Assets.md` §4.
- [ ] Auto-encolado RF-12 cuando RF-04 detecta PJ no-en-roster (ya documentado en RF-12 §6.1, falta implementación).

### Scaffold del `.exe` standalone (RF-11)

- [x] Diseño cerrado: stack PySide6 + PyInstaller, toast + panel + dashboard, trigger sólo accionables (abril 2026).
- [ ] Scaffold del proyecto `app/` (estructura listada en §12).
- [ ] Implementar `main.py` + tray + ciclo de vida + detección de proceso `ZenlessZoneZero.exe`.
- [ ] Implementar `ui/toast.py` (widget flotante always-on-top con auto-fade 5s).
- [ ] Implementar `ui/panel_detalle.py` con las 5 pestañas (Captura en vivo, Histórico, Roster, Catálogos, Configuración).
- [ ] Hotkeys globales con `pynput` (F8/F9/F10/F11/Ctrl+Shift+Z — F11 reservado para RF-13).
- [ ] Asistente de primera ejecución (seleccionar carpeta DB, calibrar ROIs OCR, registrar hotkeys).
- [ ] Spec de PyInstaller + primera build `.exe` portable (~60-80 MB target).

### Fase 2 — Captura + scoring + optimizador base (RF-04/05/06/09)

- [x] Diseño cerrado: máquina de estados, polling adaptativo, OCR híbrido, greedy + bonus pass (abril 2026).
- [ ] `app/core/ocr_backend.py` — interfaz abstracta + impls `ocr_tesseract.py` y `ocr_paddle.py`.
- [ ] `app/core/sync_equip.py` (RF-04) — detección de cambio de equipamiento + diff PRE/POST.
- [ ] `app/core/sync_upgrade.py` (RF-05) — captura PRE/POST upgrade + decisión sub_unlocked / sub_rolled / multi_rolls.
- [ ] `app/core/scoring.py` — engine compartido (positivos × rolls − |perjudiciales| × rolls + bonus_main + bonus_nivel).
- [ ] `app/core/recommender.py` — decisor equipar / mejorar / reservar / descartar.
- [ ] `app/core/optimizer.py` (RF-06) — greedy + bonus pass + delta vs build actual.
- [ ] Migración `2026-04-XX_02_optimizer_pending.sql` (`optimizer_pending_actions`).
- [ ] Seed de `agent_substat_preferences` (~225 filas) desde Prydwen.
- [ ] `app/ui/build_optimizer_view.py` (modal con tabs por build).
- [ ] Integración auto-trigger RF-04 → RF-06 cuando un disco con `score ≥ threshold_equip` cambia la mejor build (debounce 2s/PJ).
### Fase 3 — Optimizador team-aware con IA catalogadora (RF-12)

- [x] Diseño cerrado: 3 capas (pesos / override set / sugerir equipo), Claude API catalogadora, runtime determinista (abril 2026).
- [ ] Migración `2026-04-XX_03_team_synergies.sql` (`team_synergies`, `team_compositions`, `ai_catalog_runs`).
- [ ] `app/core/ai_catalog.py` — cliente Claude API + prompt caching + retries + cap de costo (`user_config.toml::ai_catalog.cap_usd_mensual`).
- [ ] `app/core/team_optimizer.py` — lookups + integración con RF-06 (overrides de pesos y set).
- [ ] `app/ui/teams_view.py` — pestaña "Equipos" + toggle en build_optimizer_view.
- [ ] Seed inicial: 990 llamadas `team_synergy_pair` (sonnet) + 45 `team_composition_topN` (opus) ≈ $21 one-time.
- [ ] Integración del cap de costo + dashboard de uso de IA (lee `ai_catalog_runs`).
- [ ] Auto-encolado al detectar PJ/set nuevo desde RF-04.
- [ ] Caso de prueba: Ellen + Dialyn → Puffer Electro debe aparecer con `confianza ≥ 0.85` y `tipo='core_passive_ult'`.

### Fase 5 — Optimizador de armas con scoring contextual (RF-14)

- [x] Diseño cerrado: ranking ideal+disponible, modelado híbrido de pasivas, scoring por contenido + delta Prydwen, build full coordinado con RF-06 (abril 2026).
- [ ] Migración `2026-04-XX_05_weapon_optimizer.sql` (5 tablas + extensiones a `weapons` + seed `content_profiles`).
- [ ] Modelado inicial de pasivas (~80 filas en `weapon_passives_structured`) — carga manual asistida por Claude API one-time (~$3 estimado).
- [ ] Seed de `pj_weapon_synergy` (~180 filas, 45 PJs × 4 categorías de pasiva relevantes).
- [ ] `app/scripts/scrape_prydwen_weapons.py` + snapshot inicial.
- [ ] `app/core/weapon_scoring.py` — fórmula con uptime contextual (trigger_tipo → content_profile lookup).
- [ ] `app/core/weapon_optimizer.py` — rankings + build full (3 armas × 3 builds RF-06).
- [ ] `app/ui/weapons_view.py` — pestaña con 4 subpestañas (Ranking por PJ, Build full, Catálogo, Comparativo Prydwen).
- [ ] Toggle "Optimizar también el arma" en `build_optimizer_view.py` (RF-06).
- [ ] Editor admin de pasivas estructuradas (para agregar pasivas de W-Engines nuevos sin esperar update del scraper).
- [ ] Hooks de integración: con RF-12 (lectura `team_synergies` para uptime de triggers `team_has_*`); con RF-13 (recalibración bayesiana de `content_profiles` desde `lategame_runs`).
- [ ] Tests E2E: caso "la roca" (Núcleo Fosilizado Precioso) debe rankear S+ en DA y B en HZ; armas con `trigger_tipo='always'` deben rankear igual en todos los contenidos.

### Fase 4 — Validación lategame + retro-feedback bayesiano (RF-13)

- [x] Diseño cerrado: captura F11, OCR breakdown DMG, tier list calibrada vs Prydwen, ajuste bayesiano de `team_synergies.confianza` (abril 2026).
- [ ] Migración `2026-04-XX_04_lategame_validation.sql` (8 tablas + flag `congelado` en `team_synergies`).
- [ ] `app/scripts/scrape_enemies.py` — Hakush.in (datamine) + Prydwen (ciclos) → ~80 enemigos iniciales.
- [ ] `app/scripts/scrape_prydwen_tierlist.py` — snapshot semanal (Shiyu / DA / general).
- [ ] `app/core/lategame_capture.py` — pipeline OCR del breakdown DMG (reutiliza `ocr_backend.py`).
- [ ] `app/core/tier_list_calculator.py` — buckets fijos S+/S/A/B/C/D + delta vs Prydwen + justificación textual.
- [ ] `app/core/retro_feedback.py` — ajuste bayesiano de confianza con prior IA + likelihood empírica capada en 1.5.
- [ ] `app/ui/lategame_view.py` — pestaña con 5 subpestañas (Runs recientes / Tier List Personal / Comparativo Prydwen / Histórico / Ciclos).
- [ ] Hotkey F11 + asistente "calibrar ROIs del breakdown DMG" en primer uso.
- [ ] Tests E2E + validación cruzada con 20 runs reales antes de soltar el retro-feedback automático.

### Post-v1

- [ ] Versión móvil del dashboard (requiere arquitectura de sync DB).
- [ ] Integración Discord/Telegram para alertas remotas (out of scope v1).
- [ ] Modo multi-cuenta (otros UIDs además de DaniBOD).

---

## 11. Stack Técnico

| Herramienta | Uso |
|-------------|-----|
| SQLite | Base de datos local principal |
| Python 3.11+ | Lenguaje base del `.exe` y de todos los scripts |
| PySide6 (Qt 6) | UI del standalone: tray, toast flotante, dashboard integrado (RF-11) |
| PyInstaller | Empaquetado `.exe` one-file (~60-80 MB) |
| OpenCV (cv2) | Template matching para clasificar pantallas del juego |
| mss | Captura de pantalla de baja latencia |
| pynput | Hotkeys globales que funcionan aunque ZZZ tenga el foco |
| Tesseract + PaddleOCR | OCR por ROI (Tesseract para texto, Paddle para números) — RF-09 |
| pyqtgraph / QtCharts | Gráficas en el dashboard histórico |
| toml (tomli / tomli_w) | Persistencia de `user_config.toml` |
| anthropic (SDK Claude API) | IA catalogadora de sinergias y composiciones (sonnet pares / opus composiciones) — RF-12 |
| httpx + BeautifulSoup4 | Scraping de Prydwen (tier list, ciclos Shiyu) y Hakush.in (datamine de bosses) — RF-13 |
| Claude Code | Desarrollo integrado en VS Code |
| Prydwen.gg | Fuente de datos de sets, armas, builds, substat preferences, ciclos lategame y tier list |
| Hakush.in | Datamine de enemigos (HP, escalado, resistencias) — RF-13 |

**Stack descartado:** Tkinter (UX pobre, sin overlay semitransparente real), Electron (binario 150 MB + RAM alta compitiendo con ZZZ), Rust+Python sidecar (complejidad IPC no justificada en v1).

---

## 12. Estructura de Archivos

```
D:\Proyectos\Zenless_analitycs\
├── README.md
├── schema.sql
├── db\
│   ├── danibod_zzz_v2.db
│   └── migrations\
│       ├── 2026-04-24_01_archetypes_and_scoring.sql  (✅ aplicada)
│       ├── 2026-04-25_02_optimizer_pending.sql       (✅ aplicada — RF-06)
│       ├── 2026-04-25_03_team_synergies.sql          (✅ aplicada — RF-12)
│       ├── 2026-04-25_04_lategame_validation.sql     (✅ aplicada — RF-13, seeded)
│       └── 2026-04-25_05_weapon_optimizer.sql        (✅ aplicada — RF-14, seeded)
├── Documentacion\
│   ├── RF_Captura_Discos\                            (RF-04 / RF-05 / RF-09)
│   │   ├── README.md
│   │   ├── RF-Logic_Captura_Discos.md
│   │   ├── Analisis_Capturas_Iteracion_1.md
│   │   └── Catalogo_Screenshots_Requeridos.md
│   ├── RF_Optimizador\                               (RF-06)
│   │   ├── README.md
│   │   └── RF-Logic_Optimizador_Build.md
│   ├── RF_Optimizador_Equipos\                       (RF-12)
│   │   ├── README.md
│   │   └── RF-Logic_Optimizador_Equipos.md
│   ├── RF_Lategame_Validation\                       (RF-13)
│   │   ├── README.md
│   │   └── RF-Logic_Lategame_Validation.md
│   ├── RF_Optimizador_Armas\                         (RF-14)
│   │   ├── README.md
│   │   └── RF-Logic_Optimizador_Armas.md
│   ├── Modelo_Relacional\                            (MR completo de la DB)
│   │   ├── README.md                                 (catálogo de 30 tablas + FKs + decisiones)
│   │   ├── Modelo_Relacional_v1.{svg,png}            (diagrama ER agrupado por capa)
│   │   └── render_mr.py                              (script de regeneración)
│   └── Diagramas de flujos\                           (segmentados v4 — top-down decomposition)
│       ├── RF-04_v2_captura_discos.{svg,png}          (legacy v2, gigante — sustituido por sub-diagramas)
│       ├── RF-05_v2_upgrade_disco.{svg,png}           (legacy v2)
│       ├── RF-04_05_arquitectura_v2.{svg,png}         (legacy v2)
│       ├── RF-04_01_overview.{svg,png}                (RF-04 alto nivel: trigger → extracción → análisis → notify)
│       ├── RF-04_02_extraccion.{svg,png}              (sub: 3 caminos Patrulla/Música/Inventario)
│       ├── RF-04_03_analisis.{svg,png}                (sub: scoring engine completo)
│       ├── RF-05_01_overview.{svg,png}                (RF-05 alto nivel: PRE → POST → diff)
│       ├── RF-05_02_diff.{svg,png}                    (sub: sub_unlocked/sub_rolled/multi_rolls)
│       ├── RF-06_01_overview.{svg,png}                (RF-06 alto nivel: trigger → carga → algoritmo → top 3)
│       ├── RF-06_02_algoritmo.{svg,png}               (sub: greedy + bonus pass detallado)
│       ├── RF-12_01_runtime.{svg,png}                 (RF-12 runtime: 3 capas + invoca RF-06)
│       ├── RF-12_02_catalogacion.{svg,png}            (RF-12 offline: Claude API + audit)
│       ├── RF-13_01_captura.{svg,png}                 (RF-13 captura F11 + OCR + valida + insert)
│       ├── RF-13_02_tierlist.{svg,png}                (RF-13 recálculo + buckets + delta Prydwen)
│       ├── RF-13_03_bayesiano.{svg,png}               (RF-13 retro-feedback bayesiano completo)
│       ├── RF-14_01_overview.{svg,png}                (RF-14 alto nivel: scoring contextual + ranking)
│       ├── RF-14_02_buildfull.{svg,png}               (sub: combinación arma + 6 discos)
│       ├── Arquitectura_v3_completa.{svg,png}         (visión global: 5 capas + persistencia)
│       ├── rf_render_v3.py                            (script v3 — diagramas grandes legacy)
│       └── rf_render_v4.py                            (script v4 — diagramas segmentados actuales)
├── Pj_stats\                  (45 screenshots renombrados por agente)
├── Screenshots_Triggers\
│   └── Discos_Triggers\       (anclas visuales para clasificador)
├── app\                                   (.exe standalone — RF-11)
│   ├── main.py                            (entry point, QApplication, tray)
│   ├── ui\
│   │   ├── toast.py                       (widget flotante de recomendación)
│   │   ├── panel_detalle.py               (ventana expandida con tabs)
│   │   ├── dashboard_historico.py         (tabla de inventory_disc_evaluations)
│   │   ├── roster_view.py                 (estado de los 45 PJs)
│   │   ├── catalogos_view.py              (arquetipos / preferences editables)
│   │   ├── build_optimizer_view.py        (RF-06 — modal con tabs por build)
│   │   ├── teams_view.py                  (RF-12 — pares + composiciones top-N)
│   │   ├── lategame_view.py               (RF-13 — runs / tier list / comparativo / histórico / ciclos)
│   │   ├── weapons_view.py                (RF-14 — ranking por PJ / build full / catálogo / comparativo Prydwen)
│   │   └── settings_view.py               (config del usuario)
│   ├── core\
│   │   ├── monitor.py                     (orquesta pipeline + loop de captura)
│   │   ├── detector.py                    (template matching pantalla)
│   │   ├── capturer.py                    (mss screenshot + ROI crop)
│   │   ├── ocr_backend.py                 (RF-09 — interfaz abstracta)
│   │   ├── ocr_tesseract.py               (impl. Tesseract — texto)
│   │   ├── ocr_paddle.py                  (impl. PaddleOCR — números)
│   │   ├── scoring.py                     (engine compartido §11 RF-Logic)
│   │   ├── recommender.py                 (decisor equipar/mejorar/reservar/descartar)
│   │   ├── sync_equip.py                  (RF-04 — cambio de equipamiento)
│   │   ├── sync_upgrade.py                (RF-05 — upgrade PRE/POST)
│   │   ├── optimizer.py                   (RF-06 — greedy + bonus pass)
│   │   ├── ai_catalog.py                  (RF-12 — cliente Claude API + prompt caching)
│   │   ├── team_optimizer.py              (RF-12 — lookups + integración con RF-06)
│   │   ├── lategame_capture.py            (RF-13 — pipeline OCR breakdown DMG)
│   │   ├── tier_list_calculator.py        (RF-13 — buckets fijos + delta vs Prydwen)
│   │   ├── retro_feedback.py              (RF-13 — ajuste bayesiano de confianza)
│   │   ├── weapon_scoring.py              (RF-14 — fórmula con uptime contextual)
│   │   └── weapon_optimizer.py            (RF-14 — rankings + build full)
│   ├── scripts\                           (background jobs / scrapers)
│   │   ├── scrape_enemies.py              (RF-13 — Hakush.in + Prydwen)
│   │   ├── scrape_prydwen_tierlist.py     (RF-13 — snapshot semanal de tier list)
│   │   └── scrape_prydwen_weapons.py      (RF-14 — snapshot semanal de armas por PJ)
│   ├── db\
│   │   ├── schema.py                      (migrations runner)
│   │   └── repositories.py                (queries parametrizadas por tabla)
│   ├── config\
│   │   ├── user_config.toml               (overrides del usuario; incluye ai_catalog.cap_usd_mensual y lategame.recalc_threshold)
│   │   └── defaults.toml                  (defaults compilados)
│   ├── resources\
│   │   ├── icon.ico
│   │   ├── templates\                     (screenshots de anclas visuales)
│   │   └── sounds\                        (feedback opcional)
│   └── build\
│       └── main.spec                      (PyInstaller spec file)
└── data\
    ├── discs_unequipped\                  (screenshots manuales)
    └── screenshots_auto\                  (capturas del pipeline)
```

---

*Generado con Claude — Abril 2026*  
*Continuar desarrollo con Claude Code en VS Code*

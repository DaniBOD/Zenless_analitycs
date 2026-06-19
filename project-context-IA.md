# project-context-IA.md

> **Propósito:** Snapshot condensado del proyecto para que un agente IA recupere el contexto esencial sin tener que leer todos los `.md` extensos. Si necesitas profundidad, ve al archivo "Fuente" indicado en cada sección.
>
> **Última verificación contra DB real:** 2026-05-01
> **Mantener actualizado tras cierre de fase, migración o cambio estructural.**
>
> **Módulos transversales:** [Documentacion/QA/](./Documentacion/QA/) (plan maestro + 7 sub-docs cubriendo ETL, scoring, OCR, IA, lategame, performance, regresión por patches).

---

## 1. Identidad del proyecto

- **Nombre:** Proyecto ZZZ — Analizador de cuenta DaniBOD (Zenless Zone Zero)
- **UID jugador:** 1000860143 · Servidor America · Top 6% global · 657 días activos
- **Inicio:** Abril 2026
- **Stack:** SQLite + Python 3.11+ + PySide6 (Qt6) + PyInstaller + OpenCV + mss + pynput + Tesseract + PaddleOCR + Anthropic SDK + httpx/BS4 + Claude Code (VS Code)
- **DB:** `db/danibod_zzz_v2.db` (SQLite monolítica, sincronizable a móvil copiando un archivo)
- **Reglas no negociables del proyecto:**
  - **RNF-01 ETL sin fallas** — toda carga/migración con `PRAGMA foreign_key_check` + `integrity_check`, transacciones, backups antes de merges, rastro auditable en README.
  - **RNF-02 Análisis minucioso** — cero shortcuts. Dato no confirmado ⇒ marcar tentativo con fuente, o NULL hasta validar. Fuentes autorizadas: Prydwen.gg, HoYoLAB, Game8, IcyVeins, 141store, Fandom oficial.
  - **RNF-03 Compatibilidad ToS HoYoverse** — solo pixels en pantalla. NUNCA inyección, lectura de memoria, simulación de inputs ni automatización de gameplay. Equivalente legal a Inventory Kamera (Genshin).
  - **RNF-06 Responsividad** — toast <500 ms, optimizador discos <500 ms, lookup RF-12 <50 ms, recálculo tier list <3 s, RAM idle <200 MB, CPU polling <3 %.

---

## 2. Visión funcional (qué hace el sistema)

Sistema de análisis y optimización de cuenta para ZZZ porque el juego carece de QoL para:
1. Evaluar discos al obtenerlos (¿guardo o borro?).
2. Comparar builds vs thresholds óptimos por personaje.
3. Planificar equipos para Shiyu Defense / Deadly Assault.
4. Detectar discos por screenshot (sin tocar el proceso del juego).
5. Visualizar matemáticamente el mejor equipo para un PJ (sinergias elemento/rol/facción/buffs/thresholds).
6. (Futuro) Analizar rotaciones para maximizar DPS real.

Único frontend en v1: `.exe` standalone (RF-11). No hay CLI ni web.

---

## 3. Estado real de la DB (verificado 2026-05-01)

**31 tablas de usuario** (32 si se cuenta `sqlite_sequence`).

| Capa | Tabla | Filas | Notas |
|------|-------|------:|-------|
| 1 Catálogos | `agents` | **47** | 45 originales + Cissia v2.7 (2026-05-04) + Billy Estelar v2.x (2026-06-12, onboarding PARCIAL: identidad+stats, pendiente synergy/splash/IA) |
| 1 | `weapons` | 53 | 49 base + 4 nuevas (Street Superstar, Florescencia aurífera, Wild Gastronome, Hertz Transit). Ya tiene `pasiva_modelada` + `sensibilidad_contexto` |
| 1 | `disc_sets` | 26 | Post-merge (id 47→40 Puffer Electro; id 50→35 Nana luz cenicienta) |
| 1 | `agent_awakenings` | **7** | 1 verificado (Burnice nv6) + 4 placeholder `pending_capture` (Lycaon, Ellen, Grace, N.°0:Anby) + 1 placeholder Cissia + 1 placeholder Billy Estelar. Harumasa y N.°11 sin insertar hasta confirmar nivel |
| 2 Inventarios | `agent_discs` | 270 | 45 PJs × 6 slots; incluye EMPTY (Antón, Ben, builds 3+3). Cissia usa inventory_discs directamente hasta sync RF-04 |
| 2 | `inventory_discs` | **334** | 263 equipados + 71 sueltos (+ 2 nuevos Cissia slot 4/6) |
| 2 | `inventory_weapons` | 50 | 40 equipadas + 10 sueltas |
| 3 Thresholds | `agent_thresholds` | **110** | 47/47 PJs con ≥1 stat · +5 Cissia · +2 Billy Estelar (CR/CDmg) |
| 3 | `agent_score_thresholds` | **47** | Defaults equip 0.75 / stock 0.50, overridable |
| 3 | `agent_substat_preferences` | 0 | Cae al arquetipo del rol hasta que se cargue |
| 4 Scoring | `disc_archetypes` | 6 | ATK_DPS, HP_DISRUPT, ANOMALY, STUN, SUPPORT_ER, DEFENSE |
| 4 | `disc_set_archetype` | 34 | N:M con prioridad 1=primario, 2=secundario |
| 4 | `inventory_disc_evaluations` | 0 | Histórico del scoring engine; crece con uso |
| 5 RF-06 | `optimizer_pending_actions` | 0 | TODO/APLICADO/DESCARTADO/OBSOLETO |
| 6 RF-12 | `team_synergies` | 0 | C(46,2)=1035 pares posibles; ~300+ esperados con sinergia |
| 6 | `team_compositions` | 0 | top-N por PJ principal |
| 6 | `ai_catalog_runs` | 0 | Auditoría llamadas Claude API |
| 7 RF-13 | `enemies` | 12 | 5 notorious + 3 bosses + 3 elites + 1 dummy |
| 7 | `enemy_resistances` | 72 | 12 × 6 elementos |
| 7 | `shiyu_cycles` / `da_cycles` | 0 / 0 | Esperan scraper |
| 7 | `lategame_runs` / `lategame_run_damage` | 0 / 0 | Captura F11 |
| 7 | `tier_list_personal` | 0 | Snapshots atómicos (no UPDATE) |
| 7 | `prydwen_tier_snapshots` | 0 | Snapshot semanal scraper |
| 7 | `team_synergy_adjustments` | 0 | Auditoría retro-feedback bayesiano |
| 8 RF-14 | `weapon_passives_structured` | 0 | Modelado formal pasivas (15 trigger_tipo) |
| 8 | `content_profiles` | 4 | seed: shiyu_critical, da, hollow_zero, general |
| 8 | `weapon_evaluations` | 0 | Cache scores (PJ × weapon × refinamiento × contenido) |
| 8 | `prydwen_weapon_recommendations_snapshots` | 0 | Snapshot semanal scraper |
| 8 | `pj_weapon_synergy` | **276** | 46 PJs × 6 categorías · Billy Estelar PENDIENTE (rol Disruptivos/Rupture sin matriz confirmada — RNF-02) |

**Migraciones aplicadas:** 9/9 (`01_archetypes_and_scoring`, `02_optimizer_pending`, `03_team_synergies`, `04_lategame_validation`, `05_weapon_optimizer`, `06_onboarding_cissia`, `07_re_estandarizacion`, `08_fix_archetypes_mains`, `09_add_protected_build`). Integrity OK, 0 FK violations.

**FK con CASCADE** (resto sin CASCADE para preservar histórico): `enemy_resistances.enemy_id`, `lategame_run_damage.run_id`, `team_synergy_adjustments.synergy_id`, `weapon_passives_structured.weapon_id`.

**Detalles del schema profundos:** `Documentacion/Modelo_Relacional/README.md`.

---

## 4. Mapa de Requerimientos Funcionales

| RF | Nombre | Estado | Doc fuente |
|----|--------|--------|------------|
| RF-01 | Estado completo del roster (45 PJs, stats, armas, discos, thresholds, awakenings) | ✅ Cerrado (gap: 4 awakenings con texto pendiente + Harumasa/N.°11 sin nivel) | README §3.1 |
| RF-02 | Inventario discos equipados + no equipados | ✅ Cerrado · 332 totales | README §3.1 |
| RF-03 | Inventario W-Engines | ✅ Cerrado · 50 totales | README §3.1 |
| RF-04 | Sync automático al cambiar discos en juego | 🟡 Implementado, pendiente QA en juego 2026-05-10 | `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` |
| RF-05 | Sync automático al mejorar discos (PRE/POST) | 🟡 Implementado, pendiente QA en juego 2026-05-10 | mismo doc, §upgrade |
| RF-06 | Optimizador build por PJ (greedy + bonus pass, top 3) | 🟦 Diseño cerrado | `Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md` |
| RF-07/08/10 | ❌ Descartados de v1 | — | (preservados como IDs vacíos) |
| RF-09 | OCR híbrido Tesseract (texto) + PaddleOCR (números), interfaz abstracta | 🟦 Diseño cerrado | RF-Captura_Discos §3.1 |
| RF-11 | UI standalone `.exe` (PySide6 + PyInstaller, tray + toast + panel 5 tabs) | 🟡 Implementado básico (.exe + tray + 5 tabs + toast 4 variants + LivePanel). Pendiente Hito 2.7: set logos + avatares target + click toast→panel | README §3.1 RF-11 |
| RF-12 | Optimizador team-aware (Claude API catalogadora offline + lookup determinista <50 ms) | 🟦 Diseño cerrado | `Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md` |
| RF-13 | Validación lategame (F11 OCR breakdown DMG) + tier list calibrada vs Prydwen + retro-feedback bayesiano | 🟦 Diseño cerrado | `Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md` |
| RF-14 | Optimizador W-Engines con scoring contextual + build full coordinada con RF-06 | 🟦 Diseño cerrado | `Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md` |

**Dependencia crítica resumida:**
```
RF-01 → RF-02/03/Thresholds/Awakenings → RF-04 → RF-06 → RF-12 → RF-13
                                                         ↘  RF-14
RF-09 precede RF-04/05 ; RF-11 consume RF-04/05/06/09 + scoring tables
RF-12 extiende RF-06 ; RF-13 retroalimenta RF-12 (confianza) + recalibra RF-14 (content_profiles)
RF-14 coordina con RF-06 (build full = arma + 6 discos)
```

---

## 5. Roadmap por fases

| Fase | Contenido | Estado |
|------|-----------|--------|
| 1 | Estado de PJs (RF-01/02/03 equipados) | ✅ Cerrada |
| 1.5 | Inventario completo (equipados + no equipados) | ✅ Cerrada |
| 1.6 | Schema arquetipos + scoring (mig 01) | ✅ Cerrada |
| 1.7 | Migraciones 02-05 + seeds iniciales (enemies, content_profiles, pj_weapon_synergy) | ✅ Cerrada |
| 2 | RF-04/05/06/09 implementación (captura + scoring + optimizador) | ✅ Cerrada (Hitos 2.0–2.6) |
| 3 | RF-12 implementación (team-aware + IA) | 📋 Pendiente |
| 4 | RF-13 implementación (lategame + tier list + bayesiano) | 📋 Pendiente |
| 5 | RF-14 implementación (W-Engines optimizer) | 📋 Pendiente |
| Transversal | RF-11 UI `.exe` | 📋 Pendiente |

**Estado actual real (2026-05-08):** Fase 2 completa + UI capturador básico + `.exe` empaquetado.
- Motor de captura: detector (9 templates), parser_disc por estado (S3/S6/S7/S10), monitor con polling adaptativo + hotkeys F8/F10, sync_equip + sync_upgrade.
- ROIs calibrados visualmente sobre 31 screenshots reales: secciones separadas `modal_detalle_s3` / `s6` / `s7` / `modal_upgrade_s10` en `rois.toml`. Tool `tools/annotate_rois.py` para validar.
- Pipeline E2E con OCR: tool `tools/run_pipeline_on_screenshots.py` listo (bloqueado por instalación de Tesseract).
- UI: `app/ui/{tokens.py, toast.py, live_panel.py, controller.py}` portados desde mockups con fidelidad alta. Toast con 4 variants + chamfered corners + glow + urgency bar animada.
- `.exe` standalone: 5.9 MB exe + 246 MB onedir, compilado con PyInstaller spec en `app/build/main.spec`. Shortcut al escritorio via `tools/create_shortcut.ps1`.
- 42 tests pasan (34 originales + 5 nuevos de mapping ROIs por estado + 3 de geometría).

**Siguiente:** QA en juego 2026-05-10 (ver `Documentacion/QA/Guia_QA_Domingo.md`). Pre-requisito: instalar Tesseract con `winget install UB-Mannheim.TesseractOCR`.

---

## 6. Roster (rápido)

**47 PJs** · Distribución elemento: Físico 14 · Eléctrico 12 · Fuego 9 · Éter 7 · Hielo 5
**Distribución rol:** Ataque 14 · Aturdimiento 9 · Anomalía 8 · Soporte 8 · Defensa 5 · Disruptivos 3

> Corrección rol/elemento mig 07+08 (2026-06-01): se reasignaron 6 roles mal seedeados
> (Pulchra→Aturdimiento, Lucía→Soporte, Ye Shunguang→Ataque, Yuzuha→Soporte, Dialyn→
> Aturdimiento, Ju Fufu→Aturdimiento). Synergy remapeada al rol corregido; thresholds de
> Ju Fufu/Yuzuha/Dialyn re-derivados (Prydwen/Game8). **Política de elementos:** atributos
> especiales se guardan como su equivalente estándar (Auric Ink→Éter, Frost→Hielo, Honed
> Edge→Físico); **Viento** agregado al dominio para PJs futuros. Ground truth pantalla S18
> QA 2026-05-31. Ver `audit/correccion_roles_elementos_20260601.md`.

**Niveles:** 41 en nv60 · 4 en nv55 (Harumasa, Seth, Ben, Antón, Corin)
**Performance:** Defensa Shiyu 94 809 (top 31.35 %) · Simulación Umbral 185 006 (top 43.21 %)

**Stunners principales:** Lycaon (M4, Impact 169, Hielo) · Koleda (M3, Fuego) · Qingyi (Eléctrico) · Anby (M6) · Pulchra (M6, Impact 189) · Gatillo
**DPS S-rank destacados:** Miyabi (Hielo Anomaly) · Yanagi (Eléctrico Anomaly A-arma) · Burnice (Fuego Anomaly) · Ellen (Hielo) · Zhu Yuan/Yixuan/Dialyn/Ye Shunguang (varios) · Manato M6 · Evelyn

**Bajo umbral críticos:** Miyabi CRIT 51.4/65 · Burnice ER 1.56/1.8 (despertar inactivo) · Soukaku/Lucy/Nekomata/Antón/Harumasa sin arma o subdesarrollados.

Detalle completo: README §5-6.

---

## 7. Decisiones cerradas que NO hay que revisar (a menos que se reabran)

- **OCR híbrido** Tesseract+PaddleOCR vía interfaz abstracta `app/core/ocr_backend.py` (swap futuro a Claude/GPT-4o vision).
- **`.exe` con PySide6 + PyInstaller**, tray + toast esquina inferior derecha + panel 5 tabs. Hotkeys F8 captura · F9 panel · F10 pausa · F11 RF-13 lategame · Ctrl+Shift+Z salir.
- **Toast solo accionables** (Equipar / Mejorar / Reserva ≥ stock). Resto al histórico.
- **RF-06 algoritmo:** greedy por slot top-K + bonus pass para set bonus 4pc/2+2+2/3+3.
- **RF-12 IA catalogadora, runtime determinista:** Claude API offline puebla `team_synergies` + `team_compositions`; runtime solo lee DB. Costo proyectado <$10/mes con prompt caching. Cap usuario en `user_config.toml::ai_catalog.cap_usd_mensual`.
- **RF-13 buckets fijos** S+ ≥90 / S 80-89 / A 65-79 / B 50-64 / C 30-49 / D 0-29 (no cuartiles). Tier list por contenido (Shiyu / DA / general).
- **RF-13 retro-feedback bayesiano:** `confianza_post = peso_prior × confianza_ai + peso_evidencia × likelihood`, `peso_prior = 1/(1+0.3·runs)`, likelihood capada en 1.5. Override manual con flag `congelado=1`.
- **RF-14 pesos scoring:** ATK 25 / stat secundario 15 / pasiva estructurada 40 / pasiva textual 10 / sinergia core 10 = 100 pts. Refinamiento R1↔R5 lineal (override disponible).
- **Snapshots atómicos** en `tier_list_personal` (no UPDATE; cada recálculo es nuevo snapshot_id).
- **Orden canónico** en `team_synergies` con CHECK `pj_a < pj_b` + UNIQUE.
- **Caso de prueba canónico RF-12:** Ellen + Dialyn → Puffer Electro debe aparecer con `confianza ≥ 0.85` y `tipo='core_passive_ult'`.
- **Caso canónico RF-14:** Núcleo Fosilizado Precioso ("la roca") debe rankear S+ en DA y B en HZ.

---

## 8. Estructura de directorios (mental map)

```
D:\Proyectos\Zenless_analitycs\
├── README.md                              ← doc maestro (1214 líneas)
├── project-context-IA.md                  ← ESTE archivo
├── db/
│   ├── danibod_zzz_v2.db                  ← DB activa
│   ├── danibod_zzz_v2.backup_*.db         ← backups pre-merge
│   └── migrations/                        ← 9 SQL aplicadas (última: 09_add_protected_build)
├── Documentacion/
│   ├── Modelo_Relacional/                 ← schema canónico + diagrama ER
│   ├── QA/                                ← plan maestro QA + 7 sub-docs (ETL, scoring, OCR, IA, lategame, performance, regresión)
│   ├── RF_Captura_Discos/                 ← RF-04/05/09
│   ├── RF_Optimizador/                    ← RF-06
│   ├── RF_Optimizador_Equipos/            ← RF-12
│   ├── RF_Lategame_Validation/            ← RF-13
│   ├── RF_Optimizador_Armas/              ← RF-14
│   ├── Interfaz/                          ← Brief diseño + assets (logos facciones, sets, engines, splashes, mockups)
│   ├── Diagramas de flujos/               ← rf_render_v3.py / v4.py + SVG/PNG segmentados por RF
│   ├── Onboarding_Nuevo_PJ.md             ← 8 pasos + checklist por patch
│   └── Onboarding_Nuevos_Assets.md        ← W-Engines / Sets / Facciones
├── Pj_stats/                              ← 45 screenshots HoYoLAB renombrados
├── Inventario/                            ← Armas_Inventario_faltantes/ + Discos_Inventario_faltantes/
├── Screenshots_Triggers/Discos_Triggers/  ← anclas visuales para detector OCR (12 carpetas 00-11)
├── audit/                                 ← discrepancy_report + image_mapping
└── app/                                   ← (NO existe aún) scaffold .exe pendiente RF-11
```

**App layout previsto** (cuando se implemente):
`app/main.py` · `app/ui/{toast,panel_detalle,build_optimizer_view,teams_view,lategame_view,weapons_view,settings_view}.py` · `app/core/{monitor,detector,capturer,ocr_backend,ocr_tesseract,ocr_paddle,scoring,recommender,sync_equip,sync_upgrade,optimizer,ai_catalog,team_optimizer,lategame_capture,tier_list_calculator,retro_feedback,weapon_scoring,weapon_optimizer}.py` · `app/scripts/{scrape_enemies,scrape_prydwen_tierlist,scrape_prydwen_weapons}.py` · `app/db/{schema,repositories}.py` · `app/config/{user_config,defaults}.toml` · `app/resources/{icon.ico,templates/,sounds/}` · `app/build/main.spec`.

---

## 9. Convenciones para futuras intervenciones de IA

1. **Antes de proponer cambios al schema:** leer `Documentacion/Modelo_Relacional/README.md`. Cualquier nueva tabla debe respetar la nomenclatura de capas (1-8) y registrarse ahí.
2. **Antes de aplicar SQL en la DB:** crear backup `db/danibod_zzz_v2.backup_YYYYMMDD_HHMMSS.db`, ejecutar dentro de transacción, correr `PRAGMA integrity_check; PRAGMA foreign_key_check;`.
3. **Antes de cargar datos de un PJ/W-Engine/Set/Facción nuevos:** seguir `Documentacion/Onboarding_Nuevo_PJ.md` o `Onboarding_Nuevos_Assets.md` (8 / 4-5 pasos respectivamente).
4. **Nunca inventar valores.** Si una stat o threshold no se valida con fuente, dejar NULL o `pending_capture` con `activo=0`. Documentar en README §6.2 o sección equivalente.
5. **Cuando se implemente algo nuevo:** actualizar la columna "Estado" del RF correspondiente en README §3.1 + §3.3 + esta tabla §4.
6. **Awakenings:** solo cargar texto desde screenshot in-game del usuario (RNF-02). No inferir desde guías externas.
7. **Cualquier merge de IDs** (sets/armas/PJs) requiere backup previo + log de filas afectadas en README.
8. **Para RF-12/14 con Claude API:** respetar `cap_usd_mensual` del usuario, usar prompt caching, registrar cada llamada en `ai_catalog_runs`.
9. **Antes de cerrar cualquier RF en producción:** consultar `Documentacion/QA/QA-0X_*.md` correspondiente y verificar la "cobertura mínima" listada al final del doc.
10. **Tras cada patch del juego:** ejecutar checklist `Documentacion/QA/QA-07_Regresion_Patches.md` paso a paso antes de tocar nada.
11. **Estilo de comunicación con Daniel (está aprendiendo a desarrollar con IA):** usar un **lenguaje semi-técnico** — ni puro jerga ni excesivamente simplificado. Cuando aparezca un concepto técnico complejo (p. ej. "descriptor", "umbral/threshold", "dedup", "early return", "Hough"), **aclararlo en el momento, en una frase**, sin asumir que ya se conoce. Preferir explicar el *porqué* de una decisión, no solo el *qué*. Reportes operativos cortos (ver CLAUDE.md §8).

---

## 10. Tareas pendientes inmediatas

**Pre-QA del 2026-05-10:**
1. **Instalar Tesseract OCR** — `winget install UB-Mannheim.TesseractOCR` + descargar `spa.traineddata` (3 min). Bloquea todo el pipeline OCR en vivo.
2. Correr `python tools/run_pipeline_on_screenshots.py` para generar reporte `audit/calibracion_<TS>.md` y validar OCR offline.
3. Ejecutar la **Guía QA del Domingo** (`Documentacion/QA/Guia_QA_Domingo.md`) paso a paso.

**Post-QA (Hito 2.7 — pulido UI):**
- Cargar set logos reales en `DiscThumb` (de `Documentacion/Interfaz/Sets_Logos/`).
- Cargar avatar real del target agent en el toast.
- Wiring: click en toast abre el panel principal.
- Re-ajustar coords de label vs chevron del toast si el QA detectó overlap.

**Backlog cierre Fase 1 (heredado):**
- Capturar texto in-game de awakenings nv1-6 para Lycaon, Ellen, Grace, N.°0:Anby.
- Confirmar nivel exacto de awakening de Asaba Harumasa y N.°11.
- Cargar `agent_substat_preferences` (~225 filas) desde Prydwen.

---

## 11. QA — capas, golden cases canónicos y módulo

**Filosofía:** RNF-01 (ETL sin fallas) + RNF-02 (cero shortcuts) son las reglas; QA las hace evidenciables.

**5 capas de testing:**

| L | Nombre | Quién | Cuándo |
|---|--------|-------|--------|
| L1 | Schema/datos (`PRAGMA` + scripts) | automático | tras cada migración o carga |
| L2 | Unit tests (funciones puras) | automático (`pytest`) | cada commit |
| L3 | Integration con fixture DB | automático | pre-merge a `main` |
| L4 | Pruebas reales en juego | **Daniel** | uso normal con app activa |
| L5 | Validación cruzada con fuentes | mixto | semanal + post-patch |

**Casos canónicos compartidos (los más mencionados):**

- **Ellen + Dialyn → Puffer Electro** (RF-12) — `confianza ≥ 0.85`, `tipo='core_passive_ult'`. Tras 5 runs con rate 3★=0.20, bayesiano debe llevar `confianza_post` a ~0.46 (RF-13) → desactiva override.
- **"La roca" / Núcleo Fosilizado Precioso** (RF-14) — debe ranquear S+ en DA y B en HZ por uptime contextual (HP enemigo > 50%).
- **Pasivas `trigger_tipo='always'`** (RF-14) — invariantes a contenido (delta < 5% entre Shiyu/DA/HZ/general).
- **Determinismo de scoring** (RF-06) — mismo input → mismo output 1000/1000 veces.
- **Caso `pj_a < pj_b`** en `team_synergies` — orden canónico siempre respetado.
- **Suma DMG ≈ 100%** en breakdown lategame (RF-13) — margen 2%.
- **Buckets fijos S+/S/A/B/C/D** con cortes 90/80/65/50/30 (RF-13).

**Módulo QA — 8 docs:**

| Doc | Cubre |
|-----|-------|
| [QA/README.md](./Documentacion/QA/README.md) | Plan maestro: 5 capas, matriz cobertura, criterios aceptación, roadmap por fase |
| [QA-01_ETL_Integridad.md](./Documentacion/QA/QA-01_ETL_Integridad.md) | Smoke test post-DB, baseline filas, constraints CHECK, idempotencia migraciones, política backups, awakenings RNF-02 |
| [QA-02_Scoring_y_Optimizador.md](./Documentacion/QA/QA-02_Scoring_y_Optimizador.md) | RF-06 + RF-14 golden cases (7 casos scoring + caso "la roca" + build full), validación cruzada Prydwen |
| [QA-03_OCR_y_Captura.md](./Documentacion/QA/QA-03_OCR_y_Captura.md) | RF-04/05/09 templates detector, golden set OCR (50 capturas con JSON), edge cases visuales, diff PRE/POST upgrade |
| [QA-04_IA_Catalogadora.md](./Documentacion/QA/QA-04_IA_Catalogadora.md) | RF-12 schema validator, hallucination detection, cap costo, prompt caching, **roadmap modelo local post-v1** (RX 9060 XT 16GB, opciones Ollama/llama.cpp, criterios switch) |
| [QA-05_Lategame_y_Bayesiano.md](./Documentacion/QA/QA-05_Lategame_y_Bayesiano.md) | RF-13 captura F11, buckets fijos, retro-feedback bayesiano (caso Ellen+Dialyn paso a paso), `congelado=1` |
| [QA-06_Performance_y_UX.md](./Documentacion/QA/QA-06_Performance_y_UX.md) | Decorator `@measure_latency`, tabla `metrics_latency` (a crear), pipeline disco→toast <500ms, hotkeys globales, multi-monitor |
| [QA-07_Regresion_Patches.md](./Documentacion/QA/QA-07_Regresion_Patches.md) | Workflow por patch ZZZ (~6 sem): backup → onboarding → re-scrape → recálculo → L4 → docs |

**Pendientes operativos del propio QA** (consolidados en QA/README §10):
- Crear migración `2026-05-XX_06_metrics_latency.sql` con tabla `metrics_latency` + decorator `@measure_latency`.
- Crear `app/tests/{unit,integration,regressions,fixtures}/`.
- Crear `app/tests/fixtures/golden_cases.json` con casos canónicos.
- Decidir framework: `pytest` + `pytest-cov` + `pytest-benchmark` (recomendado).
- Decidir CI: GitHub Actions (L1+L2+L3) o local con pre-commit hooks.

**Roadmap modelo local (post-v1, idea futura):** Ver QA-04 §9. Hardware RX 9060 XT 16GB. Opciones plausibles: Ollama+Qwen 2.5 14B Q4 (~10 GB VRAM, 32K ctx) o Mistral Small 22B Q4 (~14 GB, cerca del límite). Criterio para considerar el switch viable: coincidencia top-1 ≥ 85% sobre 100 pares canónicos vs Claude API + cobertura cruzada Prydwen ≥ 75%. **Recomendación de diseño:** la interfaz `ai_catalog.py::backend` debe ser abstracta desde v1 (`['claude','local','hybrid']`) aunque solo se implemente `claude` — el local se enchufa después sin tocar la lógica de validación L1/L5. Híbrido pragmático: Claude API para casos críticos + local para refresh masivo barato.

---

## 12. Glosario rápido (para no reinventar terminología)

- **Disco** = drive disc (artefacto/equipo) · **Slot** 1-6 · **Set** = bonus 2pc/4pc · **Mainstat** vs **Substat** + `rolls` (0-4 upgrades extra a nivel 3/6/9/12/15).
- **W-Engine** = arma · `refinamiento` 1-5 · `pasiva_tipo` semi-estructurado.
- **Disorder** = combo entre dos Anomalías de elementos distintos (alto daño).
- **Mindscape (M)** = constelación 0-6.
- **Awakening / Despertar / Silueta Potencial** = sistema v2.5+. "Agotado" en tienda = nv6 completado. "Límite xN" = parcial.
- **Shiyu Defense / Deadly Assault / Hollow Zero** = contenido lategame (`content_profiles`).
- **Threshold equip / stock** = score mínimo para equipar / guardar (defaults 0.75 / 0.50).
- **Anti-shill** = equipo objetivamente mejor que el "shilleado" por la comunidad (flag en `team_compositions`).
- **DaniBOD** = el usuario / cuenta del jugador (UID 1000860143).

---

*Si vas a expandir este archivo, mantén ≤300 líneas y prioriza tablas/listas sobre prosa. La intención es que un agente pueda leer este archivo en una sola pasada y tener el contexto suficiente para 80 % de las consultas, dejando los `.md` extensos para el 20 % restante.*

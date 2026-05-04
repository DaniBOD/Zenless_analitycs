# Modelo Relacional — `danibod_zzz_v2.db`

**Última actualización:** 2026-04-25
**Total de tablas:** 30 (5 migraciones aplicables)
**Diagrama:** [Modelo_Relacional_v1.svg](./Modelo_Relacional_v1.svg) · [PNG](./Modelo_Relacional_v1.png)
**Script de regeneración:** [render_mr.py](./render_mr.py)

Este documento describe el modelo relacional completo de la base, post-aplicación de las 5 migraciones (`01_archetypes_and_scoring` ya aplicada; `02..05` pendientes de implementación pero con SQL definitivo en `db/migrations/`).

## Vista de alto nivel — 8 capas

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CAPA 1 — CATÁLOGOS                  agents · weapons · disc_sets ·      │
│                                       agent_awakenings                    │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 2 — INVENTARIOS                agent_discs · inventory_discs ·     │
│                                       inventory_weapons                   │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 3 — THRESHOLDS Y PREFERENCIAS  agent_thresholds ·                  │
│  (mig 01)                             agent_score_thresholds ·            │
│                                       agent_substat_preferences           │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 4 — ARQUETIPOS Y SCORING       disc_archetypes ·                   │
│  (mig 01)                             disc_set_archetype ·                │
│                                       inventory_disc_evaluations          │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 5 — OPTIMIZADOR DE DISCOS      optimizer_pending_actions           │
│  (mig 02 — RF-06)                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 6 — TEAM-AWARE                 team_synergies · team_compositions ·│
│  (mig 03 — RF-12)                     ai_catalog_runs                     │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 7 — VALIDACIÓN LATEGAME        enemies · enemy_resistances ·       │
│  (mig 04 — RF-13)                     shiyu_cycles · da_cycles ·          │
│                                       lategame_runs · lategame_run_damage │
│                                       tier_list_personal ·                │
│                                       prydwen_tier_snapshots ·            │
│                                       team_synergy_adjustments            │
├──────────────────────────────────────────────────────────────────────────┤
│  CAPA 8 — OPTIMIZADOR DE ARMAS       weapon_passives_structured ·        │
│  (mig 05 — RF-14)                     content_profiles ·                  │
│                                       weapon_evaluations ·                │
│                                       prydwen_weapon_snapshots ·          │
│                                       pj_weapon_synergy                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Catálogo de tablas

### Capa 1 — Catálogos del juego

| Tabla | Filas iniciales | Descripción |
|-------|-----------------|-------------|
| `agents` | 45 | Roster completo. Stats efectivos de HoYoLAB, mindscape, FK a `weapons` y `disc_sets` (4p/2p equipados) |
| `weapons` | 49 + extensiones (mig 05) | Catálogo de W-Engines con `pasiva_tipo` semi-estructurado. Mig 05 agrega `pasiva_modelada` y `sensibilidad_contexto` |
| `disc_sets` | 26 | Catálogo de sets con `bonus_2p` y `bonus_4p_desc` |
| `agent_awakenings` | 1 cargado / 7 confirmados | Despertares con `version_juego` para escalabilidad. Pendiente: capturar texto de Lycaon/Ellen/Grace/N.º 0: Anby (Task #12) |

### Capa 2 — Inventarios

| Tabla | Filas iniciales | Descripción |
|-------|-----------------|-------------|
| `agent_discs` | 270 (45 PJs × 6 slots) | Discos equipados actualmente, slot por slot. Incluye EMPTY para Antón/Ben |
| `inventory_discs` | 332 (257 equipados + 75 sueltos) | Inventario completo. RF-04/05 lo expande con discos nuevos farmer-eados |
| `inventory_weapons` | 50 (40 equipadas + 10 sueltas) | Inventario de W-Engines con refinamiento real |

### Capa 3 — Thresholds y preferencias (migración 01)

| Tabla | Filas iniciales | Descripción |
|-------|-----------------|-------------|
| `agent_thresholds` | 103 | Umbrales mín/óptimo/máximo por stat con justificación + fuente |
| `agent_score_thresholds` | 45 (defaults) | Cortes de score `equipar` (0.75) y `upgrade` (0.50), overridable por usuario |
| `agent_substat_preferences` | 0 (vacía al inicio) | Overrides de pesos por PJ; cae al arquetipo primario hasta que se cargue |

### Capa 4 — Arquetipos y scoring (migración 01)

| Tabla | Filas iniciales | Descripción |
|-------|-----------------|-------------|
| `disc_archetypes` | 6 (seed) | ATK_DPS, HP_DISRUPT, ANOMALY, STUN, SUPPORT_ER, DEFENSE con pesos JSON |
| `disc_set_archetype` | 31 (26 sets + 5 dobles) | Mapping N:M con `prioridad` (1=primario, 2=secundario) |
| `inventory_disc_evaluations` | 0 | Histórico de recomendaciones del scoring engine. Crece con uso |

### Capa 5 — Optimizador de discos (migración 02 — RF-06)

| Tabla | Filas iniciales | Descripción |
|-------|-----------------|-------------|
| `optimizer_pending_actions` | 0 | Top-3 builds calculadas. Estados: TODO/APLICADO/DESCARTADO/OBSOLETO. JSON de build + swaps requeridos |

### Capa 6 — Team-aware (migración 03 — RF-12)

| Tabla | Filas esperadas | Descripción |
|-------|-----------------|-------------|
| `team_synergies` | ~990 (C(45,2)), ~300 con sinergia activa | Pares (pj_a < pj_b) con CHECK + UNIQUE. Override de pesos y set + `confianza` ajustable bayesianamente |
| `team_compositions` | ~225 (45 PJs × top-5) | Top-N composiciones de 3 PJs con `score_composicion`, `flag_anti_shill` |
| `ai_catalog_runs` | grow ~10/sem | Auditoría de cada llamada a Claude API: tokens, costo, duración, response_json opcional |

### Capa 7 — Validación lategame (migración 04 — RF-13)

| Tabla | Filas esperadas | Descripción |
|-------|-----------------|-------------|
| `enemies` | ~80 iniciales | Catálogo de bosses/notorious con `escalado_dificultad` JSON. Fuente Hakush.in + Prydwen |
| `enemy_resistances` | ~480 (80 × 6 elementos) | Multiplicador de daño por elemento + `breakdown_status` |
| `shiyu_cycles` | 1 inicial, +1 cada 2 sem | Ciclo activo de Shiyu Critical con `frentes` JSON |
| `da_cycles` | 1 inicial, +1 cada 2 sem | Ciclo activo de Deadly Assault con `entidades` JSON |
| `lategame_runs` | 0 al inicio, ~5-15/sem | Captura manual con F11. Equipo + estrellas + tiempo + breakdown DMG |
| `lategame_run_damage` | 3 × runs | Breakdown DMG por agente (posición, dmg_total, dmg_porcentaje, rol_efectivo) |
| `tier_list_personal` | ~135/snapshot | Tier S+/S/A/B/C/D por (PJ, contenido, snapshot_id). Histórico atómico |
| `prydwen_tier_snapshots` | 3 iniciales, +3/sem | Snapshot semanal de tier list general de Prydwen |
| `team_synergy_adjustments` | grow con uso | Auditoría del retro-feedback bayesiano sobre `team_synergies.confianza` |

### Capa 8 — Optimizador de armas (migración 05 — RF-14)

| Tabla | Filas esperadas | Descripción |
|-------|-----------------|-------------|
| `weapon_passives_structured` | ~80 iniciales | Modelado formal de pasivas (15 `trigger_tipo`, modifiers, `uptime_base`). UNIQUE(weapon, modifier_stat, trigger_tipo) |
| `content_profiles` | 4 (seed) | Shiyu Critical / DA / Hollow Zero / general con TTL boss, uptime HP>50%, frecuencias |
| `weapon_evaluations` | grow por snapshot | Cache de scores por (PJ, weapon, refinamiento, contenido). Lookup directo <5 ms |
| `prydwen_weapon_snapshots` | 45 iniciales, +45/sem | Recomendaciones de armas por PJ desde Prydwen para delta |
| `pj_weapon_synergy` | ~180 (45 × 4 categorías) | Bonus por compatibilidad PJ ↔ tipo de pasiva |

---

## Foreign Keys consolidadas

Lista canónica de las 30+ relaciones FK del modelo:

| Tabla origen | Columna | → | Tabla destino | Acción ON DELETE |
|--------------|---------|---|---------------|------------------|
| `agents` | weapon_id | → | weapons | (ninguna explícita) |
| `agents` | set_4p_id, set_2p_id | → | disc_sets | (ninguna) |
| `agent_awakenings` | agente_id | → | agents | (ninguna) |
| `agent_discs` | agente_id, set_id | → | agents, disc_sets | (ninguna) |
| `inventory_discs` | set_id, agente_asignado | → | disc_sets, agents | (ninguna) |
| `inventory_weapons` | weapon_id, agente_asignado | → | weapons, agents | (ninguna) |
| `agent_thresholds` | agente_id | → | agents | (ninguna) |
| `agent_score_thresholds` | agente_id | → | agents | (PK) |
| `agent_substat_preferences` | agente_id | → | agents | (PK compuesta) |
| `disc_set_archetype` | set_id, archetype_id | → | disc_sets, disc_archetypes | (PK compuesta) |
| `inventory_disc_evaluations` | inventory_disc_id | → | inventory_discs | (ninguna) |
| `optimizer_pending_actions` | agente_id | → | agents | (ninguna) |
| `team_synergies` | pj_a_id, pj_b_id | → | agents | (ninguna) — CHECK pj_a<pj_b |
| `team_synergies` | set_recomendado_pj_a/b | → | disc_sets | (ninguna, nullable) |
| `team_compositions` | pj_principal_id, pj_companion_1/2_id | → | agents | (ninguna, comp_2 nullable) |
| `enemy_resistances` | enemy_id | → | enemies | **CASCADE** |
| `lategame_runs` | pj_principal_id, pj_companion_1/2_id | → | agents | (ninguna) |
| `lategame_run_damage` | run_id, agent_id | → | lategame_runs, agents | **CASCADE** en run_id |
| `tier_list_personal` | pj_id | → | agents | (ninguna) |
| `team_synergy_adjustments` | synergy_id | → | team_synergies | **CASCADE** |
| `weapon_passives_structured` | weapon_id | → | weapons | **CASCADE** |
| `weapon_evaluations` | pj_id, weapon_id | → | agents, weapons | (ninguna) |
| `weapon_evaluations` | contenido | → | content_profiles(contenido) | (FK por TEXT, no ID) |
| `prydwen_weapon_snapshots` | pj_id | → | agents | (ninguna) |
| `pj_weapon_synergy` | pj_id | → | agents | (ninguna) |

**Nota sobre CASCADE:** se usa en relaciones donde el padre es "owner" del hijo (ej. borrar un `enemy` debería limpiar sus `enemy_resistances`). En el resto se evita CASCADE para preservar histórico (un PJ no debería borrar evaluaciones; se desactivan con flags).

---

## Constraints CHECK destacados

| Tabla | Constraint | Propósito |
|-------|------------|-----------|
| `team_synergies` | `CHECK (pj_a_id < pj_b_id)` | Orden canónico para evitar duplicados (a,b) y (b,a) |
| `team_synergies` | `confianza BETWEEN 0 AND 1` | Cota matemática del valor |
| `team_synergies` | `tipo IN (9 valores)` | Enum cerrado de tipos de sinergia |
| `weapon_passives_structured` | `trigger_tipo IN (15 valores)` | Enum cerrado de triggers (always, on_skill_use, enemy_hp_above, etc.) |
| `tier_list_personal` | `tier IN ('S+','S','A','B','C','D')` | Buckets fijos del tier system |
| `lategame_runs` | `estrellas BETWEEN 0 AND 3` | Validación numérica |
| `lategame_run_damage` | `dmg_porcentaje BETWEEN 0 AND 100` | Validación numérica |
| `optimizer_pending_actions` | `estado IN (TODO, APLICADO, DESCARTADO, OBSOLETO)` | Estado machine cerrada |
| `enemy_resistances` | `multiplicador REAL` | Cota implícita: 0=inmune, <1=resistente, >1=débil |

---

## Índices estratégicos

**Para el optimizador de discos (RF-06):**
- `idx_inv_set_slot ON inventory_discs(set_id, slot)` — lookup por slot al armar build
- `idx_inv_agente ON inventory_discs(agente_asignado)` — discos de un PJ específico
- `idx_opt_pending_agente_rank ON optimizer_pending_actions(agente_id, rank, estado)` — UI lookup

**Para el optimizador team-aware (RF-12):**
- `idx_team_syn_pj_a/b` — lookup por par desde cualquier dirección
- `idx_team_comp_principal ON team_compositions(pj_principal_id, contenido_optimo, rank_para_principal)` — UI top-N
- `idx_ai_runs_costo_mes` — query "cuánto gasté este mes" para el cap

**Para validación lategame (RF-13):**
- `idx_runs_pj_contenido` — agregaciones del tier list por (PJ, contenido)
- `idx_runs_equipo` — buscar runs de una composición específica para retro-feedback
- `idx_tier_pj_snap` y `idx_tier_contenido_snap` — UI navegación por snapshot
- `idx_synergy_adj_synergy` — auditoría de ajustes por sinergia

**Para optimizador de armas (RF-14):**
- `idx_weval_pj_contenido ON weapon_evaluations(pj_id, contenido, snapshot_id)` — lookup directo desde cache
- `idx_weval_score` — top-N rankings ordenados
- `idx_passives_trigger` — agrupar pasivas por trigger_tipo para análisis batch

---

## Decisiones de modelado

| Decisión | Justificación |
|----------|---------------|
| **`team_synergies` con orden canónico (pj_a < pj_b)** | Evita modelar (1,2) y (2,1) como pares distintos. Reduce espacio de 45² a C(45,2)=990. CHECK + UNIQUE garantizan integridad. |
| **`tier_list_personal` con `snapshot_id` (no UPDATE)** | Permite histórico atómico, rollback trivial, comparativos temporales. Costo de almacenamiento despreciable. |
| **`content_profiles` con `contenido` TEXT como PK natural** | Solo 4 valores fijos; usar TEXT permite que `weapon_evaluations.contenido` sea legible al inspeccionar. |
| **`agent_substat_preferences` vacía al inicio** | Cae a arquetipo del rol del PJ por default; el usuario llena gradualmente con datos de Prydwen. |
| **CASCADE en `enemy_resistances`/`lategame_run_damage`/`team_synergy_adjustments`** | Son tablas "hijas estrictas" — sin el padre no tienen significado. |
| **Sin CASCADE en `lategame_runs.pj_*`** | Borrar un PJ del roster no debería borrar runs históricos donde participó (preservar evidencia). |
| **JSON en columnas TEXT (`detalle_json`, `frentes`, `tier_data`, etc.)** | SQLite no tiene JSONB nativo pre-3.45. Trade-off: queries por contenido JSON son más lentas, pero el caso de uso es lookup primario por FK. |
| **Flag `congelado` en `team_synergies` y `team_compositions`** | Permite override manual del usuario que el job bayesiano de RF-13 respeta. |
| **`uptime_base` en `weapon_passives_structured`** | Estimación pesimista para cuando no hay `content_profile` aplicable. Default 1.0 si la pasiva es `trigger_tipo='always'`. |

---

## Relación con las migraciones SQL

| Migración | Archivo | Estado | Tablas creadas |
|-----------|---------|--------|----------------|
| 01 | `2026-04-24_01_archetypes_and_scoring.sql` | ✅ Aplicada | `disc_archetypes`, `disc_set_archetype`, `agent_substat_preferences`, `agent_score_thresholds`, `inventory_disc_evaluations` (5) |
| 02 | `2026-04-25_02_optimizer_pending.sql` | 📋 Pendiente | `optimizer_pending_actions` (1) |
| 03 | `2026-04-25_03_team_synergies.sql` | 📋 Pendiente | `team_synergies`, `team_compositions`, `ai_catalog_runs` (3) |
| 04 | `2026-04-25_04_lategame_validation.sql` | 📋 Pendiente | `enemies`, `enemy_resistances`, `shiyu_cycles`, `da_cycles`, `lategame_runs`, `lategame_run_damage`, `tier_list_personal`, `prydwen_tier_snapshots`, `team_synergy_adjustments` (9) |
| 05 | `2026-04-25_05_weapon_optimizer.sql` | 📋 Pendiente | `weapon_passives_structured`, `content_profiles`, `weapon_evaluations`, `prydwen_weapon_recommendations_snapshots`, `pj_weapon_synergy` (5) + ALTER `weapons` |

**Total tras aplicar las 5 migraciones:** 30 tablas + 2 columnas adicionales en `weapons` + ~40 índices.

---

## Validación tras aplicar migraciones

Las 4 migraciones nuevas (02-05) fueron testeadas en sandbox SQLite con schema mock (DB temporal en `/tmp`):

```
✓ 2026-04-25_02_optimizer_pending.sql
✓ 2026-04-25_03_team_synergies.sql
✓ 2026-04-25_04_lategame_validation.sql
✓ 2026-04-25_05_weapon_optimizer.sql

Pruebas funcionales:
✓ CHECK pj_a < pj_b en team_synergies funciona
✓ UNIQUE (pj_a, pj_b) funciona
✓ content_profiles seeded con 4 perfiles (da, general, hollow_zero, shiyu_critical)
✓ ALTER TABLE weapons agregó pasiva_modelada + sensibilidad_contexto
✓ Integrity check: ok
✓ Foreign key check: 0 violations
```

Aplicación recomendada en producción:

```bash
sqlite3 db/danibod_zzz_v2.db < db/migrations/2026-04-25_02_optimizer_pending.sql
sqlite3 db/danibod_zzz_v2.db < db/migrations/2026-04-25_03_team_synergies.sql
sqlite3 db/danibod_zzz_v2.db < db/migrations/2026-04-25_04_lategame_validation.sql
sqlite3 db/danibod_zzz_v2.db < db/migrations/2026-04-25_05_weapon_optimizer.sql
sqlite3 db/danibod_zzz_v2.db "PRAGMA integrity_check; PRAGMA foreign_key_check;"
```

Aplicar en orden estricto. La migración 04 no añade `congelado` directamente a `team_synergies` (lo hace mediante el modelado del flag en la propia tabla en mig 03), eliminando dependencia de orden ALTER.

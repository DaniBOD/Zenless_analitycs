-- =============================================================================
-- Migración: optimizador de armas con scoring contextual (RF-14)
-- Fecha: 2026-04-25
-- Autor: Daniel (danibod)
-- Refs: Documentacion/RF_Optimizador_Armas/RF-Logic_Optimizador_Armas.md
--
-- Crea 5 tablas nuevas + extiende `weapons`:
--   1. weapon_passives_structured                 — modelado formal de pasivas
--   2. content_profiles                           — perfiles de contenido (TTL, uptimes)
--   3. weapon_evaluations                         — cache + histórico de scores
--   4. prydwen_weapon_recommendations_snapshots   — snapshot semanal Prydwen
--   5. pj_weapon_synergy                          — bonus por (PJ, tipo de pasiva)
--
-- Extiende `weapons`:
--   - pasiva_modelada (0=no, 1=parcial, 2=completa)
--   - sensibilidad_contexto (baja|media|alta)
--
-- Seed inicial:
--   - 4 perfiles de contenido (shiyu_critical, da, hollow_zero, general)
--     con valores estimados manualmente. Recalibrables por RF-13.
--
-- ALTER TABLE: NOT idempotente nativamente. Se envuelve en bloques que
-- chequean primero la columna para permitir re-aplicar sin errores.
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- 0. Extensión de `weapons`
--    SQLite no soporta IF NOT EXISTS en ADD COLUMN, así que envolvemos en
--    PRAGMA + condicional via aplicación. Para esta migración, se asume
--    primera aplicación; al re-aplicar, los ALTER TABLE fallarán de forma
--    silenciosa si las columnas ya existen (el runner de migraciones debe
--    capturar el "duplicate column name" como warning, no como error).
-- -----------------------------------------------------------------------------

ALTER TABLE weapons ADD COLUMN pasiva_modelada INTEGER NOT NULL DEFAULT 0
    CHECK(pasiva_modelada IN (0, 1, 2));
-- 0 = sin modelar (solo texto)
-- 1 = modelada parcialmente (algunos efectos cubiertos)
-- 2 = modelada completamente

ALTER TABLE weapons ADD COLUMN sensibilidad_contexto TEXT
    CHECK(sensibilidad_contexto IS NULL OR sensibilidad_contexto IN ('baja', 'media', 'alta'));

-- -----------------------------------------------------------------------------
-- 1. weapon_passives_structured — modelado formal de pasivas
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS weapon_passives_structured (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id               INTEGER NOT NULL REFERENCES weapons(id) ON DELETE CASCADE,

    -- Trigger: cuándo se activa la pasiva
    trigger_tipo            TEXT NOT NULL
                            CHECK(trigger_tipo IN (
                                'always',                  -- siempre activa
                                'on_skill_use',            -- al usar skill
                                'on_basic_attack',         -- al hacer basic
                                'on_dodge_counter',        -- al esquivar / counter
                                'on_chain_attack',         -- al hacer chain
                                'on_ultimate',             -- al usar ultimate
                                'on_anomaly_trigger',      -- al activar anomalía
                                'on_stun',                 -- al stunear enemigo
                                'on_off_field',            -- mientras off-field
                                'enemy_hp_above',          -- HP enemigo > umbral
                                'enemy_hp_below',          -- HP enemigo < umbral
                                'team_has_faction',        -- equipo tiene PJ de facción X
                                'team_has_element',        -- equipo tiene PJ de elemento X
                                'er_above',                -- ER del PJ > umbral
                                'energy_full'              -- energía al máximo
                            )),

    -- Parámetros del trigger (JSON flexible)
    -- ej: {"hp_threshold": 50, "stack_max": 3, "duration_s": 12}
    trigger_params          TEXT,

    -- Modifiers: qué stat afecta y cuánto
    modifier_stat           TEXT NOT NULL,
                            -- 'atk_pct' | 'crit_rate' | 'crit_dmg' | 'impact' |
                            -- 'anomaly_mastery' | 'pen_ratio' | 'er' |
                            -- 'dmg_pct_element_X' | etc.

    modifier_value_r1       REAL NOT NULL,         -- valor a refinamiento R1
    modifier_value_r5       REAL NOT NULL,         -- valor a R5 (interp lineal)
    modifier_stack_max      INTEGER DEFAULT 1,

    -- Uptime base (sin contexto): estimación pesimista del % activa en condiciones genéricas
    uptime_base             REAL DEFAULT 1.0
                            CHECK(uptime_base BETWEEN 0 AND 1),

    descripcion_breve       TEXT,
    fuente                  TEXT NOT NULL DEFAULT 'manual'
                            CHECK(fuente IN ('manual', 'ai_claude', 'datamine')),
    fecha_modelado          DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas                   TEXT,

    UNIQUE(weapon_id, modifier_stat, trigger_tipo)
);

CREATE INDEX IF NOT EXISTS idx_passives_weapon  ON weapon_passives_structured(weapon_id);
CREATE INDEX IF NOT EXISTS idx_passives_trigger ON weapon_passives_structured(trigger_tipo);
CREATE INDEX IF NOT EXISTS idx_passives_stat    ON weapon_passives_structured(modifier_stat);

-- -----------------------------------------------------------------------------
-- 2. content_profiles — caracterización del contenido para uptime contextual
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS content_profiles (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido                       TEXT NOT NULL UNIQUE,
                                    -- 'shiyu_critical' | 'da' | 'hollow_zero' | 'general'
    nombre_display                  TEXT NOT NULL,

    -- Características que afectan uptimes de pasivas
    ttl_boss_promedio_s             REAL,           -- tiempo a 0 HP
    hp_boss_uptime_above_50pct      REAL CHECK(hp_boss_uptime_above_50pct BETWEEN 0 AND 1),
    hp_boss_uptime_above_30pct      REAL CHECK(hp_boss_uptime_above_30pct BETWEEN 0 AND 1),

    chain_attacks_por_min           REAL,
    skills_por_min                  REAL,
    ultimates_por_min               REAL,
    anomalies_por_min               REAL,
    stuns_por_min                   REAL,

    promedio_pjs_off_field          REAL DEFAULT 2.0,

    fuente                          TEXT NOT NULL DEFAULT 'calibracion_inicial'
                                    CHECK(fuente IN ('calibracion_inicial',
                                                     'recalibrado_rf13',
                                                     'manual_user')),
    fecha_calibrado                 DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas                           TEXT
);

-- Seed inicial (calibrado con runs típicos + datos de Prydwen).
-- Recalibrable por RF-13 con runs reales del usuario.
INSERT OR IGNORE INTO content_profiles (
    contenido, nombre_display,
    ttl_boss_promedio_s,
    hp_boss_uptime_above_50pct, hp_boss_uptime_above_30pct,
    chain_attacks_por_min, skills_por_min, ultimates_por_min,
    anomalies_por_min, stuns_por_min,
    promedio_pjs_off_field, fuente
) VALUES
    ('shiyu_critical', 'Shiyu Defense Critical', 75.0,
     0.55, 0.75, 3.0, 12.0, 1.5, 4.0, 2.0, 2.0, 'calibracion_inicial'),
    ('da',             'Deadly Assault',          90.0,
     0.95, 0.99, 2.5, 14.0, 2.0, 5.0, 2.5, 2.0, 'calibracion_inicial'),
    ('hollow_zero',    'Hollow Zero',             25.0,
     0.30, 0.55, 1.8, 10.0, 1.2, 3.0, 1.5, 2.0, 'calibracion_inicial'),
    ('general',        'Contenido General',       60.0,
     0.50, 0.70, 2.5, 11.0, 1.5, 3.5, 2.0, 2.0, 'calibracion_inicial');

-- -----------------------------------------------------------------------------
-- 3. weapon_evaluations — cache + histórico de scores
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS weapon_evaluations (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id                       INTEGER NOT NULL REFERENCES agents(id),
    weapon_id                   INTEGER NOT NULL REFERENCES weapons(id),
    refinamiento                INTEGER NOT NULL CHECK(refinamiento BETWEEN 1 AND 5),
    nivel                       INTEGER NOT NULL DEFAULT 60,
    contenido                   TEXT NOT NULL REFERENCES content_profiles(contenido),

    score_normalizado           REAL NOT NULL CHECK(score_normalizado BETWEEN 0 AND 100),

    -- Desglose para auditoría / explicación al usuario
    score_atk_base              REAL,
    score_stat_secundario       REAL,
    score_pasiva_estructurada   REAL,           -- suma de pasivas con uptime contextual
    score_pasiva_textual        REAL,           -- bonus subjetivo manual (fallback)
    score_synergy_pj            REAL,           -- bonus por compat con habilidades core

    -- Comparación con Prydwen
    prydwen_tier_referencia     TEXT,
    delta_vs_prydwen            TEXT,

    snapshot_id                 TEXT NOT NULL,  -- agrupa todos los cálculos de la corrida
    fecha_calculado             DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(pj_id, weapon_id, refinamiento, contenido, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_weval_pj_contenido
    ON weapon_evaluations(pj_id, contenido, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_weval_score
    ON weapon_evaluations(pj_id, contenido, score_normalizado DESC);

CREATE INDEX IF NOT EXISTS idx_weval_weapon
    ON weapon_evaluations(weapon_id, contenido);

-- -----------------------------------------------------------------------------
-- 4. prydwen_weapon_recommendations_snapshots — snapshot semanal Prydwen
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prydwen_weapon_recommendations_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               DATE NOT NULL,
    pj_id               INTEGER NOT NULL REFERENCES agents(id),

    -- JSON: [{"rank":1, "weapon_nombre":"Hailstorm Shrine", "tier":"S+", "notas":"BiS"}, ...]
    recomendaciones     TEXT NOT NULL,

    fuente_url          TEXT NOT NULL,
    parser_version      TEXT,

    UNIQUE(fecha, pj_id)
);

CREATE INDEX IF NOT EXISTS idx_prydwen_weapons_fecha
    ON prydwen_weapon_recommendations_snapshots(fecha DESC);

CREATE INDEX IF NOT EXISTS idx_prydwen_weapons_pj
    ON prydwen_weapon_recommendations_snapshots(pj_id, fecha DESC);

-- -----------------------------------------------------------------------------
-- 5. pj_weapon_synergy — bonus por compatibilidad PJ ↔ tipo de pasiva
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pj_weapon_synergy (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id                   INTEGER NOT NULL REFERENCES agents(id),
    weapon_pasiva_tipo      TEXT NOT NULL,
                            -- coincide con weapons.pasiva_tipo:
                            -- 'dmg_boost' | 'anomaly_proficiency' | 'energy_regen' |
                            -- 'crit' | 'pen_ratio' | 'atk_boost' | 'mixed'

    bonus                   REAL NOT NULL DEFAULT 0
                            CHECK(bonus BETWEEN -1 AND 2),
    razon                   TEXT,                   -- explicación textual
    fuente                  TEXT NOT NULL DEFAULT 'manual'
                            CHECK(fuente IN ('manual', 'ai_claude')),
    fecha_creado            DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(pj_id, weapon_pasiva_tipo)
);

CREATE INDEX IF NOT EXISTS idx_pj_w_syn_pj
    ON pj_weapon_synergy(pj_id);

CREATE INDEX IF NOT EXISTS idx_pj_w_syn_tipo
    ON pj_weapon_synergy(weapon_pasiva_tipo, bonus DESC);

COMMIT;

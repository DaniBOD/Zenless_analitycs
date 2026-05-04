-- =============================================================================
-- Migración: validación lategame + tier list personal + retro-feedback (RF-13)
-- Fecha: 2026-04-25
-- Autor: Daniel (danibod)
-- Refs: Documentacion/RF_Lategame_Validation/RF-Logic_Lategame_Validation.md
--
-- Crea 9 tablas nuevas:
--   1. enemies                          — catálogo de bosses/notorious del juego
--   2. enemy_resistances                — resistencias por elemento
--   3. shiyu_cycles                     — ciclos rotativos de Shiyu Critical
--   4. da_cycles                        — ciclos rotativos de Deadly Assault
--   5. lategame_runs                    — registro primario de runs
--   6. lategame_run_damage              — breakdown DMG por agente del run
--   7. tier_list_personal               — tabla calculada con histórico atómico
--   8. prydwen_tier_snapshots           — snapshots semanales de tier list Prydwen
--   9. team_synergy_adjustments         — auditoría de ajustes bayesianos
--
-- Sin seed: las tablas se pueblan por captura manual + scrapers + recálculo.
--
-- Idempotente.
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- 1. enemies — catálogo de enemigos
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enemies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_es           TEXT NOT NULL UNIQUE,
    nombre_en           TEXT,
    tipo                TEXT NOT NULL
                        CHECK(tipo IN ('normal', 'elite', 'boss', 'notorious_hunter')),
    faccion             TEXT,                       -- 'Ethereal' | 'Thiren' | 'Notorious Hunter' | etc.
    hp_base             INTEGER,                    -- HP a nivel de referencia
    nivel_referencia    INTEGER DEFAULT 80,

    -- JSON: {"shiyu_critical": 1.5, "da_high": 2.0, "hollow_zero_l3": 1.2}
    escalado_dificultad TEXT,

    mecanicas_clave     TEXT,                       -- texto libre
    fuente              TEXT NOT NULL
                        CHECK(fuente IN ('hakush.in', 'prydwen', 'manual', 'fandom')),
    fuente_url          TEXT,
    fecha_actualizado   DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas               TEXT
);

CREATE INDEX IF NOT EXISTS idx_enemies_tipo    ON enemies(tipo);
CREATE INDEX IF NOT EXISTS idx_enemies_faccion ON enemies(faccion);

-- -----------------------------------------------------------------------------
-- 2. enemy_resistances
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enemy_resistances (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    enemy_id            INTEGER NOT NULL REFERENCES enemies(id) ON DELETE CASCADE,
    elemento            TEXT NOT NULL
                        CHECK(elemento IN ('fisico', 'fuego', 'hielo', 'electrico', 'eter', 'frost')),

    -- 1.0 = neutral; <1.0 = resistente; >1.0 = débil; 0 = inmune
    multiplicador       REAL NOT NULL DEFAULT 1.0,
    breakdown_status    TEXT
                        CHECK(breakdown_status IS NULL OR
                              breakdown_status IN ('weak', 'neutral', 'resistant', 'immune')),
    notas               TEXT,

    UNIQUE(enemy_id, elemento)
);

CREATE INDEX IF NOT EXISTS idx_enemy_res_enemy ON enemy_resistances(enemy_id);
CREATE INDEX IF NOT EXISTS idx_enemy_res_elem  ON enemy_resistances(elemento, multiplicador);

-- -----------------------------------------------------------------------------
-- 3. shiyu_cycles
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shiyu_cycles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number    INTEGER NOT NULL UNIQUE,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,

    -- JSON array: [{"frente":1, "bosses":[enemy_id,...], "modificadores":"...",
    --               "elemento_recomendado":"..."}, ...]
    frentes         TEXT NOT NULL,

    fuente          TEXT NOT NULL DEFAULT 'prydwen',
    fecha_capturado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas           TEXT
);

CREATE INDEX IF NOT EXISTS idx_shiyu_fecha
    ON shiyu_cycles(fecha_inicio, fecha_fin);

-- -----------------------------------------------------------------------------
-- 4. da_cycles
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS da_cycles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number    INTEGER NOT NULL UNIQUE,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,

    -- JSON array: [{"slot":1, "enemy_id":N, "modificadores":"...",
    --               "weakness_recomendada":"..."}, ...]
    entidades       TEXT NOT NULL,

    fuente          TEXT NOT NULL DEFAULT 'prydwen',
    fecha_capturado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas           TEXT
);

CREATE INDEX IF NOT EXISTS idx_da_fecha
    ON da_cycles(fecha_inicio, fecha_fin);

-- -----------------------------------------------------------------------------
-- 5. lategame_runs — registro primario de evidencia
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lategame_runs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha                       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    contenido                   TEXT NOT NULL
                                CHECK(contenido IN ('shiyu_critical', 'shiyu_normal', 'da', 'hollow_zero')),

    -- FK condicional según contenido (NULL para 'shiyu_normal' y 'hollow_zero' v1)
    cycle_id                    INTEGER,

    -- Frente 1-9 para Shiyu, slot 1-3 para DA
    frente_o_slot               INTEGER NOT NULL,

    -- Equipo usado
    pj_principal_id             INTEGER NOT NULL REFERENCES agents(id),
    pj_companion_1_id           INTEGER REFERENCES agents(id),
    pj_companion_2_id           INTEGER REFERENCES agents(id),
    pj_bangboo_id               INTEGER,                -- futuro: cuando se modele bangboos

    -- Resultados
    estrellas                   INTEGER NOT NULL CHECK(estrellas BETWEEN 0 AND 3),
    tiempo_segundos             REAL,                   -- NULL si DA (DA reporta score)
    score_juego                 INTEGER,                -- score que muestra el juego
    completado                  INTEGER NOT NULL DEFAULT 1 CHECK(completado IN (0, 1)),

    -- Trazabilidad
    screenshot_resumen_path     TEXT,
    screenshot_breakdown_path   TEXT,
    fuente_captura              TEXT NOT NULL DEFAULT 'manual_ocr'
                                CHECK(fuente_captura IN ('manual_ocr', 'manual_typed')),

    notas                       TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_fecha
    ON lategame_runs(fecha DESC);

CREATE INDEX IF NOT EXISTS idx_runs_pj_contenido
    ON lategame_runs(pj_principal_id, contenido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_runs_equipo
    ON lategame_runs(pj_principal_id, pj_companion_1_id, pj_companion_2_id);

CREATE INDEX IF NOT EXISTS idx_runs_cycle
    ON lategame_runs(contenido, cycle_id);

-- -----------------------------------------------------------------------------
-- 6. lategame_run_damage — breakdown DMG por agente del run
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lategame_run_damage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES lategame_runs(id) ON DELETE CASCADE,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    posicion        INTEGER NOT NULL CHECK(posicion BETWEEN 1 AND 3),

    dmg_total       INTEGER NOT NULL,
    dmg_porcentaje  REAL NOT NULL CHECK(dmg_porcentaje BETWEEN 0 AND 100),

    rol_efectivo    TEXT
                    CHECK(rol_efectivo IS NULL OR
                          rol_efectivo IN ('main_dps', 'sub_dps', 'support_dmg', 'enabler')),

    UNIQUE(run_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_run_dmg_agent
    ON lategame_run_damage(agent_id);

CREATE INDEX IF NOT EXISTS idx_run_dmg_run
    ON lategame_run_damage(run_id, posicion);

-- -----------------------------------------------------------------------------
-- 7. tier_list_personal — tabla con histórico atómico (snapshot_id)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tier_list_personal (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id                       INTEGER NOT NULL REFERENCES agents(id),

    -- Granularidad: 'shiyu_global' | 'da_global' | 'shiyu_fuego' | 'da_eter' |
    --               'shiyu_frente_1' | 'general' | etc. — diseño extensible
    contenido                   TEXT NOT NULL,

    tier                        TEXT NOT NULL
                                CHECK(tier IN ('S+', 'S', 'A', 'B', 'C', 'D')),
    score_normalizado           REAL NOT NULL CHECK(score_normalizado BETWEEN 0 AND 100),

    -- Métricas agregadas que justifican el tier
    runs_evaluados              INTEGER NOT NULL,
    win_rate                    REAL,
    rate_3_estrellas            REAL,
    avg_dmg_share               REAL,
    avg_tiempo_normalizado      REAL,                   -- tiempo / par_3star

    -- Comparación con Prydwen
    delta_vs_prydwen            TEXT,                   -- '+2', '+1', '=', '-1', '-2'
    prydwen_tier_referencia     TEXT,
    justificacion               TEXT,                   -- texto autogenerado

    fecha_calculado             DATETIME DEFAULT CURRENT_TIMESTAMP,
    snapshot_id                 TEXT NOT NULL,          -- agrupa toda una corrida

    UNIQUE(pj_id, contenido, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_tier_pj_snap
    ON tier_list_personal(pj_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_tier_contenido_snap
    ON tier_list_personal(contenido, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_tier_score
    ON tier_list_personal(contenido, snapshot_id, score_normalizado DESC);

-- -----------------------------------------------------------------------------
-- 8. prydwen_tier_snapshots — snapshots semanales para comparativos históricos
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prydwen_tier_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           DATE NOT NULL,
    contenido       TEXT NOT NULL
                    CHECK(contenido IN ('shiyu', 'da', 'general')),

    -- JSON: {"Yanagi":"S+", "Burnice":"S", ...}
    tier_data       TEXT NOT NULL,
    fuente_url      TEXT NOT NULL,
    parser_version  TEXT,

    UNIQUE(fecha, contenido)
);

CREATE INDEX IF NOT EXISTS idx_prydwen_fecha
    ON prydwen_tier_snapshots(fecha DESC, contenido);

-- -----------------------------------------------------------------------------
-- 9. team_synergy_adjustments — auditoría del retro-feedback bayesiano
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS team_synergy_adjustments (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    synergy_id              INTEGER NOT NULL REFERENCES team_synergies(id) ON DELETE CASCADE,
    fecha                   DATETIME DEFAULT CURRENT_TIMESTAMP,

    confianza_anterior      REAL NOT NULL,
    confianza_nueva         REAL NOT NULL,

    runs_evidencia          INTEGER NOT NULL,
    rate_3star_observado    REAL,

    motivo                  TEXT NOT NULL
                            CHECK(motivo IN ('rf13_bayesiano', 'manual_user', 'congelado_off')),

    notas                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_synergy_adj_synergy
    ON team_synergy_adjustments(synergy_id, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_synergy_adj_motivo
    ON team_synergy_adjustments(motivo, fecha DESC);

COMMIT;

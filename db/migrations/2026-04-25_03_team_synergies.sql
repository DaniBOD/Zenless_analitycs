-- =============================================================================
-- Migración: team_synergies + team_compositions + ai_catalog_runs (RF-12)
-- Fecha: 2026-04-25
-- Autor: Daniel (danibod)
-- Refs: Documentacion/RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md
--
-- Crea 3 tablas nuevas:
--   1. team_synergies        — pares ordenados (pj_a < pj_b) con overrides
--   2. team_compositions     — top-N composiciones de 3 PJs por personaje principal
--   3. ai_catalog_runs       — auditoría de cada llamada a Claude API
--
-- Convención: pj_a_id < pj_b_id SIEMPRE (constraint CHECK + UNIQUE).
--             Espacio máximo: C(45,2) = 990 pares.
--             Espera ~300 pares con sinergia activa (sinergia_existe=1).
--
-- Sin seed: poblada por el catalogador IA en background tras la migración.
--
-- Idempotente.
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- 1. team_synergies — par PJ_a × PJ_b
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS team_synergies (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_a_id                     INTEGER NOT NULL REFERENCES agents(id),
    pj_b_id                     INTEGER NOT NULL REFERENCES agents(id),

    -- ¿Existe sinergia documentada/inferida? Permite catalogar negativos también.
    sinergia_existe             INTEGER NOT NULL CHECK(sinergia_existe IN (0, 1)),

    -- Tipo de sinergia (NULL si sinergia_existe=0).
    tipo                        TEXT
                                CHECK(tipo IS NULL OR tipo IN (
                                    'disorder_elemento',
                                    'additional_ability_faccion',
                                    'core_passive_ult',
                                    'core_passive_buff',
                                    'shield_synergy',
                                    'energy_battery',
                                    'stunner_buff_dps',
                                    'rotation_compatible',
                                    'otro'
                                )),

    -- Overrides — pueden ser NULL si no aplica
    set_recomendado_pj_a        INTEGER REFERENCES disc_sets(id),
    set_recomendado_pj_b        INTEGER REFERENCES disc_sets(id),

    -- JSON: {"stat": peso_override, ...} — override sobre agent_substat_preferences
    pesos_substat_override_pj_a TEXT,
    pesos_substat_override_pj_b TEXT,

    -- Descripción del buff/efecto
    buff_descripcion            TEXT,

    -- Confianza [0..1]. Initial = lo que dice Claude API; ajustable por RF-13.
    confianza                   REAL NOT NULL DEFAULT 0.5
                                CHECK(confianza BETWEEN 0 AND 1),

    -- Trazabilidad
    fuente                      TEXT NOT NULL DEFAULT 'ai_claude'
                                CHECK(fuente IN ('ai_claude', 'manual_user', 'manual_official')),
    modelo_version              TEXT,                  -- 'claude-sonnet-4-6' | 'claude-opus-4-6'
    fecha_generado              DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizado           DATETIME,

    -- Override manual: si Daniel ajusta `confianza` o decisión, queda congelada
    -- y el job bayesiano de RF-13 deja de tocarla.
    congelado                   INTEGER NOT NULL DEFAULT 0 CHECK(congelado IN (0, 1)),

    notas                       TEXT,

    -- Constraints a nivel de tabla
    UNIQUE(pj_a_id, pj_b_id),
    CHECK (pj_a_id < pj_b_id)        -- orden canónico para evitar duplicados (a,b) y (b,a)
);

CREATE INDEX IF NOT EXISTS idx_team_syn_pj_a       ON team_synergies(pj_a_id);
CREATE INDEX IF NOT EXISTS idx_team_syn_pj_b       ON team_synergies(pj_b_id);
CREATE INDEX IF NOT EXISTS idx_team_syn_existe     ON team_synergies(sinergia_existe, confianza DESC);
CREATE INDEX IF NOT EXISTS idx_team_syn_tipo       ON team_synergies(tipo) WHERE tipo IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 2. team_compositions — top-N composiciones de 3 PJs
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS team_compositions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_principal_id     INTEGER NOT NULL REFERENCES agents(id),
    pj_companion_1_id   INTEGER NOT NULL REFERENCES agents(id),
    pj_companion_2_id   INTEGER REFERENCES agents(id),  -- NULL para duos especiales

    -- Score normalizado 0-100 (score_composicion)
    score_composicion   REAL NOT NULL CHECK(score_composicion BETWEEN 0 AND 100),
    rank_para_principal INTEGER NOT NULL CHECK(rank_para_principal >= 1),

    -- Para qué contenido se evaluó: 'shiyu_critical' | 'da' | 'general' | 'hollow_zero'
    contenido_optimo    TEXT NOT NULL DEFAULT 'general',

    justificacion       TEXT,

    -- JSON array: ["disorder_elemento", "additional_ability_faccion", ...]
    sinergias_activadas TEXT,

    requiere_stunner    INTEGER NOT NULL DEFAULT 0 CHECK(requiere_stunner IN (0, 1)),

    -- True cuando la composición es objetivamente mejor que la "shilleada"
    -- por la comunidad para este PJ.
    flag_anti_shill     INTEGER NOT NULL DEFAULT 0 CHECK(flag_anti_shill IN (0, 1)),

    -- Trazabilidad
    fuente              TEXT NOT NULL DEFAULT 'ai_claude'
                        CHECK(fuente IN ('ai_claude', 'manual_user')),
    modelo_version      TEXT,
    fecha_generado      DATETIME DEFAULT CURRENT_TIMESTAMP,

    congelado           INTEGER NOT NULL DEFAULT 0 CHECK(congelado IN (0, 1)),

    notas               TEXT,

    UNIQUE(pj_principal_id, pj_companion_1_id, pj_companion_2_id, contenido_optimo)
);

CREATE INDEX IF NOT EXISTS idx_team_comp_principal
    ON team_compositions(pj_principal_id, contenido_optimo, rank_para_principal);

CREATE INDEX IF NOT EXISTS idx_team_comp_score
    ON team_compositions(pj_principal_id, score_composicion DESC);

-- -----------------------------------------------------------------------------
-- 3. ai_catalog_runs — auditoría de uso de Claude API
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ai_catalog_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operacion       TEXT NOT NULL
                    CHECK(operacion IN (
                        'team_synergy_pair',
                        'team_composition_topN',
                        'weapon_passive_modeling',
                        'pj_weapon_synergy_seed',
                        'recatalog_on_demand',
                        'recatalog_auto_new_pj',
                        'recatalog_auto_new_set'
                    )),
    modelo          TEXT NOT NULL,                    -- 'claude-sonnet-4-6' | 'claude-opus-4-6'

    -- Input identification
    pj_ids          TEXT,                             -- JSON array [N, N, ...]
    weapon_ids      TEXT,                             -- JSON array
    prompt_hash     TEXT,                             -- sha256(prompt) para cache hit detection

    -- Tokens
    tokens_input            INTEGER,
    tokens_input_cached     INTEGER DEFAULT 0,        -- prompt caching hits
    tokens_output           INTEGER,

    costo_usd       REAL,                             -- estimado tras la llamada
    duracion_ms     INTEGER,

    exito           INTEGER NOT NULL CHECK(exito IN (0, 1)),
    error_msg       TEXT,

    -- Response opcional (puede pesar; activable por flag de debug)
    response_json   TEXT,

    fecha           DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_runs_fecha
    ON ai_catalog_runs(fecha DESC);

CREATE INDEX IF NOT EXISTS idx_ai_runs_op_modelo
    ON ai_catalog_runs(operacion, modelo, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_ai_runs_costo_mes
    ON ai_catalog_runs(fecha, costo_usd) WHERE exito = 1;

COMMIT;

-- =============================================================================
-- Migración: arquetipos + scoring + histórico de evaluaciones
-- Fecha: 2026-04-24
-- Autor: Daniel (danibod)
-- Refs: Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md §11.2
--
-- Crea 5 tablas nuevas:
--   1. disc_archetypes             — catálogo de 6 arquetipos de build
--   2. disc_set_archetype          — relación N:M set ↔ arquetipo
--   3. agent_substat_preferences   — overrides de pesos por PJ (vacío al inicio)
--   4. agent_score_thresholds      — cortes de score por PJ (seed default)
--   5. inventory_disc_evaluations  — histórico de recomendaciones
--
-- Seed inicial:
--   - 6 arquetipos con substats positivos/perjudiciales y pesos.
--   - 26 sets clasificados (primario y secundario donde aplica).
--   - 45 PJs con thresholds default 0.75 equip / 0.50 upgrade.
--
-- Idempotente: todas las sentencias usan CREATE TABLE IF NOT EXISTS y
-- INSERT OR IGNORE. Puede re-aplicarse sin duplicar.
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- 1. disc_archetypes
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS disc_archetypes (
    id                     INTEGER PRIMARY KEY,
    code                   TEXT UNIQUE NOT NULL,
    nombre                 TEXT NOT NULL,
    descripcion            TEXT,
    mains_4                TEXT,  -- JSON array
    mains_5                TEXT,
    mains_6                TEXT,
    substats_positivos     TEXT,  -- JSON objeto: {"stat": peso, ...}
    substats_perjudiciales TEXT,  -- JSON objeto: {"stat": -peso, ...}
    threshold_stock        REAL NOT NULL DEFAULT 0.7
);

-- Seed de los 6 arquetipos.
INSERT OR IGNORE INTO disc_archetypes (id, code, nombre, descripcion, mains_4, mains_5, mains_6, substats_positivos, substats_perjudiciales, threshold_stock) VALUES
(1, 'ATK_DPS',     'Atacante ATK-scaler',   'Atacantes directos que escalan con ATK y crits.',
    '["Prob. Crítica","Daño Crítico","ATK%"]',
    '["Bono Daño","ATK%"]',
    '["Daño Crítico","ATK%"]',
    '{"Prob. Crítica":1.0,"Daño Crítico":1.0,"ATK%":1.0,"ATK":0.4,"Perforación":0.7}',
    '{"DEF":-0.8,"DEF%":-1.0,"HP":-0.5,"HP%":-0.8,"Maestría de Anomalía":-0.8}',
    0.70),
(2, 'HP_DISRUPT',  'Disruptivo HP-scaler',  'Atacantes cuyo daño escala con HP. Ignoran defensa por kit.',
    '["Prob. Crítica","Daño Crítico","HP%"]',
    '["Bono Daño","HP%"]',
    '["Daño Crítico","HP%"]',
    '{"Prob. Crítica":1.0,"Daño Crítico":1.0,"HP%":1.0,"HP":0.4}',
    '{"DEF":-0.8,"DEF%":-1.0,"Maestría de Anomalía":-0.8,"Perforación":-0.5}',
    0.70),
(3, 'ANOMALY',     'Anomaly DPS',           'DPS por reacciones anomalía; Maestría y ATK como escalado.',
    '["Maestría de Anomalía","ATK%"]',
    '["Bono Daño","ATK%"]',
    '["Maestría de Anomalía","ATK%"]',
    '{"Maestría de Anomalía":1.0,"ATK%":1.0,"ATK":0.4,"Perforación":0.6}',
    '{"DEF":-0.8,"DEF%":-1.0,"HP":-0.5,"HP%":-0.8,"Daño Crítico":-0.6}',
    0.70),
(4, 'STUN',        'Aturdidor',             'Stunner: builda Impacto como main slot 6, ataca con Crit/ATK.',
    '["Prob. Crítica","Daño Crítico","ATK%"]',
    '["ATK%"]',
    '["Impacto"]',
    '{"ATK%":1.0,"ATK":0.4,"Prob. Crítica":0.8,"Daño Crítico":0.8,"Perforación":0.6}',
    '{"DEF":-0.8,"DEF%":-1.0,"HP":-0.5,"HP%":-0.8,"Maestría de Anomalía":-0.8}',
    0.70),
(5, 'SUPPORT_ER',  'Soporte de energía',    'Generador de Recarga; puede aportar daño secundario.',
    '["ATK%","Prob. Crítica"]',
    '["ATK%","Bono Daño"]',
    '["Recarga de Energía"]',
    '{"ATK%":0.7,"HP%":0.7,"Prob. Crítica":0.6,"Daño Crítico":0.6,"Perforación":0.4}',
    '{"DEF":-0.5,"DEF%":-0.6,"Maestría de Anomalía":-0.7}',
    0.65),
(6, 'DEFENSE',     'Defensor / Tank',       'Escalado en HP/DEF; builds con Impacto slot 6 para subaturdir.',
    '["DEF%","HP%"]',
    '["DEF%","HP%"]',
    '["Impacto","DEF%","HP%"]',
    '{"DEF%":1.0,"DEF":0.4,"HP%":1.0,"HP":0.4}',
    '{"ATK":-0.6,"ATK%":-0.8,"Perforación":-0.6,"Maestría de Anomalía":-0.8}',
    0.65);

-- -----------------------------------------------------------------------------
-- 2. disc_set_archetype
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS disc_set_archetype (
    set_id       INTEGER NOT NULL REFERENCES disc_sets(id),
    archetype_id INTEGER NOT NULL REFERENCES disc_archetypes(id),
    prioridad    INTEGER NOT NULL DEFAULT 1,  -- 1 = primario, 2 = secundario
    PRIMARY KEY (set_id, archetype_id)
);

CREATE INDEX IF NOT EXISTS idx_dse_arch ON disc_set_archetype(archetype_id, prioridad);

-- Clasificación de los 26 sets existentes.
-- Primario = uso principal; secundario = uso válido pero no ideal.
INSERT OR IGNORE INTO disc_set_archetype (set_id, archetype_id, prioridad) VALUES
(24, 5, 1), (24, 1, 2),   -- Voz Astral       → SUPPORT_ER (1), ATK_DPS (2)
(25, 3, 1), (25, 1, 2),   -- Balada rama/esp  → ANOMALY (1), ATK_DPS (2)
(26, 6, 1),               -- Conejo maravill  → DEFENSE
(27, 3, 1),               -- Jazz Caótico     → ANOMALY
(28, 1, 1), (28, 3, 2),   -- Metal Caótico    → ATK_DPS (1), ANOMALY (2)
(29, 1, 1),               -- Floración alba   → ATK_DPS
(30, 1, 1), (30, 3, 2),   -- Metal Colmilludo → ATK_DPS (1), ANOMALY (2)
(31, 3, 1),               -- Blues Libre      → ANOMALY
(32, 1, 1),               -- Punk Hormonal    → ATK_DPS
(33, 1, 1),               -- Metal Infernal   → ATK_DPS
(34, 4, 1),               -- Monarca Pináculo → STUN
(35, 5, 1),               -- Nana luz ceniza  → SUPPORT_ER
(36, 1, 1), (36, 3, 2),   -- Notas encadenas  → ATK_DPS (1), ANOMALY (2)
(37, 5, 1), (37, 3, 2),   -- Melodía Faetón   → SUPPORT_ER (1), ANOMALY (2)
(38, 1, 1),               -- Polar Metal      → ATK_DPS
(39, 6, 1),               -- Punk Primitivo   → DEFENSE
(40, 1, 1), (40, 5, 2),   -- Puffer Electro   → ATK_DPS (1), SUPPORT_ER (2)
(41, 1, 1),               -- Armonía umbría   → ATK_DPS
(42, 1, 1), (42, 4, 2),   -- Aria brillante   → ATK_DPS (1), STUN (2)
(43, 4, 1),               -- Disco Sacudeestr → STUN
(44, 6, 1),               -- Soul Rock        → DEFENSE
(45, 5, 1),               -- Jazz Oscilante   → SUPPORT_ER
(46, 1, 1),               -- Metal Eléctrico  → ATK_DPS
(48, 1, 1),               -- Tecno Pícido     → ATK_DPS
(49, 2, 1),               -- Fábula Yunkui    → HP_DISRUPT
(51, 1, 1);               -- Balada aguas bl  → ATK_DPS

-- -----------------------------------------------------------------------------
-- 3. agent_substat_preferences
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_substat_preferences (
    agente_id INTEGER NOT NULL REFERENCES agents(id),
    substat   TEXT NOT NULL,
    peso      REAL NOT NULL DEFAULT 0.0,     -- -1.0 (perjudicial fuerte) a +1.0 (ideal)
    fuente    TEXT DEFAULT 'prydwen',        -- 'prydwen' | 'daniel' | 'default_archetype'
    PRIMARY KEY (agente_id, substat)
);

CREATE INDEX IF NOT EXISTS idx_asp_agente ON agent_substat_preferences(agente_id);

-- Sin seed: la tabla queda vacía al inicio. El scoring cae por defecto al arquetipo
-- primario asociado al rol del PJ hasta que Daniel cargue preferencias desde Prydwen.

-- -----------------------------------------------------------------------------
-- 4. agent_score_thresholds
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_score_thresholds (
    agente_id         INTEGER PRIMARY KEY REFERENCES agents(id),
    threshold_equip   REAL NOT NULL DEFAULT 0.75,
    threshold_upgrade REAL NOT NULL DEFAULT 0.50,
    fuente            TEXT DEFAULT 'default',    -- 'default' | 'daniel'
    actualizado       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed de todos los PJs con defaults. Daniel ajusta DPS core después.
INSERT OR IGNORE INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents;

-- -----------------------------------------------------------------------------
-- 5. inventory_disc_evaluations
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS inventory_disc_evaluations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_disc_id INTEGER NOT NULL REFERENCES inventory_discs(id),
    fecha             DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger_evento    TEXT NOT NULL,   -- 'captura_inicial' | 're_eval_threshold' | 're_eval_upgrade' | 're_eval_manual'
    recomendacion     TEXT,            -- 'equipar_pj_X' | 'mejorar_pj_Y' | 'reserva_arq_Z' | 'descartar'
    score             REAL,
    detalle_json      TEXT             -- desglose: set_match, main_match, subs_positivos, subs_perjudiciales, arquetipo, pj_top
);

CREATE INDEX IF NOT EXISTS idx_ide_disc ON inventory_disc_evaluations(inventory_disc_id, fecha DESC);

-- -----------------------------------------------------------------------------
-- 6. Índices complementarios sobre tablas existentes (idempotentes)
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_inv_set_slot       ON inventory_discs(set_id, slot);
CREATE INDEX IF NOT EXISTS idx_inv_agente         ON inventory_discs(agente_asignado);
CREATE INDEX IF NOT EXISTS idx_agent_discs_lookup ON agent_discs(set_id, slot, main_stat);

COMMIT;

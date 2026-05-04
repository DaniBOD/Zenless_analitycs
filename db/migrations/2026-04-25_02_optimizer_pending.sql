-- =============================================================================
-- Migración: optimizer_pending_actions (RF-06)
-- Fecha: 2026-04-25
-- Autor: Daniel (danibod)
-- Refs: Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md
--
-- Crea 1 tabla nueva:
--   1. optimizer_pending_actions — top-3 builds calculadas por RF-06
--      mantenidas como "TODO" hasta que RF-04 confirme su aplicación in-game.
--
-- Sin seed: la tabla queda vacía hasta el primer cálculo del optimizador.
--
-- Idempotente: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- 1. optimizer_pending_actions
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS optimizer_pending_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agente_id       INTEGER NOT NULL REFERENCES agents(id),
    rank            INTEGER NOT NULL CHECK(rank BETWEEN 1 AND 3),
    score_estimado  REAL NOT NULL,                   -- score conjunto de la build
    score_actual    REAL,                            -- score de la build actual del PJ
    delta           REAL,                            -- score_estimado - score_actual

    -- Build propuesta. JSON: {"slot_1": disc_id, ..., "slot_6": disc_id,
    --                          "set_4p": set_id, "set_2p": set_id}
    build_json      TEXT NOT NULL,
    set_bonus       TEXT,                            -- '4p_X' | '2+2+2_X+Y+Z' | '3+3_X+Y'

    -- Discos que vienen de OTROS PJs (cadena de swap longitud 1 en v1).
    -- JSON array: [{"disc_id":N, "agente_origen":N, "delta_origen":-N.NN}, ...]
    requiere_swaps  TEXT,

    estado          TEXT NOT NULL DEFAULT 'TODO'
                    CHECK(estado IN ('TODO', 'APLICADO', 'DESCARTADO', 'OBSOLETO')),

    -- Origen del cálculo
    fuente_trigger  TEXT NOT NULL DEFAULT 'manual'
                    CHECK(fuente_trigger IN ('manual', 'auto_post_captura', 'recalc_inventario')),

    fecha_calculado DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_aplicado  DATETIME,                        -- NULL hasta que el usuario aplique
    fecha_obsoleto  DATETIME,                        -- cuando otro recálculo lo invalida

    notas           TEXT
);

CREATE INDEX IF NOT EXISTS idx_opt_pending_agente_rank
    ON optimizer_pending_actions(agente_id, rank, estado);

CREATE INDEX IF NOT EXISTS idx_opt_pending_estado
    ON optimizer_pending_actions(estado, fecha_calculado DESC);

CREATE INDEX IF NOT EXISTS idx_opt_pending_score
    ON optimizer_pending_actions(agente_id, score_estimado DESC);

COMMIT;

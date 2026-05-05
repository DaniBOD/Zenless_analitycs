-- =============================================================================
-- Migración 09 — Agregar protected_build a agents
-- Hito 2.6: el optimizador respeta builds "sagradas" por PJ (RF-06 §4.3).
-- Nota: optimizer_pending_actions ya existe en schema base (migración 01).
-- =============================================================================

BEGIN TRANSACTION;

ALTER TABLE agents ADD COLUMN protected_build INTEGER NOT NULL DEFAULT 0
    CHECK(protected_build IN (0, 1));

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Verificación
SELECT COUNT(*) AS total_agents,
       SUM(protected_build) AS protected_count
  FROM agents;

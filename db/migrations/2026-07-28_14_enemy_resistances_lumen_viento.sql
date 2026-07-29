-- =============================================================================
-- Patch v3.1 · Migración 14 — enemy_resistances admite 'viento' y 'lumen'
-- Fecha: 2026-07-28
-- =============================================================================
-- MOTIVO
--   `enemy_resistances.elemento` tiene un CHECK cerrado que quedó desactualizado:
--
--       CHECK(elemento IN ('fisico','fuego','hielo','electrico','eter','frost'))
--
--   Le faltan DOS elementos:
--     1. 'viento' — atraso preexistente. Viento es estándar desde v3.0 y Velina
--        (agents.id=48) está en el roster desde 2026-06-19. El parser ya lo
--        conoce (app/core/parser_agent_stats.py::_ELEMENTOS_DB) pero el CHECK
--        nunca se actualizó → hoy es imposible cargar la resistencia a Viento
--        de un enemigo.
--     2. 'lumen'  — atributo de daño NUEVO del patch v3.1 (2026-07-28).
--
--   En SQLite un CHECK no se puede alterar: hay que reconstruir la tabla
--   (crear nueva → copiar → drop → rename → recrear índices).
--
-- ALCANCE — esto es SOLO schema.
--   NO inserta filas de resistencia para viento/lumen. Los multiplicadores por
--   enemigo son datos que hay que observar/scrapear (Hakush.in) y por RNF-02 no
--   se inventan. La tabla queda con las mismas 72 filas (12 enemigos × 6
--   elementos viejos); las nuevas entran cuando haya datos reales.
--
-- CONVENCIÓN DE FORMA (no unificar con `agents`).
--   Esta columna usa minúscula sin tilde ('fisico', 'electrico'); `agents.elemento`
--   usa capitalizado con tilde ('Físico', 'Eléctrico'). Son vocabularios de
--   consumidores distintos y se mantienen separados a propósito.
--   'frost' se conserva: Miyabi/Escarcha se modela aparte acá aunque el parser
--   de agentes lo colapse a Hielo.
--
-- ⚠️ Antes de ejecutar: BACKUP de db/danibod_zzz_v2.db (RNF-01). App cerrada.
--   Runner: python app/scripts/qa/apply_migration.py <este archivo>
--   (el runner desactiva foreign_keys durante el rebuild y los reactiva después).
-- =============================================================================

BEGIN TRANSACTION;

-- 1. Tabla nueva: idéntica salvo el CHECK ampliado.
CREATE TABLE enemy_resistances_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    enemy_id            INTEGER NOT NULL REFERENCES enemies(id) ON DELETE CASCADE,
    elemento            TEXT NOT NULL
                        CHECK(elemento IN ('fisico', 'fuego', 'hielo', 'electrico',
                                           'eter', 'frost', 'viento', 'lumen')),

    -- 1.0 = neutral; <1.0 = resistente; >1.0 = débil; 0 = inmune
    multiplicador       REAL NOT NULL DEFAULT 1.0,
    breakdown_status    TEXT
                        CHECK(breakdown_status IS NULL OR
                              breakdown_status IN ('weak', 'neutral', 'resistant', 'immune')),
    notas               TEXT,

    UNIQUE(enemy_id, elemento)
);

-- 2. Copiar las filas existentes preservando los id (para no romper referencias
--    externas ni el contador AUTOINCREMENT).
INSERT INTO enemy_resistances_new (id, enemy_id, elemento, multiplicador, breakdown_status, notas)
SELECT id, enemy_id, elemento, multiplicador, breakdown_status, notas
  FROM enemy_resistances;

-- 3. Swap.
DROP TABLE enemy_resistances;
ALTER TABLE enemy_resistances_new RENAME TO enemy_resistances;

-- 4. Recrear los índices (el DROP se los llevó).
CREATE INDEX idx_enemy_res_enemy ON enemy_resistances(enemy_id);
CREATE INDEX idx_enemy_res_elem  ON enemy_resistances(elemento, multiplicador);

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada SELECT devuelve una columna `expected_N` que DEBE valer N.
SELECT 'filas preservadas'            AS check_name, COUNT(*) AS expected_72 FROM enemy_resistances;
SELECT 'elementos distintos (viejos)' AS check_name, COUNT(DISTINCT elemento) AS expected_6 FROM enemy_resistances;
SELECT 'enemigos con resistencias'    AS check_name, COUNT(DISTINCT enemy_id) AS expected_12 FROM enemy_resistances;
SELECT 'indices recreados'            AS check_name, COUNT(*) AS expected_2
  FROM sqlite_master WHERE type='index' AND tbl_name='enemy_resistances' AND name LIKE 'idx_%';
SELECT 'CHECK admite viento+lumen'    AS check_name, COUNT(*) AS expected_1
  FROM sqlite_master WHERE name='enemy_resistances'
   AND sql LIKE '%viento%' AND sql LIKE '%lumen%';
SELECT 'id max preservado'            AS check_name, MAX(id) AS expected_72 FROM enemy_resistances;

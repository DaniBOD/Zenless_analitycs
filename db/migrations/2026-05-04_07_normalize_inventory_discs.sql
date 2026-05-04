-- =============================================================================
-- Migración 07 — Normalizar inventory_discs
-- Aplica: columnas unidad1-4 + unidad_main para distinguir % vs flat
--         índices recomendados RF-04 §11.3
-- Ejecutar DESPUÉS de restandarize_inventory_discs.py (Hito 2.0.4)
-- =============================================================================

BEGIN TRANSACTION;

-- Columnas de unidad (distinguen % vs flat)
ALTER TABLE inventory_discs ADD COLUMN unidad_main TEXT CHECK(unidad_main IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad1 TEXT CHECK(unidad1 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad2 TEXT CHECK(unidad2 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad3 TEXT CHECK(unidad3 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad4 TEXT CHECK(unidad4 IN ('flat','%'));

-- Índices RF-04 §11.3
CREATE INDEX IF NOT EXISTS idx_inv_set_slot       ON inventory_discs(set_id, slot);
CREATE INDEX IF NOT EXISTS idx_inv_agente         ON inventory_discs(agente_asignado);
CREATE INDEX IF NOT EXISTS idx_inv_pending        ON inventory_discs(descartado, equipado) WHERE descartado = 0;
CREATE INDEX IF NOT EXISTS idx_inv_score          ON inventory_discs(score_evaluacion);

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT 'columnas_unidad' AS check_name,
       COUNT(*) AS total_cols
  FROM pragma_table_info('inventory_discs')
 WHERE name LIKE 'unidad%';

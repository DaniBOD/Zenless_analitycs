-- =====================================================================
-- 2026-06-03 · Migración 09 — Corrección "Tasa de Anomalía" vs "Maestría de Anomalía"
-- =====================================================================
-- Hallazgo (QA S17, 2026-06-02): "Tasa de Anomalía" (Anomaly Mastery %) y
-- "Maestría de Anomalía" (Anomaly Mastery flat / Anomaly Proficiency) son DOS
-- stats DISTINTAS. El modelo viejo (audit Hito 2.0.1 + stats_vocab) las conflaba,
-- tratando "Tasa de Anomalía" como error de OCR de "Maestría", y reescribió los
-- discos slot-6 a "Maestría de Anomalía".
--
-- Evidencia (RNF-02):
--   - Captura real Ejemplo_8: slot 6 main = "Tasa de Anomalía 30 %".
--   - Captura real Ejemplo_9: slot 4 main = "Maestría de Anomalía 92" (flat).
--   - DB: los 11 discos slot-6 "Maestría de Anomalía" tienen main_valor = 30
--     (una Maestría flat sería ~92, no 30) → son Tasa de Anomalía 30 %.
--
-- Corrección: revertir esos 11 a "Tasa de Anomalía" con unidad "%". Los discos
-- slot-4 "Maestría de Anomalía" (valor 92/23 flat) y las substats Maestría
-- (flat) quedan INTACTOS — son legítimos.
--
-- RNF-01: backup previo + transacción + PRAGMA checks (ver script de aplicación).
-- =====================================================================

BEGIN TRANSACTION;

UPDATE inventory_discs
SET main_stat   = 'Tasa de Anomalía',
    unidad_main = '%'
WHERE slot = 6
  AND main_stat LIKE 'Maestr%a de Anomal%a'
  AND main_valor = 30.0;

COMMIT;

-- Smoke checks (deben mostrar el valor esperado):
SELECT 'expected_11' AS check_name,
       COUNT(*)      AS tasa_slot6
FROM inventory_discs
WHERE slot = 6 AND main_stat = 'Tasa de Anomalía';

SELECT 'expected_0' AS check_name,
       COUNT(*)     AS maestria_slot6_restante
FROM inventory_discs
WHERE slot = 6 AND main_stat LIKE 'Maestr%a de Anomal%a';

SELECT 'expected_14' AS check_name,
       COUNT(*)      AS maestria_slot4_intacta
FROM inventory_discs
WHERE slot = 4 AND main_stat LIKE 'Maestr%a de Anomal%a';

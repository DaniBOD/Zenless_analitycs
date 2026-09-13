-- =============================================================================
-- 2026-09-12_32 · disc_archetypes: el main de anomalía de slot 6 es "Tasa de
--                 Anomalía", y los arquetipos elementales admiten Viento
-- =============================================================================
-- Cierra el pendiente que dejó escrito la migración 09 (2026-06-03,
-- audit/correccion_tasa_anomalia_20260603.md §4): esa migración separó
-- "Maestría de Anomalía" (flat, main de slot 4 + substat) de "Tasa de Anomalía"
-- (%, main de slot 6) en los discos y en stats_vocab, pero NO en los arquetipos.
--
-- ## Evidencia (Dev_IA/.../2026-09-12_DIAG_El_filtro_de_mains_excluye_el_30_por_ciento_de_lo_equipado.md)
--
-- Tres fuentes concordantes para slot 6 = Tasa de Anomalía:
--   - app/core/stats_vocab.py  CANONICAL_MAINS_VARIABLE[6]
--   - RF-04 §7.2.1 (corrección de la mig 09)
--   - inventory_discs: slot 6 → 30 % (13 discos); slot 4 → 92 flat (14 discos)
--
-- ANOMALY.mains_6 = ["Maestría de Anomalía","ATK%"] era letra muerta: ningún
-- disco la cumple, así que el optimizador solo admitía ATK% en slot 6 para los
-- 11 PJs de anomalía, y el scoring les negaba el bono de main (+1.0) al disco
-- correcto. Medido en memoria: 10/11 cambian de slot 6 y el score actual de los
-- 8 que ya lo llevan sube exactamente +1.0.
--
-- Viento: "Bono Daño Viento" está en stats_vocab (entró con Velina) y ningún
-- arquetipo lo admitía, aunque los cinco que listan bonos elementales listaban
-- los otros cinco. DEFENSE no lista ninguno y no se toca. "Bono Daño Lumen" NO se
-- agrega: ese main no existe (contrato en test_stats_vocab.py).
--
-- Contrato nuevo: app/tests/unit/test_disc_archetypes_contrato.py.
-- Solo corrige vocabulario: qué mains le sirven a cada arquetipo (Miyabi con
-- Daño Crítico, ER en atacantes, etc.) es otra decisión, no tomada acá.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE disc_archetypes
   SET mains_6 = REPLACE(mains_6, '"Maestría de Anomalía"', '"Tasa de Anomalía"')
 WHERE code = 'ANOMALY'
   AND mains_6 LIKE '%"Maestría de Anomalía"%';

UPDATE disc_archetypes
   SET mains_5 = REPLACE(mains_5, '"Bono Daño Éter"', '"Bono Daño Éter","Bono Daño Viento"')
 WHERE mains_5 LIKE '%"Bono Daño Éter"%'
   AND mains_5 NOT LIKE '%"Bono Daño Viento"%';

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_6 FROM disc_archetypes;
SELECT COUNT(*) AS expected_6 FROM disc_archetypes
 WHERE json_valid(mains_4) AND json_valid(mains_5) AND json_valid(mains_6);
-- ANOMALY slot 6: exactamente Tasa + ATK%, en ese orden.
SELECT COUNT(*) AS expected_1 FROM disc_archetypes
 WHERE code = 'ANOMALY' AND mains_6 = '["Tasa de Anomalía","ATK%"]';
-- Ningún arquetipo pide ya el main flat en slot 6.
SELECT COUNT(*) AS expected_0 FROM disc_archetypes WHERE mains_6 LIKE '%Maestría de Anomalía%';
-- Slot 4 de ANOMALY conserva la Maestría (esa SÍ es de slot 4).
SELECT COUNT(*) AS expected_1 FROM disc_archetypes
 WHERE code = 'ANOMALY' AND mains_4 = '["Maestría de Anomalía","ATK%"]';
-- Viento en los cinco elementales, una sola vez cada uno; DEFENSE sin bonos.
SELECT COUNT(*) AS expected_5 FROM disc_archetypes WHERE mains_5 LIKE '%"Bono Daño Viento"%';
SELECT COUNT(*) AS expected_0 FROM disc_archetypes
 WHERE mains_5 LIKE '%"Bono Daño Viento"%"Bono Daño Viento"%';
SELECT COUNT(*) AS expected_1 FROM disc_archetypes
 WHERE code = 'DEFENSE' AND mains_5 = '["DEF%","HP%"]';
SELECT COUNT(*) AS expected_0 FROM disc_archetypes WHERE mains_5 LIKE '%Lumen%';
PRAGMA foreign_key_check;
PRAGMA integrity_check;

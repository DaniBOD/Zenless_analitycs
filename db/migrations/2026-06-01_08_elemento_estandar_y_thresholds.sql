-- =====================================================================
-- 2026-06-01_08_elemento_estandar_y_thresholds.sql
-- ---------------------------------------------------------------------
-- Decisiones de DaniBOD sobre la mig 07 (2026-06-01):
--
-- (A) POLÍTICA DE ELEMENTOS: los atributos "especiales" del juego se guardan
--     como su EQUIVALENTE ESTÁNDAR (a fin de cuentas heredan modificadores del
--     estándar). Por eso se REVIERTE la decisión de mig 07 de guardar Yixuan
--     como "Tinta áurica":
--       - Yixuan: Tinta áurica (Auric Ink) -> Éter            [revertido aquí]
--       - Ye Shunguang: Honed Edge -> Físico                  [ya quedó Físico en mig 07]
--       - Miyabi: Frost/Escarcha -> Hielo                     [ya estaba Hielo]
--     El atributo VIENTO (Wind), que SÍ es un elemento estándar nuevo (no
--     equivalente a otro), se incorpora al dominio del proyecto de forma
--     proactiva (parser `_ELEMENTOS_DB`, modelo relacional, project-context),
--     aunque todavía no haya agentes Viento en el roster.
--
-- (B) NANGONG YU (id 26): confirmado 100% Stunner con subrol oculto sub-anómalo.
--     rol='Aturdimiento' (correcto, sin cambio). Su synergy/thresholds
--     anomaly-flavored (maestria_anomalia 280/360) son INTENCIONALES — su Daze
--     escala con Maestría de Anomalía. NO se normaliza la matriz (forzar
--     anomaly_proficiency 0.2 degradaría el scoring de sus armas de AM).
--
-- (C) THRESHOLDS re-derivados contra Prydwen/Game8 (RNF-02) para los 3 agentes
--     cuyo rol cambió en mig 07 hacia un perfil de stats distinto:
--       - Ju Fufu (29, Fire Stun híbrido): "CRIT Rate hasta 50% > ATK hasta 3400".
--       - Dialyn  (27, Physical Stun):     "+CRIT Rate; Energy Regen efecto
--                                            desmesurado en velocidad de stun".
--       - Yuzuha  (24, Physical Support):  "≥3000 ATK y 200 Anomaly Mastery".
--     (Pulchra/Lucía/Ye Shunguang ya tenían thresholds acordes a su rol real.)
-- =====================================================================

BEGIN TRANSACTION;

-- (A) Yixuan: elemento estándar -----------------------------------------
UPDATE agents SET elemento = 'Éter' WHERE id = 31;   -- Auric Ink ≡ Éter

-- (C) Re-derivación de thresholds (RNF-02, fuente Prydwen/Game8) ---------
-- Ju Fufu (29): CRIT Rate target 50% (no 60-70). ATK y ER se mantienen.
UPDATE agent_thresholds
   SET valor_minimo = 50.0, valor_optimo = 60.0,
       descripcion = 'CRIT Rate ≥50% para 4P King of the Summit',
       fuente = 'Prydwen/Game8 rederivado 2026-06-01'
 WHERE agente_id = 29 AND stat = 'prob_critico';

-- Dialyn (27): añadir Recuperación de Energía (clave para velocidad de stun).
INSERT INTO agent_thresholds (agente_id, stat, valor_minimo, valor_optimo, valor_maximo, descripcion, fuente)
  VALUES (27, 'rec_energia', 1.5, 2.0, NULL,
          'ER acelera EX Special -> mayor frecuencia de Daze',
          'Prydwen/Game8 rederivado 2026-06-01');

-- Yuzuha (24): targets de buff -> ATK ≥3000 y Maestría de Anomalía ~200.
UPDATE agent_thresholds
   SET valor_minimo = 3000.0, valor_optimo = 3200.0,
       descripcion = 'ATK ≥3000 para maximizar buffs (Additional Ability)',
       fuente = 'Prydwen/Game8 rederivado 2026-06-01'
 WHERE agente_id = 24 AND stat = 'ataque';
UPDATE agent_thresholds
   SET valor_minimo = 180.0, valor_optimo = 220.0,
       descripcion = 'Maestría de Anomalía ~200 para tope de buffs',
       fuente = 'Prydwen/Game8 rederivado 2026-06-01'
 WHERE agente_id = 24 AND stat = 'maestria_anomalia';
UPDATE agent_thresholds
   SET valor_optimo = 2.2,
       fuente = 'Prydwen/Game8 rederivado 2026-06-01'
 WHERE agente_id = 24 AND stat = 'rec_energia';

COMMIT;

-- =====================================================================
-- SMOKE CHECKS (cada SELECT debe devolver expected_N = N)
-- =====================================================================
-- Yixuan vuelve a Éter; ya no quedan agentes con 'Tinta áurica'
SELECT COUNT(*) AS expected_1 FROM agents WHERE id=31 AND elemento='Éter';
SELECT COUNT(*) AS expected_0 FROM agents WHERE elemento='Tinta áurica';
-- Ju Fufu prob_critico = 50/60
SELECT COUNT(*) AS expected_1 FROM agent_thresholds
 WHERE agente_id=29 AND stat='prob_critico' AND valor_minimo=50.0 AND valor_optimo=60.0;
-- Dialyn ahora tiene 3 thresholds (incluye rec_energia)
SELECT COUNT(*) AS expected_3 FROM agent_thresholds WHERE agente_id=27;
-- Yuzuha ataque 3000/3200 + maestria 180/220
SELECT COUNT(*) AS expected_1 FROM agent_thresholds
 WHERE agente_id=24 AND stat='ataque' AND valor_minimo=3000.0 AND valor_optimo=3200.0;
SELECT COUNT(*) AS expected_1 FROM agent_thresholds
 WHERE agente_id=24 AND stat='maestria_anomalia' AND valor_minimo=180.0 AND valor_optimo=220.0;

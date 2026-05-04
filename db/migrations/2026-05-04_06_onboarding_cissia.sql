-- =============================================================================
-- Onboarding Cissia · 2026-05-04
-- =============================================================================
-- Aplica:
--   1. INSERT en agents (Cissia · S · Eléctrico · Ataque · M0 · CRIT · v2.7)
--   2. INSERT en agent_thresholds (5 thresholds — Ataque crit-DPS)
--   3. INSERT en agent_score_thresholds (defaults 0.75 / 0.50)
--   4. INSERT en agent_awakenings (placeholder — Cissia no tiene awakening en v2.7)
--   5. INSERT en pj_weapon_synergy (6 filas — BONUS_MATRIX rol Ataque · Onboarding §6)
--   6. UPDATE 4 discos existentes (slots 1, 2, 3, 5 — sueltos en DB) → asignar a Cissia
--   7. INSERT 2 discos nuevos (slots 4 y 6 — capturados esta sesión)
--   8. PRAGMA integrity_check + foreign_key_check + smoke checks
--
-- ⚠️ Antes de ejecutar:
--   1. BACKUP: cp db/danibod_zzz_v2.db db/danibod_zzz_v2.backup_premig_20260504_HHMMSS.db
--   2. Validar que la DB no fue modificada desde 2026-05-03 19:30 (última inspección).
--
-- Convención de val* en inventory_discs:
--   La columna sigue mixta TEXT/REAL hasta que aplique la migración 06 (Fase 2.0.3).
--   Aquí mantengo la convención actual: % como TEXT con sufijo, flat como REAL.
--   La migración 06 + script de re-estandarización (Fase 2.0.4) absorbe estos discos
--   junto con los 332 existentes. NO afecta el onboarding.
-- =============================================================================

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- 1. INSERT en agents
--    Stats efectivos extraídos de Pj_stats/Cissia.jpeg (HoYoLAB, RNF-02 verified).
--    Datos confirmados por usuario 2026-05-04:
--      mindscape = 0
--      rol       = 'Ataque'
--      faccion   = CRIT (misma que Seth/Qingyi/Zhu Yuan/Jane)
--      patch    = v2.7
--      awakening = no tiene (placeholder activo=0)
--      variante visual: Metropolitan Order Division (logo propio, caso Jane Doe)
-- ---------------------------------------------------------------------------
INSERT INTO agents (
    nombre, rango, nivel, mindscape, elemento, rol, faccion,
    pv, ataque, defensa, impacto,
    prob_critico, dano_critico,
    tasa_anomalia, maestria_anomalia,
    tasa_perforacion, perforacion,
    rec_energia, bono_dano_elemento,
    weapon_id, weapon_nivel, weapon_rango,
    set_4p_id, set_2p_id, disco6_main, notas
) VALUES (
    'Cissia',
    'S',
    60,
    0,                                                -- mindscape M0 (sin nodos desbloqueados)
    'Eléctrico',
    'Ataque',                                         -- rol oficial
    'Criminal Investigation Special Response Team',   -- facción paraguas (CRIT/N.E.P.S.)
    -- Stats efectivos (con W-Engine Drill Rig R5 + 6 discos lvl 15 equipados):
    10788,            -- pv
    2178,             -- ataque
    849,              -- defensa
    93,               -- impacto
    48.2,             -- prob_critico
    126.8,            -- dano_critico
    94,               -- tasa_anomalia
    147,              -- maestria_anomalia
    0.0,              -- tasa_perforacion
    36,               -- perforacion
    3.58,             -- rec_energia
    30.0,             -- bono_dano_elemento (Bono Eléctrico)
    -- W-Engine equipada
    41,               -- weapon_id (Taladradora giratoria - Eje, A-rank)
    60,               -- weapon_nivel
    5,                -- weapon_rango (refinamiento R5/P5)
    -- Build de discos
    29,               -- set_4p_id (Floración del alba)
    35,               -- set_2p_id (Nana a la luz cenicienta)
    'Recuperación de Energía',  -- disco6_main
    'Patch v2.7. Variante visual: Metropolitan Order Division (División del Orden Metropolitano) — sub-facción dentro de CRIT/N.E.P.S., logo propio en Faccion_Logos/Faction_Metropolitan_Order_Division_Icon.webp. Caso análogo a Jane Doe. Skill levels: 12/9/10/12/12/7. Sin awakening (no desbloqueado en v2.7).'
);

-- ---------------------------------------------------------------------------
-- 2. agent_thresholds (5 stats — perfil Crit-DPS Eléctrico)
--    Calibrados para rol Ataque con W-Engine Drill Rig R5.
--    El build actual (Crit 48.2 / CDmg 126.8 / ER 3.58) está cerca del óptimo
--    pero CR está debajo del mínimo recomendado — la app debería sugerir mejorarlo.
-- ---------------------------------------------------------------------------
INSERT INTO agent_thresholds (agente_id, stat, valor_minimo, valor_optimo, valor_maximo, descripcion, fuente)
SELECT id, 'prob_critico',       60.0,  70.0,  NULL, 'CRIT estándar Ataque crit-DPS',                  'prydwen_default'
  FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'dano_critico',    150.0, 200.0, NULL, 'CDmg estándar Ataque crit-DPS',                 'prydwen_default'
  FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'ataque',          2300,  2600,  NULL, 'ATK objetivo M0 + Drill Rig R5',                'prydwen_default'
  FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'rec_energia',     1.4,   1.8,   NULL, 'ER mínima para uptime de skills · Drill Rig R5','prydwen_default'
  FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'bono_dano_elemento', 30.0, 45.0, NULL, 'Bono Eléctrico ideal con disco slot 5 + W-Engine','prydwen_default'
  FROM agents WHERE nombre='Cissia';

-- ---------------------------------------------------------------------------
-- 3. agent_score_thresholds (defaults RF-04 §12.3)
-- ---------------------------------------------------------------------------
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Cissia';

-- ---------------------------------------------------------------------------
-- 4. agent_awakenings (placeholder — Cissia v2.7 no tiene awakening desbloqueado)
-- ---------------------------------------------------------------------------
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0,
       'Sin awakening',
       'Cissia v2.7 no tiene awakening desbloqueado. Captura in-game cuando se compre la silueta.',
       'placeholder',
       0,
       'v2.7'
  FROM agents WHERE nombre='Cissia';

-- ---------------------------------------------------------------------------
-- 5. pj_weapon_synergy (6 filas — BONUS_MATRIX rol Ataque, Onboarding §6)
--    Bonus matrix canónica para Ataque crit-DPS:
--      dmg_boost           = 1.0  (DPS escala fuerte con multiplicadores de daño)
--      crit                = 1.5  (CR/CDmg es el principal pilar)
--      atk_boost           = 1.0  (ATK% escala el daño base)
--      anomaly_proficiency = 0.3  (cobertura mínima — no es su pilar)
--      energy_regen        = 0.4  (ER apenas para uptime)
--      pen_ratio           = 0.8  (Perforación útil contra enemigos lategame)
-- ---------------------------------------------------------------------------
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
SELECT id, 'dmg_boost',           1.0, 'Ataque: DPS escala con multiplicadores de daño',         'manual' FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'crit',                1.5, 'Ataque: CR/CDmg es el pilar principal',                  'manual' FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'atk_boost',           1.0, 'Ataque: ATK% escala el daño base',                       'manual' FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'anomaly_proficiency', 0.3, 'Ataque: cobertura mínima de Anomalía, no pilar',         'manual' FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'energy_regen',        0.4, 'Ataque: ER solo para uptime de skill',                   'manual' FROM agents WHERE nombre='Cissia'
UNION ALL SELECT id, 'pen_ratio',           0.8, 'Ataque: Perforación útil contra enemigos lategame',      'manual' FROM agents WHERE nombre='Cissia';

-- ---------------------------------------------------------------------------
-- 6. UPDATE 4 discos existentes (slots 1, 2, 3, 5)
--    Match exacto contra screenshot HoYoLAB de Cissia.
--    Estados previos: equipado=0, agente_asignado=NULL (sueltos).
-- ---------------------------------------------------------------------------
UPDATE inventory_discs
   SET agente_asignado = (SELECT id FROM agents WHERE nombre='Cissia'),
       equipado        = 1,
       notas           = COALESCE(notas || ' | ', '') || 'Equipado a Cissia 2026-05-04 (slot ' || slot || ')'
 WHERE id IN (261, 263, 259, 268);

-- ---------------------------------------------------------------------------
-- 7. INSERT 2 discos NUEVOS (slots 4 y 6) capturados esta sesión
--    Convención val*: '%' guardado como TEXT con sufijo (será normalizado en 2.0.4).
-- ---------------------------------------------------------------------------

-- Disco nuevo Slot 4 — Floración del alba (set 29)
-- Main: Probabilidad de Crítico 24%
-- Subs: Maestría Anomalía 18 (rolls 1) · PV 224 (rolls 1) · Defensa 30 (rolls 1) · PV 6% (rolls 1)
INSERT INTO inventory_discs (
    fecha_obtencion, set_id, slot,
    main_stat,                    main_valor,
    sub1, val1, rolls1,
    sub2, val2, rolls2,
    sub3, val3, rolls3,
    sub4, val4, rolls4,
    nivel, agente_asignado, equipado,
    score_evaluacion, agentes_compatibles, notas
) VALUES (
    CURRENT_TIMESTAMP, 29, 4,
    'Probabilidad de Crítico', '24%',
    'Maestría Anomalía',  18.0, 1,
    'PV',                 224.0, 1,
    'Defensa',            30.0, 1,
    'PV %',               '6%', 1,
    15,
    (SELECT id FROM agents WHERE nombre='Cissia'),
    1,
    NULL, NULL,
    'Capturado 2026-05-04. Slot 4 nuevo de Cissia.'
);

-- Disco nuevo Slot 6 — Nana a la luz cenicienta (set 35)
-- Main: Recuperación de Energía 60%
-- Subs: Ataque 19 (rolls 0) · Perforación 9 (rolls 0) · Daño Crítico 19.2% (rolls 3) · Prob Crítico 4.8% (rolls 1)
INSERT INTO inventory_discs (
    fecha_obtencion, set_id, slot,
    main_stat,                main_valor,
    sub1, val1, rolls1,
    sub2, val2, rolls2,
    sub3, val3, rolls3,
    sub4, val4, rolls4,
    nivel, agente_asignado, equipado,
    score_evaluacion, agentes_compatibles, notas
) VALUES (
    CURRENT_TIMESTAMP, 35, 6,
    'Recuperación de Energía', '60%',
    'Ataque',         19.0, 0,
    'Perforación',     9.0, 0,
    'Daño Crítico',  '19.2%', 3,
    'Prob Crítico',  '4.8%', 1,
    15,
    (SELECT id FROM agents WHERE nombre='Cissia'),
    1,
    NULL, NULL,
    'Capturado 2026-05-04. Slot 6 nuevo de Cissia.'
);

COMMIT;

-- ---------------------------------------------------------------------------
-- 8. Validación post-onboarding (Onboarding_Nuevo_PJ.md §12)
-- ---------------------------------------------------------------------------
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks (los SELECT muestran 'expected_*' como nombre de columna —
-- el valor en COUNT(*) debe coincidir con el sufijo).
SELECT 'agents Cissia'                AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE nombre='Cissia';

SELECT 'thresholds (=5)'              AS check_name, COUNT(*) AS expected_5
  FROM agent_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia');

SELECT 'score_thresholds (=1)'        AS check_name, COUNT(*) AS expected_1
  FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia');

SELECT 'awakening placeholder (=1)'   AS check_name, COUNT(*) AS expected_1
  FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia');

SELECT 'pj_weapon_synergy (=6)'       AS check_name, COUNT(*) AS expected_6
  FROM pj_weapon_synergy WHERE pj_id=(SELECT id FROM agents WHERE nombre='Cissia');

SELECT 'discos equipados (=6)'        AS check_name, COUNT(*) AS expected_6
  FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND equipado=1;

SELECT 'discos nuevos s4/s6 (=2)'     AS check_name, COUNT(*) AS expected_2
  FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND notas LIKE '%nuevo%';

SELECT 'discos sueltos liberados (=4)' AS check_name, COUNT(*) AS expected_4
  FROM inventory_discs WHERE id IN (259, 261, 263, 268)
                          AND equipado=1
                          AND agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia');

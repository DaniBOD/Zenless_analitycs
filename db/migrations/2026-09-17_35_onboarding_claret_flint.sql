-- =============================================================================
-- Onboarding Claret Flint · 2026-09-17 · migración 35
-- =============================================================================
-- Claret Flint: S · Eléctrico · Armero · Flint Workshop · Nivel 60/60 · M0 (CINEMA 0/6) · v3.2.
--
-- A diferencia de Aria, trae VOCABULARIO NUEVO en tres capas:
--   · rol 'Armero' (EN "Armorer"): especialidad nueva de v3.2. No existía en ninguna tabla ni
--     mapa. Un rol desconocido caía EN SILENCIO al arquetipo ATK_DPS (repositories.AgentRepo),
--     que penaliza DEF% con -1.0 — y Claret escala con DEF. Por eso esta migración crea su
--     arquetipo (ARMORER_DEF) y el mismo commit lo mapea en código.
--   · facción 'Flint Workshop' (pantalla ES: "Taller Flint de Roscaelifer"; el nombre EN sale del
--     logo del wiki y de Game8). Logo agregado en la entrega de assets.
--   · dos stats propios del rol, que ocupan en la ficha los lugares de ATK y de Rec. de energía:
--     "Daño de laceración" (Laceration DMG) y "Acumulación Automática de afiladura". Decisión de
--     Daniel: columnas nuevas en `agents`, persistidas en vivo por S18.
--
-- FUENTES (RNF-02)
--   · Identidad y stats EFECTIVOS: la captura del propio juego
--     Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_17.png
--     (S18, "Atributos base"). La ficha NO muestra ATK ⇒ ataque NULL.
--   · Kit, build y objetivos: Prydwen.gg, guía de Claret actualizada el 2026-09-09 (patch 3.2),
--     leída el 2026-09-17. Cruce con Game8 (rareza, atributo, especialidad, facción, release).
--       - "skill DMG Multipliers are based on DEF"; el crit del Sharp DMG usa el Laceration DMG
--         Bonus en vez del CRIT DMG; 1 % de CD inicial → +0,35 % de CR inicial.
--       - Discos: Thorned Rose 4pc + 2pc Puffer Electro (rec.) / Woodpecker Electro / Soul Rock /
--         Thunder Metal / Branch & Blade Song. Mains: 4 CRIT Rate · 5 PEN Ratio · 6 DEF%.
--       - Substats: CRIT RATE > DEF% > CRIT DMG > PEN > DEF.
--       - Endgame Nv60: DEF 2300-2600+ · HP 9500+ · CRIT RATE 128,9 % con signature, tope 200 %.
--
-- NO se inventa (NULL): ataque (no está en la ficha), perforacion plana, rec_energia (su celda es
--   la afiladura), bono_dano_elemento, weapon_*, set_*, disco6_main — los llena la captura en vivo.
--   Sus W-Engines (Crimson Thirst, Bloodmarrow Coffer, Catty Luck) NO están en `weapons` y entran
--   por el flujo normal de S26/S30 (decisión de Daniel).
--
-- ⚠️ Backup RNF-01 lo hace el runner. App cerrada. Ensayar primero sobre una COPIA:
--    python app/scripts/qa/apply_migration.py <este .sql> --db <copia> --no-backup
-- =============================================================================

BEGIN TRANSACTION;

-- 1. Columnas del rol Armero. Unidades como el resto de la tabla: % en enteros (150.0), la
--    afiladura cruda (1.5), igual que rec_energia.
ALTER TABLE agents ADD COLUMN dano_laceracion REAL;
ALTER TABLE agents ADD COLUMN acumulacion_afiladura REAL;

-- 2. Arquetipo del Armero. mains_5 admite los 6 bonos elementales (contrato
--    test_disc_archetypes_contrato: un arquetipo elemental no elige elemento) + Tasa de Perforación.
--    mains_4 suma Daño Crítico a Prob. Crítica: el kit convierte CD en CR (Prydwen); el main
--    recomendado sigue siendo CR, y el peso de substats lo refleja (1.0 contra 0.7).
INSERT INTO disc_archetypes (id, code, nombre, descripcion, mains_4, mains_5, mains_6,
                             substats_positivos, substats_perjudiciales, threshold_stock)
VALUES (
    7, 'ARMORER_DEF', 'Armero DEF-scaler',
    'Armeros cuyo daño escala con DEF y crit (Sharp DMG). Primero: Claret Flint, v3.2.',
    '["Prob. Crítica","Daño Crítico"]',
    '["Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter","Bono Daño Viento","Tasa de Perforación"]',
    '["DEF%"]',
    '{"Prob. Crítica":1.0,"DEF%":0.9,"Daño Crítico":0.7,"Perforación":0.6,"DEF":0.4}',
    '{"ATK%":-1.0,"ATK":-0.8,"Maestría de Anomalía":-0.8}',
    0.7
);

-- 3. Sets del arquetipo: Thorned Rose ("made for Armorers") primario; los 2pc de Prydwen, secundarios.
INSERT INTO disc_set_archetype (set_id, archetype_id, prioridad) VALUES
    (55, 7, 1),   -- Rosa espinosa / Thorned Rose
    (40, 7, 2),   -- Tecno tetraodóntido / Puffer Electro (recomendado)
    (48, 7, 2),   -- Tecno Pícido / Woodpecker Electro
    (44, 7, 2),   -- Rock espiritual / Soul Rock
    (46, 7, 2),   -- Metal Eléctrico / Thunder Metal
    (25, 7, 2);   -- Balada de la rama y la espada / Branch & Blade Song

-- 4. agents
INSERT INTO agents (
    nombre, rango, nivel, mindscape, elemento, rol, faccion,
    pv, ataque, defensa, impacto,
    prob_critico, dano_critico,
    tasa_anomalia, maestria_anomalia,
    tasa_perforacion, perforacion,
    rec_energia, bono_dano_elemento,
    dano_laceracion, acumulacion_afiladura,
    weapon_id, weapon_nivel, weapon_rango,
    set_4p_id, set_2p_id, disco6_main,
    protected_build, notas
) VALUES (
    'Claret Flint', 'S', 60, 0, 'Eléctrico', 'Armero', 'Flint Workshop',
    8360, NULL, 927, 93,
    95.2, 93.2,
    86, 79,
    32.0, NULL,
    NULL, NULL,
    150.0, 1.5,
    NULL, NULL, NULL,
    NULL, NULL, NULL,
    0,
    'Onboarding 2026-09-17 (mig 35), v3.2. Stats EFECTIVOS de la ficha S18 '
    || '(atributos_base_ejemplo_17): Nivel 60/60, M0. La ficha del Armero no muestra ATK -> NULL; '
    || 'en su lugar Dano de laceracion 150 % y, en el de Rec. de energia, Acumulacion Automatica '
    || 'de afiladura 1.5. weapon_* y set_* NULL: los llena la captura en vivo. Build/objetivos: '
    || 'Prydwen 2026-09-09. W-Engines fuera de catalogo (flujo S26/S30).'
);

-- 5. agent_score_thresholds (defaults del proyecto)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre = 'Claret Flint';

-- 6. agent_awakenings — placeholder. El patch SÍ está confirmado (Game8 + Prydwen): v3.2.
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening',
       'Claret Flint: awakening no capturado todavia. Capturar in-game al comprar la silueta.',
       'placeholder', 0, 'v3.2'
FROM agents WHERE nombre = 'Claret Flint';

-- 7. agent_thresholds — los objetivos endgame de Prydwen, con fuente y fecha.
INSERT INTO agent_thresholds (agente_id, stat, valor_minimo, valor_optimo, valor_maximo, descripcion, fuente)
SELECT id, 'defensa', 2300.0, 2600.0, NULL,
       'DEF endgame Nv60: sus multiplicadores escalan con DEF', 'prydwen_2026-09-09'
FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'pv', 9500.0, NULL, NULL,
       'HP endgame Nv60', 'prydwen_2026-09-09'
FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'prob_critico', 128.9, 200.0, 200.0,
       'CR endgame con signature (Crimson Thirst); el kit convierte CD en CR, tope 200 %', 'prydwen_2026-09-09'
FROM agents WHERE nombre = 'Claret Flint';

-- 8. agent_substat_preferences — el orden de Prydwen (positivos) y el kit (negativos).
INSERT INTO agent_substat_preferences (agente_id, substat, peso, fuente)
SELECT id, 'Prob. Crítica',        1.0, 'prydwen'           FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'DEF%',                 0.9, 'prydwen'           FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'Daño Crítico',         0.7, 'prydwen'           FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'Perforación',          0.6, 'prydwen'           FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'DEF',                  0.4, 'prydwen'           FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'ATK%',                -1.0, 'default_archetype' FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'ATK',                 -0.8, 'default_archetype' FROM agents WHERE nombre = 'Claret Flint' UNION ALL
SELECT id, 'Maestría de Anomalía',-0.8, 'default_archetype' FROM agents WHERE nombre = 'Claret Flint';

-- 9. pj_weapon_synergy — 6 filas. No hay matriz para el rol Armero: se deriva del kit, con la
--    razón escrita. energy_regen NO tiene fuente: queda el default del rol de ataque, anotado así.
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
SELECT id, 'crit',                1.5, 'Armero: CR es el pilar (Prydwen: substat #1, objetivo 128,9-200 %).', 'manual' FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'dmg_boost',           1.0, 'Armero: DPS principal; los multiplicadores de daño escalan su burst.', 'manual' FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'pen_ratio',           0.8, 'Armero: PEN Ratio es el main recomendado de slot 5 (Prydwen).', 'manual' FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'atk_boost',           0.0, 'Armero: los multiplicadores escalan con DEF, no con ATK (kit, Prydwen).', 'manual' FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'anomaly_proficiency', 0.0, 'Armero: el kit no aplica anomalías; su daño es Sharp DMG.', 'manual' FROM agents WHERE nombre = 'Claret Flint'
UNION ALL
SELECT id, 'energy_regen',        0.4, 'SIN FUENTE: default del rol de ataque, a revisar cuando haya guía de ER para Armeros.', 'manual' FROM agents WHERE nombre = 'Claret Flint';

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada `expected_N` tiene que valer exactamente N.
SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Claret Flint' AND rango = 'S' AND nivel = 60 AND mindscape = 0
   AND elemento = 'Eléctrico' AND rol = 'Armero' AND faccion = 'Flint Workshop';

SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Claret Flint' AND pv = 8360 AND defensa = 927 AND impacto = 93
   AND prob_critico = 95.2 AND dano_critico = 93.2
   AND tasa_anomalia = 86 AND maestria_anomalia = 79 AND tasa_perforacion = 32.0
   AND dano_laceracion = 150.0 AND acumulacion_afiladura = 1.5;

-- Lo que la ficha no muestra quedó NULL, no en cero (RNF-02).
SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Claret Flint' AND ataque IS NULL AND rec_energia IS NULL
   AND perforacion IS NULL AND bono_dano_elemento IS NULL
   AND weapon_id IS NULL AND set_4p_id IS NULL AND set_2p_id IS NULL AND disco6_main IS NULL;

-- Las columnas nuevas NO tocaron a nadie más.
SELECT COUNT(*) AS expected_51 FROM agents
 WHERE dano_laceracion IS NULL AND acumulacion_afiladura IS NULL;

SELECT COUNT(*) AS expected_1 FROM disc_archetypes WHERE id = 7 AND code = 'ARMORER_DEF';
SELECT COUNT(*) AS expected_6 FROM disc_set_archetype WHERE archetype_id = 7;
SELECT COUNT(*) AS expected_3 FROM agent_thresholds
 WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'Claret Flint');
SELECT COUNT(*) AS expected_8 FROM agent_substat_preferences
 WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'Claret Flint');
SELECT COUNT(*) AS expected_6 FROM pj_weapon_synergy
 WHERE pj_id = (SELECT id FROM agents WHERE nombre = 'Claret Flint');

-- Totales después de la migración.
SELECT COUNT(*) AS expected_52 FROM agents;
SELECT COUNT(*) AS expected_52 FROM agent_score_thresholds;
SELECT COUNT(*) AS expected_7 FROM disc_archetypes;
SELECT COUNT(*) AS expected_45 FROM disc_set_archetype;
SELECT COUNT(*) AS expected_114 FROM agent_thresholds;
SELECT COUNT(*) AS expected_68 FROM agent_substat_preferences;
SELECT COUNT(*) AS expected_17 FROM agent_awakenings;
SELECT COUNT(*) AS expected_300 FROM pj_weapon_synergy;

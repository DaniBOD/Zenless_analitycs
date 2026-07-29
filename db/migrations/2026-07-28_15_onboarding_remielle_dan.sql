-- =============================================================================
-- Onboarding Remielle Dan (PARCIAL) · patch v3.1 · 2026-07-28
-- =============================================================================
-- Remielle Dan: S · Lumen (elemento NUEVO) · Anomalía · Covenant of Dayat (facción
--   NUEVA) · M0 (CINEMA 0/6) · Nivel 01.
--
-- FUENTE ÚNICA (RNF-02): la captura del propio juego
--   Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/
--   atributos_base_ejemplo_15.png  (S18 · pestaña "Atributos base")
-- Nada de acá viene de Prydwen ni de estimación: todo se lee en pantalla.
--
-- DECISIONES DE NOMENCLATURA (DaniBOD 2026-07-28) — las dos quedan grabadas:
--   · elemento = 'Lumen'. La PANTALLA dice "Lumiflujo"; se mapea a 'Lumen' igual
--     que Ígneo→Fuego y Etéreo→Éter (el rótulo de pantalla nunca es el canónico).
--     El mapeo vive en parser_agent_stats.py::_ELEMENTO_SCREEN_MAP y coincide con
--     el 'lumen' que ya admite el CHECK de enemy_resistances (migración 14).
--   · faccion = 'Covenant of Dayat', del logo dorado de la propia pantalla. El
--     texto ES dice "Alianza de Dayat", pero 13 de las 15 facciones de la tabla
--     están en inglés, así que manda la convención mayoritaria.
--   · nombre = 'Remielle Dan' (nombre completo tal cual la pantalla), consistente
--     con 'Jane Doe', 'Zhu Yuan', 'Ju Fufu', 'Pan Yinhu'.
--
-- STATS: son los de NIVEL 01 / M0 **sin discos equipados** (PV 602 / ATK 124 son
--   valores base puros; prob_critico 5 % y dano_critico 50 % son los base
--   universales). Son REALES, no inventados — pero PROVISORIOS: cambian al subir
--   nivel y al equipar. RECAPTURAR después. Mismo tratamiento que Pyrois (mig 09),
--   con la diferencia de que Pyrois sí tenía discos al azar puestos.
--
-- NO expuestos en pantalla → NULL (RNF-02, no inventar):
--   perforacion (plana), bono_dano_elemento, weapon_*, set_*, disco6_main.
-- agent_thresholds → NO se cargan: son objetivos de build por PJ y requieren
--   Prydwen, que a menos de 24 h del release todavía no publicó a Remielle.
--
-- Lo que SÍ habilita esta migración: el RECONOCIMIENTO por nombre en S18 y la
--   COSECHA de su badge (dueño de discos).
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App cerrada o en
--   READONLY. Runner: python app/scripts/qa/apply_migration.py <este archivo>
-- =============================================================================

BEGIN TRANSACTION;

-- 1. agents (core + stats de Nivel 01 / M0, sin discos)
INSERT INTO agents (
    nombre, rango, nivel, mindscape, elemento, rol, faccion,
    pv, ataque, defensa, impacto,
    prob_critico, dano_critico,
    tasa_anomalia, maestria_anomalia,
    tasa_perforacion, perforacion,
    rec_energia, bono_dano_elemento,
    weapon_id, weapon_nivel, weapon_rango,
    set_4p_id, set_2p_id, disco6_main,
    protected_build, notas
) VALUES (
    'Remielle Dan', 'S', 1, 0, 'Lumen', 'Anomalía', 'Covenant of Dayat',
    602, 124, 48, 83,
    5.0, 50.0,
    115, 116,
    0.0, NULL,
    1.2, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL,
    0,
    'Onboarding PARCIAL 2026-07-28 (patch v3.1). ELEMENTO LUMEN = estandar NUEVO; la PANTALLA lo rotula "Lumiflujo" (mapeo en parser_agent_stats.py::_ELEMENTO_SCREEN_MAP). FACCION Covenant of Dayat = NUEVA (texto ES en pantalla: "Alianza de Dayat"; se guarda el nombre del logo por convencion mayoritaria de la tabla). Titulo in-game: "Agonista de la Vacuidad: Lumiflujo Temporal". Stats = NIVEL 01 / M0 SIN DISCOS (atributos_base_ejemplo_15): reales pero PROVISORIOS -> RECAPTURAR al subir nivel/equipar. perforacion plana + bono_dano_elemento no expuestos -> NULL. agent_thresholds pending (Prydwen todavia no publico a Remielle a <24h del release). Falta splash art + avatar_ref para la cosecha de badges + IA (49 pares). Sin awakening. Cargada para RECONOCIMIENTO en S18 + cosecha de badge.'
);

-- 2. agent_score_thresholds (defaults RF-04 §12.3 — genuinos, no inventados)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Remielle Dan';

-- 3. agent_awakenings (placeholder — el texto solo se obtiene comprando la silueta)
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening',
       'Remielle Dan: awakening no capturado todavia. Capturar in-game al comprar la silueta.',
       'placeholder', 0, 'v3.1'
  FROM agents WHERE nombre='Remielle Dan';

-- 4. pj_weapon_synergy (6 filas · BONUS_MATRIX rol Anomalía · Onboarding_Nuevo_PJ.md §6)
--    Bonus y razones espejo de los PJs Anomalía ya cargados (modelo: Burnice).
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
SELECT id, 'dmg_boost', 0.7, 'DMG genérico ayuda pero no es prioritario.', 'manual' FROM agents WHERE nombre='Remielle Dan'
UNION ALL SELECT id, 'crit', 0.4, 'Las anomalías no critean; bonus bajo.', 'manual' FROM agents WHERE nombre='Remielle Dan'
UNION ALL SELECT id, 'atk_boost', 0.6, 'ATK escala daño aplicado por anomalías.', 'manual' FROM agents WHERE nombre='Remielle Dan'
UNION ALL SELECT id, 'anomaly_proficiency', 1.5, 'Anomalía escala directamente con AP; máxima sinergia.', 'manual' FROM agents WHERE nombre='Remielle Dan'
UNION ALL SELECT id, 'energy_regen', 1.2, 'Off-field rotation depende de EX/Ult constantes.', 'manual' FROM agents WHERE nombre='Remielle Dan'
UNION ALL SELECT id, 'pen_ratio', 0.4, 'PEN ayuda contra DEF en componente de daño directo.', 'manual' FROM agents WHERE nombre='Remielle Dan';

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada SELECT devuelve una columna `expected_N` que DEBE valer N.
SELECT 'agents Remielle Dan (=1)' AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE nombre='Remielle Dan';
SELECT 'elemento = Lumen'         AS check_name, elemento AS expected_Lumen
  FROM agents WHERE nombre='Remielle Dan';
SELECT 'rol = Anomalia'           AS check_name, rol AS expected_Anomalia
  FROM agents WHERE nombre='Remielle Dan';
SELECT 'faccion nueva'            AS check_name, faccion AS expected_CovenantOfDayat
  FROM agents WHERE nombre='Remielle Dan';
SELECT 'score_thresholds (=1)'    AS check_name, COUNT(*) AS expected_1
  FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Remielle Dan');
SELECT 'awakening (=1)'           AS check_name, COUNT(*) AS expected_1
  FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Remielle Dan');
SELECT 'weapon_synergy (=6)'      AS check_name, COUNT(*) AS expected_6
  FROM pj_weapon_synergy WHERE pj_id=(SELECT id FROM agents WHERE nombre='Remielle Dan');
SELECT 'unico agente Lumen (=1)'  AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE elemento='Lumen';
SELECT 'roster total (=50)'       AS check_name, COUNT(*) AS expected_50 FROM agents;

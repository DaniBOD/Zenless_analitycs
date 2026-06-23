-- =============================================================================
-- Onboarding Pyrois (PARCIAL) · 2026-06-21
-- =============================================================================
-- Pyrois: rango ∞ ("infinito", NUEVO tier · ZZZ no usaba más que S/A) · Éter ·
--   Ataque · Facción Faetón (NUEVA) · M0 (Nivel 01).
-- Confirmado por el usuario in-game + captura Perfil_agente/atributos_base_ejemplo_14.png
--   y Menu_Personajes/Ejemplo_9.png (RNF-02). El elemento se muestra "Etéreo" en pantalla
--   → canónico DB "Éter" (_canon_elemento mapea 'eter' ⊆ 'etereo' → 'Éter'; el cross-check
--   de S18 funciona). rango '∞' (U+221E) se guarda tal cual (la columna es TEXT libre, sin
--   CHECK; nada del core keyea sobre agents.rango). Fallback acordado si molestara: 'Z'.
--
-- Stats EFECTIVOS = los de NIVEL 01 / M0 con los discos al azar que el usuario le asignó
--   (RNF-02: son reales, no inventados). Cambiarán al subir de nivel → RECAPTURAR luego.
--   rec_energia=1.0 (la pantalla muestra "1"; NO es truncamiento — los demás agentes SÍ
--   muestran decimales como 1.2/2.16, así que el "1" de Pyrois es el valor real). perforacion plana y
--   bono_dano_elemento no expuestos → NULL. agent_thresholds (objetivos Prydwen) → pending
--   (RNF-02: no inventar). Se cargan synergy (matriz Ataque) + score_thresholds + awakening
--   placeholder. Lo de acá habilita el RECONOCIMIENTO (latch por nombre/stats) y la COSECHA
--   del badge de Pyrois.
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App en READONLY (sin lock de escritura).
-- =============================================================================

BEGIN TRANSACTION;

-- 1. agents (core + stats efectivos Nivel 01 / M0)
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
    'Pyrois', '∞', 1, 0, 'Éter', 'Ataque', 'Faetón',
    2985, 557, 235, 94,
    27.8, 114.0,
    94, 129,
    0.0, NULL,
    1.2, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL,
    0,
    'Onboarding PARCIAL 2026-06-21 (patch v3.x). RANGO INFINITO (∞) = tier NUEVO; FACCION Faetón = NUEVA; ELEMENTO mostrado "Etéreo" -> canon Eter. Stats = NIVEL 01 / M0 con discos al azar (atributos_base_ejemplo_14): reales pero PROVISORIOS -> RECAPTURAR al subir nivel/build. rec_energia=1.2 base universal (pantalla mostro "1"). perforacion plana + bono_dano_elemento no expuestos -> NULL. agent_thresholds pending (Prydwen Pyrois). Falta splash art (hay pyrois-ico/extend.webp en Interfaz/splash_arts, registrar en descargar_splash_arts) + IA (44 pares). Sin awakening. Cargado para COSECHA de badge + reconocimiento de dueno de discos.'
);

-- 2. agent_score_thresholds (defaults RF-04 §12.3 — genuinos, no inventados)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Pyrois';

-- 3. agent_awakenings (placeholder)
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening',
       'Pyrois: awakening no capturado todavia. Capturar in-game al comprar la silueta.',
       'placeholder', 0, 'v3.0'
  FROM agents WHERE nombre='Pyrois';

-- 4. pj_weapon_synergy (6 filas · matriz rol Ataque · espejo de Cissia, fuente 'manual')
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
SELECT id, 'dmg_boost', 1.0, 'Ataque: DPS escala con multiplicadores de daño', 'manual' FROM agents WHERE nombre='Pyrois'
UNION ALL SELECT id, 'crit', 1.5, 'Ataque: CR/CDmg es el pilar principal', 'manual' FROM agents WHERE nombre='Pyrois'
UNION ALL SELECT id, 'atk_boost', 1.0, 'Ataque: ATK% escala el daño base', 'manual' FROM agents WHERE nombre='Pyrois'
UNION ALL SELECT id, 'anomaly_proficiency', 0.3, 'Ataque: cobertura mínima de Anomalía, no pilar', 'manual' FROM agents WHERE nombre='Pyrois'
UNION ALL SELECT id, 'energy_regen', 0.4, 'Ataque: ER solo para uptime de skill', 'manual' FROM agents WHERE nombre='Pyrois'
UNION ALL SELECT id, 'pen_ratio', 0.8, 'Ataque: Perforación útil contra enemigos lategame', 'manual' FROM agents WHERE nombre='Pyrois';

COMMIT;

-- Validación (RNF-01) — correr aparte (PRAGMA + smoke checks)
PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT 'agents Pyrois (=1)'      AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE nombre='Pyrois';
SELECT 'rango = inf'             AS check_name, rango     AS expected_inf
  FROM agents WHERE nombre='Pyrois';
SELECT 'score_thresholds (=1)'   AS check_name, COUNT(*) AS expected_1
  FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Pyrois');
SELECT 'awakening (=1)'          AS check_name, COUNT(*) AS expected_1
  FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Pyrois');
SELECT 'weapon_synergy (=6)'     AS check_name, COUNT(*) AS expected_6
  FROM pj_weapon_synergy WHERE pj_id=(SELECT id FROM agents WHERE nombre='Pyrois');
SELECT 'roster total (=49)'      AS check_name, COUNT(*) AS expected_49 FROM agents;

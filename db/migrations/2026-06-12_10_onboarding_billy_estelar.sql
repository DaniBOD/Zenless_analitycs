-- =============================================================================
-- Onboarding Billy Estelar (Billy Kid Estelar / "Billy Starlight") · 2026-06-12
-- =============================================================================
-- Trigger: PJ nuevo del banner actual (v2.x). El usuario lo consiguue recién (M0).
-- Objetivo PRIMARIO: que el sistema lo identifique SIN confundirlo con "Billy" (id 12,
--   A · Físico · Ataque). Billy Estelar es S · Físico · Disruptivos (escala con HP/
--   Fuerza Bruta, no ATK — patrón Manato).
--
-- Onboarding PARCIAL (RNF-02): se cargan SOLO datos confirmados del screenshot del
--   usuario (su build M0 real, dato autoritativo para el vector de identificación
--   por stats — Capa 4 de parser_agent_stats). Se DIFIERE lo que requiere fuente
--   externa no disponible aún:
--     - pj_weapon_synergy (6 filas): no hay BONUS_MATRIX confirmada para rol
--       Disruptivos/Rupture → NO se inventa (RNF-02). Pendiente Prydwen.
--     - splash art {id}_{nombre}.png + catalogación IA (44 pares) + thresholds HP/
--       Fuerza Bruta finos → pendientes.
--   Quedan: identidad+stats (vector ID), thresholds CRIT genéricos, score_thresholds
--   default, awakening placeholder.
--
-- Aplica:
--   1. INSERT en agents (Billy Estelar · S · Físico · Disruptivos · M0 · Cunning Hares)
--   2. INSERT agent_thresholds (2 — crit genérico; está build crit 72.2/118.8)
--   3. INSERT agent_score_thresholds (defaults 0.75 / 0.50)
--   4. INSERT agent_awakenings (placeholder activo=0)
--   5. PRAGMA + smoke checks
--
-- Acompaña cambio de CÓDIGO (no SQL): ICO_ALIAS["Billy-starlight"]="Billy Estelar"
--   en app/core/avatar_descriptor.py — alinea el badge/-ico con el nombre de roster.
--
-- ⚠️ Backup previo: db\danibod_zzz_v2.backup_premig_20260612_140051.db (RNF-01).
--
-- Stats confirmados del screenshot (Pj_stats Billy Estelar, M0, build equipado):
--   PV 20573 · ATK 2043 · DEF 689 · Impacto 95 · CR 72.2% · CDmg 118.8%
--   Tasa Anomalía 90 · Maestría Anomalía 89 · (Fuerza Bruta 2669, Adrenalina 2 — sin
--   columna; se notan en notas). Rec.Energía / Perforación / Bono no visibles → NULL.
--   Facción: banner muestra "Liebres Astutas" (Cunning Hares); el logo dice
--   "Gentle House" — discrepancia anotada, a verificar (no afecta identificación).
-- =============================================================================

BEGIN TRANSACTION;

-- 1. INSERT en agents -------------------------------------------------------
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
    'Billy Estelar',
    'S',
    60,
    0,                 -- mindscape M0 (Cinema 0/6)
    'Físico',
    'Disruptivos',     -- escala con HP/Fuerza Bruta (patrón Manato), NO con ATK
    'Cunning Hares',   -- texto banner "Liebres Astutas" (logo "Gentle House" — verificar)
    -- Stats efectivos M0 (screenshot del usuario — autoritativo p/ vector ID Capa 4):
    20573,             -- pv (distintivo: el más cercano, Manato, está a >25%)
    2043,              -- ataque (modesto — DPS de HP/Rupture)
    689,               -- defensa
    95,                -- impacto
    72.2,              -- prob_critico
    118.8,             -- dano_critico
    90,                -- tasa_anomalia
    89,                -- maestria_anomalia
    NULL,              -- tasa_perforacion (no visible en screenshot)
    NULL,              -- perforacion (no visible)
    NULL,              -- rec_energia (no visible)
    NULL,              -- bono_dano_elemento (Físico — no aplica/no visible)
    NULL, NULL, NULL,  -- weapon (a capturar in-game)
    NULL, NULL, NULL,  -- set_4p / set_2p / disco6_main (a capturar)
    'ONBOARDING PARCIAL v2.x (2026-06-12). PJ nuevo banner actual, M0. Identidad+stats '
    || 'cargados del screenshot del usuario (build M0 real). Rol Disruptivos: escala con '
    || 'Fuerza Bruta (2669) / HP, no ATK — patrón Manato. Stats sin columna: Fuerza Bruta '
    || '2669, Acumulación Automática de Adrenalina 2. NO confundir con Billy (id 12, A·Ataque). '
    || 'PENDIENTE: pj_weapon_synergy (matriz Rupture sin confirmar — RNF-02), thresholds '
    || 'HP/Fuerza Bruta, splash art, catalogación IA (44 pares), facción (verificar '
    || '"Gentle House" vs Cunning Hares). -ico: Billy-starlight.png (alias en código).'
);

-- 2. agent_thresholds (crit genérico — build crit 72.2/118.8) ----------------
INSERT INTO agent_thresholds (agente_id, stat, valor_minimo, valor_optimo, valor_maximo, descripcion, fuente)
SELECT id, 'prob_critico', 60.0,  70.0,  NULL, 'CRIT estándar crit-DPS', 'prydwen_default'
  FROM agents WHERE nombre='Billy Estelar'
UNION ALL SELECT id, 'dano_critico', 150.0, 200.0, NULL, 'CDmg estándar crit-DPS', 'prydwen_default'
  FROM agents WHERE nombre='Billy Estelar';

-- 3. agent_score_thresholds (defaults RF-04 §12.3) --------------------------
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Billy Estelar';

-- 4. agent_awakenings (placeholder) -----------------------------------------
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0,
       'Sin awakening',
       'Billy Estelar M0: awakening no desbloqueado. Capturar in-game cuando se compre la silueta.',
       'placeholder',
       0,
       'v2.x'
  FROM agents WHERE nombre='Billy Estelar';

COMMIT;

-- 5. Validación -------------------------------------------------------------
PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT 'agents Billy Estelar' AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE nombre='Billy Estelar';
SELECT 'NO colisiona con Billy' AS check_name, COUNT(*) AS expected_2
  FROM agents WHERE nombre IN ('Billy', 'Billy Estelar');
SELECT 'thresholds (=2)' AS check_name, COUNT(*) AS expected_2
  FROM agent_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Billy Estelar');
SELECT 'score_thresholds (=1)' AS check_name, COUNT(*) AS expected_1
  FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Billy Estelar');
SELECT 'awakening placeholder (=1)' AS check_name, COUNT(*) AS expected_1
  FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Billy Estelar');
SELECT 'pv distintivo (Billy Estelar=20573)' AS check_name, pv AS expected_20573
  FROM agents WHERE nombre='Billy Estelar';

-- =============================================================================
-- Onboarding Velina (PARCIAL) · 2026-06-19
-- =============================================================================
-- Velina: S · Viento (elemento NUEVO) · Anomalía · External Strategy Department · M0
-- Datos confirmados por el usuario in-game 2026-06-19 (RNF-02): rareza, elemento, rol, facción.
-- Stats efectivos NO disponibles aún → NULL + pending_capture (RNF-02: no inventar).
-- Thresholds de stat NO se cargan (Velina-específicas, requieren Prydwen) → pending.
-- Onboarding PARCIAL (como Billy Estelar): faltan agent_thresholds, pj_weapon_synergy,
-- splash art, catalogación IA. Lo que se carga acá habilita el RECONOCIMIENTO (latch S18 por
-- nombre) y la COSECHA de su badge. El resto se completa cuando haya datos (RNF-02).
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App cerrada (no lock).
-- =============================================================================

BEGIN TRANSACTION;

-- 1. agents (core; stats en NULL = pending_capture)
INSERT INTO agents (nombre, rango, nivel, mindscape, elemento, rol, faccion, protected_build, notas)
VALUES (
    'Velina', 'S', 60, 0, 'Viento', 'Anomalía', 'External Strategy Department', 0,
    'Onboarding PARCIAL 2026-06-19 (patch v3.x). ELEMENTO VIENTO = nuevo en el roster (antes solo Fuego/Hielo/Electrico/Fisico/Eter) -> revisar impacto en sets/scoring de Viento. Stats efectivos pending_capture (capturar in-game/HoYoLAB). agent_thresholds pending (Prydwen Velina). Falta pj_weapon_synergy + splash + IA. Sin awakening. Faccion "External Strategy Department" tomada del icono Faction_External_Strategy_Department_Icon.webp (confirmar nombre canonico).'
);

-- 2. agent_score_thresholds (defaults RF-04 §12.3 — genuinos, no inventados)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Velina';

-- 3. agent_awakenings (placeholder)
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening',
       'Velina: awakening no capturado todavia. Capturar in-game al comprar la silueta.',
       'placeholder', 0, 'v3.0'
  FROM agents WHERE nombre='Velina';

COMMIT;

-- Validación (RNF-01)
PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT 'agents Velina'        AS check_name, COUNT(*) AS expected_1
  FROM agents WHERE nombre='Velina';
SELECT 'score_thresholds (=1)' AS check_name, COUNT(*) AS expected_1
  FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Velina');
SELECT 'awakening (=1)'        AS check_name, COUNT(*) AS expected_1
  FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Velina');
SELECT 'roster total (=48)'    AS check_name, COUNT(*) AS expected_48 FROM agents;

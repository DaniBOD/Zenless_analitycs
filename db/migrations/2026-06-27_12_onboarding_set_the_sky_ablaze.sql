-- Onboarding de SET de discos nuevo: "Firmamento llameante" (The Sky Ablaze, ZZZ v3.0).
-- Sigue Documentacion/Onboarding_Nuevos_Assets.md §2. Plantilla: Salón huracanado (commit 426a220).
--
-- DETECCIÓN (RF-04): el usuario farmeó discos del set y la captura S3 los leyó como set
--   DESCONOCIDO (el parser lee el nombre del texto, pero faltaba en disc_sets → sin scoring de
--   bono de set ni persistencia futura). QA 2026-06-27 (Ejemplo_6/7 carpeta 02).
--
-- EFECTOS confirmados (RNF-02, fuente Game8 + búsqueda agregada Prydwen/141store, verbatim):
--   2pc: "Ether DMG +10%"  (cliente ES: "Daño etéreo +10%").
--   4pc: "When the equipper is an Ether attribute Agent, their CRIT DMG increases by 30%. When the
--         equipper uses an EX Special Attack or Ultimate, their ATK increases by 10% for 30s.
--         Repeated triggers reset the duration."
--   Es el set FIRMA (BiS) de Pyrois (Éter · Ataque). Otros DPS de Éter pueden usar el 2pc de combo.
--
-- bonus_2p_stat usa la convención en inglés de la tabla ("Fire DMG"/"Ether DMG"…) → "Ether DMG".
-- ARQUETIPO (§2 paso 2, RF-06): ATK_DPS — el 4pc es CRIT DMG + ATK (DPS de crítico puro, NO anomalía;
--   por eso NO se le asigna ANOMALY, a diferencia de Metal Caótico set_id 28).
--
-- Logo: ya existe Drive_Disc_The_Sky_Ablaze_Icon.webp en Documentacion/Interfaz/Set_Discos_Logo/
--   (renombrar manual al slug español 'firmamento_llameante.webp' — los logos los baja Daniel).
-- Re-evaluación (§2 paso 4): NO aplica — los discos farmeados no se persistieron (set NULL, display-only).

BEGIN TRANSACTION;

INSERT INTO disc_sets (nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc)
VALUES (
    'Firmamento llameante', 'The Sky Ablaze', 'Ether DMG', '+10%',
    'Si el portador es un agente Éter: Daño Crítico +30%. Al usar Ataque Especial EX o Definitiva: ATK +10% por 30s (refresca duración).'
);

INSERT INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT (SELECT id FROM disc_sets WHERE nombre = 'Firmamento llameante'),
       (SELECT id FROM disc_archetypes WHERE code = 'ATK_DPS'), 1;

COMMIT;

-- Smoke checks (cada uno debe mostrar expected_1):
SELECT COUNT(*) AS expected_1 FROM disc_sets WHERE nombre = 'Firmamento llameante';
SELECT COUNT(*) AS expected_1 FROM disc_sets
 WHERE nombre = 'Firmamento llameante' AND nombre_en = 'The Sky Ablaze'
   AND bonus_2p_stat = 'Ether DMG' AND bonus_2p_valor = '+10%';
SELECT COUNT(*) AS expected_1 FROM disc_set_archetype
 WHERE set_id = (SELECT id FROM disc_sets WHERE nombre = 'Firmamento llameante');

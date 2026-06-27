-- Onboarding de SET de discos nuevo: "Salón huracanado" (Wuthering Salon, ZZZ v3.x).
-- Sigue Documentacion/Onboarding_Nuevos_Assets.md §2.
--
-- DETECCIÓN (RF-04): el usuario equipó el set a Velina y la captura S17 lo leyó como
--   set DESCONOCIDO → "S17: set desconocido 'Salón huracanado' — no se persiste"
--   (sus discos no entraban a inventory_discs por faltar el set_id). QA 2026-06-26.
--
-- EFECTOS confirmados (RNF-02, fuente Game8 / Prydwen, verbatim):
--   2pc: "Wind DMG +10%".
--   4pc: "When the equipper uses an EX Special Attack, their Anomaly Proficiency increases
--         by 25 for 40s, stacking up to 2 times. Repeated triggers reset the duration. When
--         the equipper triggers Windswept, their DMG increases by 18% for 40s. Repeated
--         triggers reset the duration."
--   Es el set FIRMA de Velina (único PJ Viento/Anomalía que lo aprovecha hoy).
--
-- bonus_2p_stat usa la convención en inglés de la tabla ("Fire DMG"/"Ether DMG"…) → "Wind DMG".
-- ARQUETIPO (§2 paso 2, RF-06): ANOMALY (Maestría de Anomalía del 4pc) primario + ATK_DPS
--   secundario — mismo patrón que los otros sets de anomalía (set_id 25).
--
-- Logo: ya existe Drive_Disc_Wuthering_Salon_Icon.webp en Documentacion/Interfaz/Set_Discos_Logo/
--   (renombrar manual al slug español 'salon_huracanado.webp' — los logos los baja Daniel).
-- Re-evaluación (§2 paso 4): NO aplica — los discos no se persistieron (set NULL); Daniel los
--   re-captura navegándolos en S17 ahora que el set existe.

BEGIN TRANSACTION;

INSERT INTO disc_sets (nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc)
VALUES (
    'Salón huracanado', 'Wuthering Salon', 'Wind DMG', '+10%',
    'Al usar EX Special: Maestría de Anomalía +25 por 40s (apila x2, refresca duración). Al activar Windswept: DMG +18% por 40s (refresca duración).'
);

INSERT INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT (SELECT id FROM disc_sets WHERE nombre = 'Salón huracanado'),
       (SELECT id FROM disc_archetypes WHERE code = 'ANOMALY'), 1;
INSERT INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT (SELECT id FROM disc_sets WHERE nombre = 'Salón huracanado'),
       (SELECT id FROM disc_archetypes WHERE code = 'ATK_DPS'), 2;

COMMIT;

-- Smoke checks (cada uno debe mostrar expected_1):
SELECT COUNT(*) AS expected_1 FROM disc_sets WHERE nombre = 'Salón huracanado';
SELECT COUNT(*) AS expected_1 FROM disc_sets
 WHERE nombre = 'Salón huracanado' AND nombre_en = 'Wuthering Salon'
   AND bonus_2p_stat = 'Wind DMG' AND bonus_2p_valor = '+10%';
SELECT COUNT(*) AS expected_2 FROM disc_set_archetype
 WHERE set_id = (SELECT id FROM disc_sets WHERE nombre = 'Salón huracanado');

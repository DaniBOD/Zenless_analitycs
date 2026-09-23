-- =============================================================================
-- Tasa de Perforación como principal del slot 5 · 2026-09-23 · migración 41
-- =============================================================================
-- Capa de AJUSTES de Daniel (migración 40): el default de `disc_archetypes` no se toca.
--
-- ## De dónde sale (RNF-02)
--
-- Al correr el motor sobre todo el inventario (paso 7b) salió #213 (Voz Astral · slot 5 · Tasa de
-- Perforación · Nv 15) como DESCARTAR con puntaje 0: ningún arquetipo aceptaba ese principal,
-- salvo el del Armero. Daniel, 2026-09-23:
--
--   "tasa de perforación le sirve a atacantes como opción secundaria y de momento a los armeros,
--    claret se ve muy beneficiada de esto, los personajes supports/apoyo se pueden beneficiar por
--    eso lo guardé (rina por ejemplo) aunque es de nicho"
--
-- Entonces:
--   ATK_DPS    · mains_5 = default + Tasa de Perforación   ("opción secundaria")
--   SUPPORT_ER · mains_5 = default + Tasa de Perforación   ("de nicho", p. ej. Rina)
--   ARMORER_DEF · ya la acepta en el default. No se toca.
--
-- ⚠️ "Secundaria" y "de nicho" no se modelan todavía: el principal decide si el disco SIRVE
-- (R9), no cuánto vale frente a un Bono Daño. Queda anotado como tentativo en el registro de casos.
--
-- Un ajuste REEMPLAZA la lista entera (así los aplica `aplicar_ajustes_arquetipo`), por eso se
-- arma desde el default de hoy con `json_insert(... '$[#]' ...)` en vez de escribirla a mano.
-- =============================================================================

BEGIN TRANSACTION;

INSERT INTO ajustes_usuario_arquetipo (code, campo, valor_json)
SELECT code, 'mains_5', json_insert(mains_5, '$[#]', 'Tasa de Perforación')
  FROM disc_archetypes
 WHERE code IN ('ATK_DPS', 'SUPPORT_ER')
   AND mains_5 NOT LIKE '%Tasa de Perforación%';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- =============================================================================
-- SMOKE CHECKS
-- =============================================================================

-- El de HP_DISRUPT (mig 40) más los dos nuevos.
SELECT COUNT(*) AS expected_3 FROM ajustes_usuario_arquetipo;

-- Cada ajuste nuevo es el default + Tasa de Perforación, ni más ni menos.
SELECT COUNT(*) AS expected_2 FROM ajustes_usuario_arquetipo a
  JOIN disc_archetypes d ON d.code = a.code
 WHERE a.campo = 'mains_5' AND a.code IN ('ATK_DPS', 'SUPPORT_ER')
   AND json_array_length(a.valor_json) = json_array_length(d.mains_5) + 1
   AND EXISTS (SELECT 1 FROM json_each(a.valor_json) WHERE value = 'Tasa de Perforación');

-- Los DEFAULTS no se tocaron: ni ATK_DPS ni SUPPORT_ER la aceptan en disc_archetypes.
SELECT COUNT(*) AS expected_0 FROM disc_archetypes
 WHERE code IN ('ATK_DPS', 'SUPPORT_ER') AND mains_5 LIKE '%Tasa de Perforación%';
SELECT COUNT(*) AS expected_1 FROM disc_archetypes
 WHERE code = 'ARMORER_DEF' AND mains_5 LIKE '%Tasa de Perforación%';

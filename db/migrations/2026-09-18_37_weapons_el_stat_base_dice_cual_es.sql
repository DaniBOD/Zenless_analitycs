-- =============================================================================
-- El atributo principal de un W-Engine dice CUÁL es · 2026-09-18 · migración 37
-- =============================================================================
-- `weapons.atk_base` daba por sentado que el atributo principal de todo W-Engine es "Ataque
-- Base". El primer engine de Armero lo desmiente: `Fortuna felina` (Catty Luck, de Claret) dice
-- **"Defensa Base"** en la ficha, y el sistema guardaba ese DEF en una columna llamada ATK.
--
-- Es la MISMA forma que Claret ya había destapado tres veces (rol nuevo → arquetipo ATK_DPS,
-- afiladura → Recarga de Energía): una especialidad nueva trae vocabulario nuevo, y el sistema lo
-- rotula mal EN SILENCIO. Una columna cuyo nombre es a veces falso es una autoridad rota (B1):
-- quien la lee no tiene forma de saber en qué caso está.
--
-- QUÉ HACE
--   1. `atk_base` → `stat_base_valor`: el número, sin afirmar qué stat es.
--   2. `stat_base_tipo` nueva: 'ATK' | 'DEF' | NULL. La dice la ETIQUETA de la pantalla, que
--      `parser_weapon_s26` ahora LEE en vez de asumir (mismo commit).
--
-- EL BACKFILL, Y POR QUÉ NO ES INVENTAR (RNF-02)
--   Las 60 filas del catálogo son anteriores al patch 3.2 y NINGUNA es de especialidad 'Armero'
--   (verificado: `SELECT COUNT(*) ... WHERE tipo_especialidad='Armero'` = 0). Armero es la única
--   especialidad conocida con DEF base. Además hay verificación DIRECTA sobre 40 de ellas: las 40
--   capturas del corpus `Engine_vista_detallada_pj` dicen "Ataque Base" en pantalla.
--
--   Se marca 'ATK' SÓLO donde hay valor. Las 10 filas con `atk_base` NULL quedan con tipo NULL:
--   un rótulo sobre un número que no tenemos no afirma nada útil y rompería el invariante de
--   abajo. Invariante que el smoke check verifica: **el tipo está exactamente cuando está el
--   valor**.
--
-- NO se da de alta ningún engine acá. El alta de Catty Luck va en su propia migración, después
-- de esta, para que estrene el catálogo con el rótulo ya correcto.
--
-- Doc: Dev_IA/documentacion_cruda/2026-09/2026-09-18_FIX_El_atributo_principal_dice_cual_es.md
-- =============================================================================

BEGIN TRANSACTION;

ALTER TABLE weapons RENAME COLUMN atk_base TO stat_base_valor;
ALTER TABLE weapons ADD COLUMN stat_base_tipo TEXT;

UPDATE weapons SET stat_base_tipo = 'ATK' WHERE stat_base_valor IS NOT NULL;

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- =============================================================================
-- SMOKE CHECKS
-- =============================================================================

-- El catálogo sigue completo.
SELECT COUNT(*) AS expected_60 FROM weapons;

-- 50 con valor → 50 con tipo.
SELECT COUNT(*) AS expected_50 FROM weapons WHERE stat_base_valor IS NOT NULL;
SELECT COUNT(*) AS expected_50 FROM weapons WHERE stat_base_tipo = 'ATK';

-- Las 10 sin valor quedan sin tipo: no se rotula lo que no se midió.
SELECT COUNT(*) AS expected_10 FROM weapons WHERE stat_base_valor IS NULL;
SELECT COUNT(*) AS expected_10 FROM weapons WHERE stat_base_tipo IS NULL;

-- EL INVARIANTE: ninguna fila tiene uno sin el otro. Si esto deja de dar 0, la columna volvió a
-- poder mentir (un tipo sin número que lo respalde, o un número sin decir qué es).
SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE (stat_base_valor IS NULL) <> (stat_base_tipo IS NULL);

-- Todavía no hay ningún DEF: el único engine de Armero conocido no está en el catálogo (entra en
-- la migración siguiente). Si esto da > 0 antes de esa alta, algo rotuló de más.
SELECT COUNT(*) AS expected_0 FROM weapons WHERE stat_base_tipo = 'DEF';

-- Ninguna especialidad 'Armero' todavía.
SELECT COUNT(*) AS expected_0 FROM weapons WHERE tipo_especialidad = 'Armero';

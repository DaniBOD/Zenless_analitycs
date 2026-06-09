-- Migración 08 (2026-06-09) — Fix de datos: nombre completo del set "Puffer Electro".
--
-- Mismo caso que Balada (migr. 07): el catálogo guardaba el nombre INGLÉS
-- 'Puffer Electro' (set id 40) pero el OCR de S17 lee el nombre ES del juego
-- 'Tecno tetraodóntido' → no resolvía (Ye Shunguang slots 1/3, QA 2026-06-09).
-- Convención ES del juego: 'Tecno <familia>' (cf. id 48 'Tecno Pícido' = Woodpecker;
-- tetraodóntido = familia del pez globo / pufferfish). Tras esto el match es exacto.
--
-- Aplicar con RNF-01: backup previo + esta transacción + PRAGMA checks.

BEGIN TRANSACTION;

UPDATE disc_sets
   SET nombre = 'Tecno tetraodóntido'
 WHERE id = 40 AND nombre = 'Puffer Electro';

-- smoke check: expected_1 = 1
SELECT COUNT(*) AS expected_1
  FROM disc_sets
 WHERE id = 40 AND nombre = 'Tecno tetraodóntido';

-- no colisión con el otro 'Tecno' (id 48 'Tecno Pícido')
SELECT COUNT(*) AS expected_2
  FROM disc_sets
 WHERE nombre LIKE 'Tecno%';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

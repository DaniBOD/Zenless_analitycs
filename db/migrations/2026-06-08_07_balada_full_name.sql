-- Migración 07 (2026-06-08) — Fase 4 fix de datos: nombre completo de "Balada".
--
-- El catálogo guardaba el ALIAS corto 'Balada rama/espada' (set id 25), pero el OCR
-- de S17 lee el nombre completo del juego 'Balada de la rama y la espada' → no
-- resolvía (y el fuzzy difflib se abstiene por el 2º 'Balada' = id 51 'Balada de
-- aguas blancas', RNF-02). Se actualiza al nombre completo del juego; tras esto el
-- match es EXACTO y no colisiona con id 51.
--
-- Aplicar con RNF-01: backup previo + esta transacción + PRAGMA checks.

BEGIN TRANSACTION;

UPDATE disc_sets
   SET nombre = 'Balada de la rama y la espada'
 WHERE id = 25 AND nombre = 'Balada rama/espada';

-- smoke check: debe devolver expected_1 = 1
SELECT COUNT(*) AS expected_1
  FROM disc_sets
 WHERE id = 25 AND nombre = 'Balada de la rama y la espada';

-- y NO debe haber colisión de nombre con el otro 'Balada' (id 51)
SELECT COUNT(*) AS expected_2
  FROM disc_sets
 WHERE nombre LIKE 'Balada%';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

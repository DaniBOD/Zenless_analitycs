-- =============================================================================
-- 2026-09-13_33 · weapons: nombre_en de 3 armas del inventario que no lo tenían
-- =============================================================================
-- Sin `nombre_en`, `engine_icon_path` no puede encontrar el ícono (los archivos
-- se llaman `W-Engine_<nombre en inglés>.webp`) y la card de la vista en vivo
-- sale sin imagen. Eran 6 armas del inventario sin ícono:
--   · Sol exuvia y Ecos bulliciosos ya tienen `nombre_en`: les falta el ARCHIVO.
--   · Tetera esmeraldina recibe `nombre_en` acá, pero tampoco hay archivo.
--   · Inocencia sacrificada (id 62) queda FUERA: su nombre en inglés, Severed
--     Innocence, ya lo tiene la fila 22 "Serenidad cortada" (catálogo inicial,
--     0 copias en inventario). Son DOS filas de catálogo para la misma arma, y
--     ponerle el nombre_en a la 62 las dejaría con la misma clave. Unificarlas
--     es una decisión de datos aparte (qué fila sobrevive, a dónde apunta el
--     inventario), no completar un campo.
--
-- Equivalencias ES → EN verificadas contra al menos dos fuentes cada una (RNF-02):
--   Última cena           → Steam Oven         BitTopup es/63 = en/63, mismo pasivo
--                                               (energía → Impacto +2 % ×8); Game8
--   Inocencia sacrificada → Severed Innocence  BitTopup es/621 = en/621 = HoYoWiki
--                                               621; ATK 713 y Daño CRIT 48 % coinciden
--                                               con la fila
--   Caldero ardiente      → The Simmering Pot  Gachabase 13020 (lang=es) y la ficha
--                                               en español de genshin-builds; Game8
--   Tetera esmeraldina    → Ice-Jade Teapot    ficha en español de genshin-builds;
--                                               S + Impacto coincide con la fila; Game8
--
-- ⚠️ Hallazgo que esta migración NO corrige: las filas 5 (Última cena) y 13
-- (Caldero ardiente) tienen stat secundario y pasiva que NO coinciden con las
-- fuentes (p. ej. Última cena dice Impact 18 % y la fuente Recuperación de
-- energía 50 %). Se deja para una migración aparte, con su propia verificación.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE weapons SET nombre_en = 'Steam Oven'        WHERE id = 5  AND nombre = 'Última cena'           AND nombre_en IS NULL;
UPDATE weapons SET nombre_en = 'The Simmering Pot' WHERE id = 13 AND nombre = 'Caldero ardiente'      AND nombre_en IS NULL;
UPDATE weapons SET nombre_en = 'Ice-Jade Teapot'   WHERE id = 63 AND nombre = 'Tetera esmeraldina'    AND nombre_en IS NULL;

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_61 FROM weapons;
SELECT COUNT(*) AS expected_3 FROM weapons
 WHERE (id, nombre_en) IN (VALUES (5, 'Steam Oven'), (13, 'The Simmering Pot'),
                                  (63, 'Ice-Jade Teapot'));
-- Quedan sin nombre_en: las 3 que ya resolvían por el slug en español (ids 37, 42, 53),
-- "Sin arma" (45) y la 62, que queda fuera a propósito (ver el encabezado).
SELECT COUNT(*) AS expected_5 FROM weapons WHERE nombre_en IS NULL;
SELECT COUNT(*) AS expected_1 FROM weapons WHERE id = 62 AND nombre_en IS NULL;
-- Ningún nombre_en repetido.
SELECT COUNT(*) AS expected_0 FROM (SELECT nombre_en FROM weapons WHERE nombre_en IS NOT NULL
                                    GROUP BY nombre_en HAVING COUNT(*) > 1);
PRAGMA foreign_key_check;
PRAGMA integrity_check;

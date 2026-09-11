-- =============================================================================
-- 2026-09-11_28 · weapons: dos nombres estaban INCOMPLETOS, y un stat era falso
-- =============================================================================
-- El censo del 2026-09-08 no pudo casar dos armas que Daniel tiene equipadas.
-- La migración _27 las atribuyó a ruido del OCR y dejó abierta la otra hipótesis:
-- que el catálogo tuviera el nombre cortado. Las capturas de Daniel del
-- 2026-09-11 (Inventario_general_engines/Ejemplo_13 y _14, panel derecho de S30)
-- lo deciden a ojo y con `parse_weapon_s30`:
--
--     fila   catálogo decía            la pantalla dice
--     42     Cilindro neumático        Cilindro neumático de Bigger       (A, de Ben)
--      2     Templo a la granizada     Templo a la granizada estelífera   (S, de Miyabi)
--
-- El repo ya lo sabía y nadie lo cruzó: `test_parser_weapon_s26.py` fija
-- "Templo a la granizada estelífera" como verdad de tierra desde julio, y S29
-- escribe "Cilindro neumático de Bigger" en el diálogo de sustitución.
--
-- Medido: con el catálogo renombrado, `match_catalogo` resuelve las 4 lecturas,
-- incluidas las crudas con los espacios comidos ('Cilindroneumatico de Bigger',
-- 'Temploala granizadaestelifera'). Con el catálogo de hoy, ninguna.
--
-- ## Fila 42: el stat secundario era falso
--
-- Decía HP% 20%. La pantalla dice **Defensa 25.6 %** (a Nv 20/30). El NOMBRE del
-- stat es fijo por arma ⇒ se corrige a 'DEF%' (inglés, como el resto del
-- catálogo). El VALOR escala con el nivel y la lectura no es de Nv 60 ⇒ NULL:
-- el 20% era del stat equivocado, y el 25.6 es de nivel 20.
--
-- De dónde venía el dato falso: la fila nació como 'Pneumatic Cylinder', una
-- traducción inventada del nombre español (la _13 la borró a NULL), y la _11
-- dejó escrito que no se tocaba "sin evidencia". Es la primera evidencia.
--
-- Lo que NO se toca, a propósito:
--   atk_base = 500   sospechoso (ningún otro rango A del catálogo tiene 500 a
--                    Nv 60) pero la captura es de Nv 20 y no lo desmiente.
--   pasiva_*         mismo origen dudoso; el efecto de pantalla ("Dieciséis
--                    toneladas") no se extrae todavía.
--   nombre_en        la hipótesis obvia ('Bigger Cylinder') no se verificó en
--                    ninguna fuente autorizada ⇒ sigue NULL (regla del 07-28).
--
-- Ninguna tabla referencia las filas 2 ni 42 (weapon_id: 0 filas en agents,
-- inventory_weapons, weapon_passives_structured, weapon_evaluations), así que
-- el renombre no arrastra nada. Detalle: `audit/weapons_catalog_20260910.md`.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE weapons SET nombre = 'Cilindro neumático de Bigger',
                   stat_secundario = 'DEF%', stat_secundario_valor = NULL
 WHERE id = 42 AND nombre = 'Cilindro neumático';

UPDATE weapons SET nombre = 'Templo a la granizada estelífera'
 WHERE id = 2 AND nombre = 'Templo a la granizada';

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_61 FROM weapons;
SELECT COUNT(*) AS expected_2 FROM weapons
 WHERE (id = 42 AND nombre = 'Cilindro neumático de Bigger' AND stat_secundario = 'DEF%'
                AND stat_secundario_valor IS NULL AND atk_base = 500)
    OR (id = 2  AND nombre = 'Templo a la granizada estelífera' AND atk_base = 743
                AND stat_secundario = 'CRIT Rate' AND stat_secundario_valor = '24%');
-- Los nombres cortos no pueden sobrevivir: serían una segunda fila del mismo arma.
SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE nombre IN ('Cilindro neumático', 'Templo a la granizada');
PRAGMA foreign_key_check;
PRAGMA integrity_check;

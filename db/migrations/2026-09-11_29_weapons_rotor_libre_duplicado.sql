-- =============================================================================
-- 2026-09-11_29 · inventory_weapons: una fila libre de Rotor de cañón sobraba
-- =============================================================================
-- La pasada de las 14:05 escribió DOS Rotor de cañón libres idénticos (filas 49
-- y 50, Nv60 · P5, copia 0 y copia 1). Daniel tiene UNO solo libre y confirmó
-- que se quedó parado sobre la misma arma: la "segunda copia" fue una relectura
-- que el monitor ubicó en otra casilla de la grilla. La causa no está probada
-- (la pasada de las 16:21, ya con la posición en el log, no lo reprodujo: tres
-- lecturas en @(582,832) reusaron la fila 49). Ver el doc del censo de armas.
--
-- Baja LÓGICA, no DELETE: `descartado = 1` saca la fila de todo el sistema
-- (todos los finders la excluyen, incluido `find_free`) y es reversible. Se
-- descarta la 50 porque es la copia 1: la copia 0 es la que la pasada siguiente
-- reusa. Las equipadas del mismo modelo (Evelyn fila 12, Zhu Yuan fila 37) no
-- se tocan.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE inventory_weapons
   SET descartado = 1,
       notas = 'duplicado de la fila 49: relectura de la misma arma en otra casilla '
            || '(pasada 2026-09-11 14:05); Daniel tiene un solo Rotor de cañón libre'
 WHERE id = 50 AND equipado = 0 AND agente_asignado IS NULL AND descartado = 0
   AND weapon_id = (SELECT id FROM weapons WHERE nombre = 'Rotor de cañón');

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_55 FROM inventory_weapons;
SELECT COUNT(*) AS expected_1 FROM inventory_weapons WHERE id = 50 AND descartado = 1;
-- Queda UNA libre de Rotor de cañón a la vista, y es la 49.
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i JOIN weapons w ON w.id = i.weapon_id
 WHERE w.nombre = 'Rotor de cañón' AND i.equipado = 0 AND i.descartado = 0 AND i.id = 49;
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i JOIN weapons w ON w.id = i.weapon_id
 WHERE w.nombre = 'Rotor de cañón' AND i.equipado = 0 AND i.descartado = 0;
-- Las equipadas del mismo modelo, intactas.
SELECT COUNT(*) AS expected_2 FROM inventory_weapons
 WHERE id IN (12, 37) AND equipado = 1 AND descartado = 0;
PRAGMA foreign_key_check;
PRAGMA integrity_check;

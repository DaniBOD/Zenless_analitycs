-- =============================================================================
-- 2026-09-13_34 · weapons: Severed Innocence estaba dos veces en el catálogo
-- =============================================================================
-- Fila 22 "Serenidad cortada"     — catálogo inicial (mayo): especialidad, pasiva y
--                                   nombre_en cargados; 0 copias en el inventario.
-- Fila 62 "Inocencia sacrificada" — alta de la mig 27 desde lecturas de S30; sólo lo
--                                   leído en pantalla (ATK 713, Daño CRIT 48 %).
--
-- Son la misma arma: BitTopup es/621 = en/621 = HoYoWiki 621 (Severed Innocence),
-- ATK y stat idénticos. La mig 33 lo destapó al no poder ponerle el nombre_en a la
-- 62 sin repetir clave. Decisión de Daniel (2026-09-13): unificar.
--
-- Sobrevive la 22 (tiene los datos), con el NOMBRE de la 62: `weapons.nombre` es el
-- nombre español DE PANTALLA, y es el que carga el matcher del censo de armas
-- (`monitor.py`, `select nombre from weapons`). "Serenidad cortada" no aparece en el
-- juego: una traducción que ninguna lectura produjo.
--
-- Referencias medidas antes (todas las tablas, FK y columnas *weapon*): sólo
-- `inventory_weapons` fila 39 (Anby, Nv60 P1, equipada) apunta a la 62.
--
-- Orden obligado por `weapons.nombre UNIQUE`: re-apuntar → borrar la 62 → renombrar.
-- La 62 se BORRA y no se deja renombrada: un duplicado que nadie referencia sólo le
-- sumaría al matcher un segundo candidato para la misma arma.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE inventory_weapons SET weapon_id = 22
 WHERE id = 39 AND weapon_id = 62;

DELETE FROM weapons
 WHERE id = 62 AND nombre = 'Inocencia sacrificada'
   AND NOT EXISTS (SELECT 1 FROM inventory_weapons WHERE weapon_id = 62);

UPDATE weapons SET nombre = 'Inocencia sacrificada'
 WHERE id = 22 AND nombre = 'Serenidad cortada'
   AND NOT EXISTS (SELECT 1 FROM weapons WHERE nombre = 'Inocencia sacrificada');

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_60 FROM weapons;
SELECT COUNT(*) AS expected_1 FROM weapons
 WHERE id = 22 AND nombre = 'Inocencia sacrificada' AND nombre_en = 'Severed Innocence';
SELECT COUNT(*) AS expected_0 FROM weapons WHERE id = 62 OR nombre = 'Serenidad cortada';
SELECT COUNT(*) AS expected_1 FROM inventory_weapons
 WHERE id = 39 AND weapon_id = 22 AND equipado = 1 AND descartado = 0;
SELECT COUNT(*) AS expected_0 FROM inventory_weapons WHERE weapon_id = 62;
-- El inventario no ganó ni perdió filas.
SELECT COUNT(*) AS expected_56 FROM inventory_weapons WHERE descartado = 0;
SELECT COUNT(*) AS expected_0 FROM (SELECT nombre_en FROM weapons WHERE nombre_en IS NOT NULL
                                    GROUP BY nombre_en HAVING COUNT(*) > 1);
PRAGMA foreign_key_check;
PRAGMA integrity_check;

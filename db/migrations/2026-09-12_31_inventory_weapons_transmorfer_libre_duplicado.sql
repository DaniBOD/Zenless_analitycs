-- =============================================================================
-- 2026-09-12_31 · inventory_weapons: la segunda 'Transmorfer original' libre
--                 era la misma vista después de un SCROLL
-- =============================================================================
-- Daniel confirmó que tiene UNA sola libre (Nv 0/10, P1). La fila 57 entró en la
-- pasada de las 02:56 como "copia 1" de esa clave.
--
-- ## Esta vez la causa quedó PROBADA, y es el scroll
--
-- El log ya trae la posición de la selección (commit `696a54c`), y ahí está:
--
--     02:54:04  Transmorfer original · Nv 0/10 · P1 · LIBRE · @(402,1064)  → fila 55
--     02:56:31  Transmorfer original · Nv 0/10 · P1 · LIBRE · @(1484,680)  → fila 57 (copia 1)
--
-- Las filas de la grilla caen en y ≈ 367, 600, 831 y 1064. **680 no es el centro
-- de ninguna**: la grilla estaba scrolleada, así que el mismo tile apareció en
-- otro lugar y el ordinal de copia —que sólo sabe de posiciones— lo leyó como una
-- pieza distinta. Es el límite que el reporte del censo ya declara ("volver a una
-- copia ya vista después de un scroll la cuenta otra vez"), ahora con evidencia.
--
-- Es el mismo patrón que la fila 50 (Rotor de cañón, mig `_29`), que se corrigió
-- sin poder probar la causa porque el log todavía no traía la posición.
--
-- Baja LÓGICA, no DELETE: `descartado = 1` la saca de todos los finders (incluido
-- `find_free`) y es reversible. Se descarta la 57 —la copia 1— porque la 55 es la
-- que la próxima pasada reusa.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE inventory_weapons
   SET descartado = 1,
       notas = 'duplicado de la fila 55: la misma arma vista tras un scroll, en @(1484,680) '
            || 'contra @(402,1064) — la y no cae en ningún centro de fila. Daniel tiene una '
            || 'sola Transmorfer original libre (pasada 2026-09-12 02:56)'
 WHERE id = 57 AND equipado = 0 AND agente_asignado IS NULL AND descartado = 0
   AND weapon_id = (SELECT id FROM weapons WHERE nombre = 'Transmorfer original');

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
-- 57 filas escritas, una dada de baja ⇒ 56 activas, que es lo que dice el contador.
SELECT COUNT(*) AS expected_56 FROM inventory_weapons WHERE descartado = 0;
SELECT COUNT(*) AS expected_1 FROM inventory_weapons WHERE id = 57 AND descartado = 1;
-- Queda UNA Transmorfer original libre a la vista, y es la 55.
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i JOIN weapons w ON w.id = i.weapon_id
 WHERE w.nombre = 'Transmorfer original' AND i.equipado = 0 AND i.descartado = 0 AND i.id = 55;
-- La de Zhao (equipada, Nv 60) no se toca.
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i JOIN weapons w ON w.id = i.weapon_id
  JOIN agents a ON a.id = i.agente_asignado
 WHERE w.nombre = 'Transmorfer original' AND a.nombre = 'Zhao' AND i.equipado = 1
   AND i.descartado = 0;
-- Y la Réplica de Billy, que era el hueco que cerraba el censo.
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i JOIN weapons w ON w.id = i.weapon_id
  JOIN agents a ON a.id = i.agente_asignado
 WHERE w.nombre = 'Réplica motor estelar' AND a.nombre = 'Billy' AND i.descartado = 0;
PRAGMA foreign_key_check;
PRAGMA integrity_check;

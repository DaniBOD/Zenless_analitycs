-- =============================================================================
-- 2026-09-01_21 · discos: borrar la fila duplicada del slot 5 de Yixuan
-- =============================================================================
-- El 2026-09-01, al abrir a Yixuan en S17 para confirmar una hipótesis del cierre
-- del censo, la persistencia INSERTÓ una fila nueva (id=384) para un disco que ya
-- estaba en la DB como id=127, guardado sin dueño y marcado
-- `dueno_no_identificado_2026-08-30`. El inventario pasó de 383 a 384.
--
-- Las dos filas son el MISMO disco físico: coinciden en los doce campos de
-- identidad — set (49, Fábula Yunkui), slot (5), main (Bono Daño Éter 30.0),
-- nivel (15) y los cuatro substats con los mismos valores Y los mismos rolls:
--
--     Perforación           9.0   rolls=0
--     Daño Crítico         14.4   rolls=2
--     Maestría de Anomalía  9.0   rolls=0
--     Prob. Crítica         7.2   rolls=2
--
-- SE CONSERVA LA 127, no la 384. La 127 tiene la `fecha_obtencion` real
-- (2026-08-31 02:51, cuando el censo la vio por primera vez); la 384 tiene la de
-- hoy, que es cuándo se creó el duplicado y no cuándo apareció el disco.
--
-- La 127 queda como está: sin dueño y con su marca. NO se le escribe el dueño
-- acá a mano. El bug de fondo se arregló en el commit a9a6dcd —las filas marcadas
-- ahora se ADOPTAN en vez de duplicarse— así que la próxima vez que se abra a
-- Yixuan la app le pone el dueño sola, leyéndolo de la pantalla. Un dato que
-- puede venir de la observación no se inventa en una migración (RNF-02).
--
-- Ninguna otra tabla referencia estas filas: `inventory_disc_evaluations` es la
-- única con FK a `inventory_discs(id)`, y ninguna de las dos tiene registros ahí.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

-- Antes: las dos filas, para que quede en el log de la corrida qué se borró.
SELECT 'ANTES' AS momento, id, set_id, slot, main_stat, main_valor, nivel,
       agente_asignado, equipado, fecha_obtencion, notas
  FROM inventory_discs WHERE id IN (127, 384);

BEGIN TRANSACTION;

-- Guarda: sólo borra si la 127 sigue existiendo. Si alguien la borró antes, esto
-- no matchea nada y la 384 sobrevive — mejor un duplicado que ningún disco.
DELETE FROM inventory_discs
 WHERE id = 384
   AND EXISTS (SELECT 1 FROM inventory_discs WHERE id = 127);

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM inventory_discs WHERE id = 384;
SELECT COUNT(*) AS expected_1 FROM inventory_discs WHERE id = 127;
SELECT COUNT(*) AS expected_383 FROM inventory_discs;
SELECT COUNT(*) AS expected_5 FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%';
-- Yixuan vuelve a 5/6 slots equipados: el 5 se lo pone la app al volver a verlo.
SELECT COUNT(DISTINCT slot) AS expected_5 FROM inventory_discs d
  JOIN agents a ON a.id = d.agente_asignado
 WHERE a.nombre = 'Yixuan' AND d.equipado = 1;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

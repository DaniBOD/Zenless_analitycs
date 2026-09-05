-- =============================================================================
-- 2026-09-05_23 · discos: borrar las 3 filas marcadas que ningún PJ puede tener
-- =============================================================================
-- Tres filas guardadas como "alguien lo tiene y no pude leer quién"
-- (`dueno_no_identificado_2026-08-30`) que en realidad son la MISMA captura que
-- una fila con dueño, duplicada por un reinicio de la captura a mitad del censo.
--
--     id=120  Fábula Yunkui  slot 3  DEF        gemela de id=121 -> Manato
--     id=266  Tecno Pícido   slot 6  Impacto    gemela de id=267 -> Anby
--     id=301  Blues Libre    slot 2  ATK        gemela de id=302 -> Soukaku
--
-- Las gemelas son byte a byte idénticas: set, slot, main, valor, nivel y los
-- cuatro substats con los mismos valores Y los mismos rolls.
--
-- ## Las tres evidencias
--
-- 1) EL MECANISMO. Las tres se escribieron entre 4 y 7 segundos antes de un
--    reinicio del monitor (22:11:43, 23:06:40, 23:15:46 hora local; la columna
--    `fecha_obtencion` está en UTC, +4 h). El censo tuvo 22 reinicios: cuando el
--    reconocimiento fallaba, Daniel detenía y reiniciaba la captura. En la pasada
--    nueva el mismo disco SÍ se nombraba, y como una fila marcada no se podía
--    adoptar (bug arreglado en a9a6dcd), se insertaba una segunda.
--
-- 2) NO TIENEN DUEÑO POSIBLE. Tras verificar en pantalla el 2026-09-05, los slots
--    2, 3 y 6 están completos en los 51 PJs; los únicos huecos son de slot 1, 4 y
--    5. Una fila marcada AFIRMA que alguien la tiene equipada, y no queda nadie
--    que pueda. La afirmación es falsa — y es justamente la lectura que falló.
--
-- 3) LAS GEMELAS ESTÁN CONFIRMADAS. Manato slot 3, Anby slot 6 y Soukaku slot 2
--    se miraron en pantalla ese mismo día: las tres filas con dueño son las que
--    el juego muestra (`s17_update`, sin altas).
--
-- ## Lo que esto NO cubre
--
-- Quedaría la posibilidad de que alguno de los ~46 PJs que no se miraron tenga
-- mal atribuido su slot 2, 3 o 6, y que una de estas filas sea suya. Las tres
-- evidencias apuntan al mismo lado, pero no es una prueba formal. Por eso hay
-- backup: si aparece un PJ al que le falte uno de estos discos, se restaura.
--
-- ## Lo que NO se toca
--
--   · `id=171` (Balada slot 4) sigue marcado: N.º 0: Anby tiene hueco justo ahí,
--     así que su afirmación de "alguien lo tiene" es consistente. Se resuelve
--     mirándolo en pantalla — con la adopción arreglada, se reconcilia solo.
--   · `id=93` (Monarca slot 3, libre) es idéntico al de Ju Fufu (`id=385`) y NO
--     es el mismo caso: una fila LIBRE afirma "no lo tiene nadie", y que otro PJ
--     tenga uno igual no la contradice. Dos discos idénticos pueden coexistir.
--
-- Ninguna otra tabla referencia estas filas: `inventory_disc_evaluations` es la
-- única con FK a `inventory_discs(id)`, y las tres tienen 0 registros ahí.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

-- Antes: las tres filas y sus gemelas, para que quede en el log qué se borró.
SELECT 'ANTES' AS momento, d.id, d.slot, s.nombre AS conjunto, d.main_stat,
       d.nivel, a.nombre AS dueno, d.equipado, d.fecha_obtencion, d.notas
  FROM inventory_discs d
  LEFT JOIN disc_sets s ON s.id = d.set_id
  LEFT JOIN agents a ON a.id = d.agente_asignado
 WHERE d.id IN (120, 121, 266, 267, 301, 302)
 ORDER BY d.id;

BEGIN TRANSACTION;

-- Guardas: sólo borra la fila marcada, sin dueño, y sólo si su gemela con dueño
-- sigue existiendo. Si alguien tocó la gemela antes, esto no matchea nada — mejor
-- un duplicado que quedarse sin el disco.
DELETE FROM inventory_discs
 WHERE id = 120 AND agente_asignado IS NULL
   AND notas LIKE '%dueno_no_identificado%'
   AND EXISTS (SELECT 1 FROM inventory_discs WHERE id = 121 AND agente_asignado IS NOT NULL);

DELETE FROM inventory_discs
 WHERE id = 266 AND agente_asignado IS NULL
   AND notas LIKE '%dueno_no_identificado%'
   AND EXISTS (SELECT 1 FROM inventory_discs WHERE id = 267 AND agente_asignado IS NOT NULL);

DELETE FROM inventory_discs
 WHERE id = 301 AND agente_asignado IS NULL
   AND notas LIKE '%dueno_no_identificado%'
   AND EXISTS (SELECT 1 FROM inventory_discs WHERE id = 302 AND agente_asignado IS NOT NULL);

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM inventory_discs WHERE id IN (120, 266, 301);
-- Las tres gemelas quedan, con su dueño y equipadas.
SELECT COUNT(*) AS expected_3 FROM inventory_discs
 WHERE id IN (121, 267, 302) AND agente_asignado IS NOT NULL AND equipado = 1;
-- No queda ninguna fila marcada en un slot que esté completo en todo el roster.
SELECT COUNT(*) AS expected_0 FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%' AND slot IN (2, 3, 6);
-- `id=171` sigue marcado: su hueco (N.º 0: Anby slot 4) existe. Si ya se adoptó
-- al mirarlo en pantalla, este check da 0 y también está bien — ver nota abajo.
SELECT COUNT(*) AS marcados_restantes FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%';
SELECT COUNT(*) AS expected_382 FROM inventory_discs;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

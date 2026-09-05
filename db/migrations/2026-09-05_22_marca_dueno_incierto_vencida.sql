-- =============================================================================
-- 2026-09-05_22 · discos: sacar la marca de dueño incierto que quedó vencida
-- =============================================================================
-- El 2026-09-05 la app adoptó el disco `id=127` al abrir a Yixuan en S17: le puso
-- el dueño (agente_asignado=31, equipado=1) sin crear una fila nueva, que es lo
-- que se arregló en a9a6dcd. Pero la fila se quedó con su nota:
--
--     notas = 'dueno_no_identificado_2026-08-30'
--
-- Esa marca AFIRMA "alguien lo tiene y no pude leer quién", y dejó de ser cierta
-- en el momento en que se leyó el dueño. No es peligrosa —la adopción exige
-- `agente_asignado IS NULL`, así que la fila no se puede volver a adoptar— pero
-- envenena el contador de inciertos, que es justo el número que dice cuántos
-- discos quedan por reconciliar: decía 5 cuando eran 4, y no iba a bajar nunca.
--
-- El código ya no la deja vencida (`limpiar_marca_dueno_incierto`, llamada al
-- adoptar). Esto limpia la única fila que quedó en ese estado — verificado: es la
-- única con la marca Y con dueño.
--
-- Se saca el TOKEN, no el campo: `notas` es un campo que otros flujos concatenan
-- con ' | ' (`no_visto_en_censo_<fecha>`, `declarado_por_usuario_<fecha>`), y
-- vaciarlo se llevaría puesto lo que dijo otro. Acá la marca está sola, así que
-- el campo queda en NULL — pero la condición del UPDATE es por token igual.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

-- Antes: qué filas están en este estado (marca vencida = con marca Y con dueño).
SELECT 'ANTES' AS momento, id, slot, agente_asignado, equipado, notas
  FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%' AND agente_asignado IS NOT NULL;

BEGIN TRANSACTION;

-- Sólo las que YA tienen dueño: una fila sin dueño y marcada sigue siendo un
-- incierto legítimo y no se toca.
UPDATE inventory_discs
   SET notas = NULL
 WHERE notas = 'dueno_no_identificado_2026-08-30'
   AND agente_asignado IS NOT NULL;

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%' AND agente_asignado IS NOT NULL;
SELECT COUNT(*) AS expected_4 FROM inventory_discs
 WHERE notas LIKE '%dueno_no_identificado%';
-- La 127 conserva dueño, equipado y su fecha de obtención original.
SELECT COUNT(*) AS expected_1 FROM inventory_discs
 WHERE id = 127 AND agente_asignado = 31 AND equipado = 1
   AND fecha_obtencion = '2026-08-31 02:51:28' AND notas IS NULL;
SELECT COUNT(*) AS expected_383 FROM inventory_discs;
SELECT COUNT(DISTINCT slot) AS expected_6 FROM inventory_discs d
  JOIN agents a ON a.id = d.agente_asignado
 WHERE a.nombre = 'Yixuan' AND d.equipado = 1;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

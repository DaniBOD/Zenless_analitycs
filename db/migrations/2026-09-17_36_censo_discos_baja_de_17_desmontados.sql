-- =============================================================================
-- Baja de 17 discos desmontados · 2026-09-17 · migración 36
-- =============================================================================
-- Cierre de la Fase 4 (censo completo de discos por S9). Estas 17 filas están en
-- `inventory_discs` y NO aparecieron en la pasada del 2026-09-17: son discos que Daniel
-- desmontó y que la DB seguía contando como inventario vivo.
--
-- POR QUÉ ACÁ SÍ SE PUEDE BORRAR POR AUSENCIA (y por qué antes no)
--
--   La regla del proyecto es que la ausencia NO prueba la inexistencia (B2): que el sistema no
--   vea algo puede significar que no lo recorriste. Lo que habilita la baja es el CRITERIO DE
--   COMPLETITUD, y esta pasada es la primera que lo cumple:
--
--     · el contador del header de S9 —la autoridad del conteo— leyó 380;
--     · el censo registró 380/380 con 0 sin resolver;
--     · y la persistencia tocó 380 FILAS DISTINTAS.
--
--   Dos caminos independientes (contar discos en pantalla y contar filas en la DB) dieron el
--   mismo número, o sea que hubo biyección: cada disco de la pantalla encontró su fila y ninguna
--   fila se usó dos veces. Si se tocaron tantas filas como discos hay, lo que quedó afuera no
--   está en la pantalla.
--
--   El censo del 2026-08-30 NO podía llegar a esto: calculaba identidad por su cuenta y el OCR
--   leía el nombre del set distinto entre pasadas, así que el total era inalcanzable por diseño
--   (~317 de 339 previstos). La pasada cierra recién desde que la identidad es la FILA.
--
-- UN CRUCE QUE NO SE BUSCÓ Y SALIÓ SOLO
--   El censo contó 69 discos libres; la DB tiene 86. 86 − 69 = 17, exactamente estas filas.
--
-- SOBRE LOS REPETIDOS
--   Entre los 17 hay 4 filas idénticas (Aria radiante slot 2 ATK Nv0) y 3 idénticas (Melodía de
--   Faetón slot 3 DEF Nv0). Preguntar CUÁL borrar no tiene sentido: son indistinguibles en todo
--   campo observable, así que borrar unas u otras es la misma operación. Lo que la evidencia
--   sostiene es el NÚMERO, y es lo que se aplica.
--
-- VERIFICADO ANTES DE ESCRIBIR
--   · las 17 existen, están vigentes (descartado=0), LIBRES (agente_asignado IS NULL) y
--     no equipadas (equipado=0) — ninguna le saca un disco a un PJ;
--   · `inventory_disc_evaluations` (única FK a inventory_discs) no referencia ninguna.
--
-- REVERSIÓN: backup previo que deja `apply_migration.py`, más el snapshot del censo
--   `audit/danibod_zzz_v2.censo_discos_20260917.db`.
--
-- Evidencia completa: audit/censo_discos_20260917.md
-- =============================================================================

BEGIN TRANSACTION;

-- Guarda de seguridad: si alguna de las 17 dejó de ser libre/vigente entre la verificación y la
-- aplicación, el filtro la deja afuera en vez de borrarla igual. Preferimos borrar de menos.
DELETE FROM inventory_discs
 WHERE id IN (25, 143, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 370, 371, 372, 373, 395)
   AND agente_asignado IS NULL
   AND (equipado = 0 OR equipado IS NULL)
   AND descartado = 0;

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- =============================================================================
-- SMOKE CHECKS
-- =============================================================================

-- Ninguna de las 17 sobrevive.
SELECT COUNT(*) AS expected_0 FROM inventory_discs
 WHERE id IN (25, 143, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 370, 371, 372, 373, 395);

-- 397 vigentes − 17 = 380, que es lo que dice el contador de la pantalla.
SELECT COUNT(*) AS expected_380 FROM inventory_discs WHERE descartado = 0;

-- Los libres pasan de 86 a 69: el mismo número que registró el censo.
SELECT COUNT(*) AS expected_69 FROM inventory_discs
 WHERE descartado = 0 AND agente_asignado IS NULL;

-- Los discos CON dueño no se tocaron.
SELECT COUNT(*) AS expected_311 FROM inventory_discs
 WHERE descartado = 0 AND agente_asignado IS NOT NULL;

-- Nadie perdió un slot: 51 PJs siguen con los 6 (el único incompleto es Nekomata, 5/6).
SELECT COUNT(*) AS expected_51 FROM (
  SELECT agente_asignado FROM inventory_discs
   WHERE descartado = 0 AND agente_asignado IS NOT NULL
   GROUP BY agente_asignado HAVING COUNT(DISTINCT slot) = 6);

-- Nivel 0 vigentes: 12 = los 10 originales que se volvieron a ver y SIGUEN en Nivel 0 (genuinos)
-- + 2 que se farmearon durante la pasada misma. No son 10: el inventario se movió mientras se
-- lo censaba, que es exactamente lo que el re-anclaje del contador está para tolerar.
SELECT COUNT(*) AS expected_12 FROM inventory_discs
 WHERE descartado = 0 AND nivel = 0;

-- Total de filas: 397 + 6 descartadas históricas − 17.
SELECT COUNT(*) AS expected_386 FROM inventory_discs;

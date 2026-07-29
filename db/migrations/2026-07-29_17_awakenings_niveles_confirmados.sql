-- =============================================================================
-- Despertares: niveles CONFIRMADOS por DaniBOD · 2026-07-29
-- =============================================================================
-- Cierra los 5 `nivel IS NULL` que dejó la migración 16. DaniBOD confirmó in-game
-- (RNF-02) el estado de su tienda Silueta Potencial:
--
--   6/6          : Jane Doe, N.º 0 Anby, Burnice, Grace, Rina, Ellen Joe, Lycaon
--   1/6          : N.º 11
--   sin mejoras  : Nekomata, Harumasa
--
-- MAPEO DE NOMBRES — los del reporte no son los de la DB:
--   "Jane Doe"  -> agents.nombre = 'Jane'   (id 38)
--   "Ellen Joe" -> agents.nombre = 'Ellen'  (id 44)
--   "N°0 Anby"  -> agents.nombre = 'N.º 0: Anby' (id 30)
--   NO se renombra nada: el resolver de assets y el latch de identidad keyean
--   por `agents.nombre` (hay overrides tipo 'Jane' -> Jane-Doe-*.webp). Tocar el
--   nombre rompería la cosecha de badges.
--
-- QUÉ CAMBIA (solo las 5 filas de la mig 16; ver abajo por qué el resto no)
--   Jane      (38) : NULL -> nivel 6, activo 1, pending_capture
--   Rina      (42) : NULL -> nivel 6, activo 1, pending_capture
--   N.º 11    (6)  : NULL -> nivel 1, activo 1, pending_capture   <- PARCIAL
--   Nekomata  (45) : NULL -> nivel 0, activo 0, placeholder
--   Harumasa  (16) : NULL -> nivel 0, activo 0, placeholder
--
-- QUÉ **NO** CAMBIA
--   Lycaon (3), N.º 0: Anby (30), Grace (41) y Ellen (44) ya estaban en nivel 6 —
--   el reporte de DaniBOD los CONFIRMA, así que no hay nada que corregir.
--   Burnice (1) ya está en nivel 6 y es la única fila con texto de efecto real
--   ('stat_boost'): no se toca para no degradarla.
--
-- NEKOMATA Y HARUMASA VAN A 'placeholder', NO A 'pending_capture'
--   Con 0 niveles comprados no hay texto que capturar todavía. Se alinean con las
--   otras filas "no lo tiene" (Cissia, Velina, Pyrois, Remielle Dan). La
--   diferencia respecto de esas —que para Nekomata/Harumasa el despertar SÍ
--   existe y es comprable desde v3.1— queda registrada en `descripcion`, para que
--   una sesión futura sepa que acá sí hay algo que capturar si DaniBOD compra.
--
-- N.º 11 QUEDA EN 1/6 — ojo al capturar
--   El despertar es progresivo: a nivel 1 solo está activa una parte del efecto.
--   Cuando se capture el texto hay que anotar A QUÉ NIVEL corresponde, o el
--   scoring va a asumir el efecto completo.
--
-- ALCANCE: sigue sin cargarse NINGÚN texto de efecto. Esta migración solo fija
--   los niveles. La deuda de texto queda en 7 filas (las de nivel > 0 sin efecto
--   real). Se cargan con capturas más adelante.
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App cerrada.
--   Runner: python app/scripts/qa/apply_migration.py <este archivo>
-- =============================================================================

BEGIN TRANSACTION;

-- 1. Despertar COMPLETO (6/6): Jane y Rina.
UPDATE agent_awakenings
   SET nivel = 6,
       activo = 1,
       nombre = '[Despertar nv6 — pendiente captura textual]',
       descripcion = 'Despertar completo 6/6 confirmado por DaniBOD in-game 2026-07-29. Texto del efecto PENDIENTE de captura (tienda Silueta Potencial). Al capturar: completar nombre + descripcion + tipo_efecto real.'
 WHERE agente_id IN (SELECT id FROM agents WHERE nombre IN ('Jane', 'Rina'))
   AND nivel IS NULL;

-- 2. Despertar PARCIAL (1/6): N.º 11.
UPDATE agent_awakenings
   SET nivel = 1,
       activo = 1,
       nombre = '[Despertar nv1 de 6 — pendiente captura textual]',
       descripcion = 'Despertar PARCIAL 1/6 confirmado por DaniBOD in-game 2026-07-29 ("Limite x1"). Texto PENDIENTE. OJO: el despertar es progresivo, a nivel 1 solo esta activa parte del efecto — al capturar, anotar A QUE NIVEL corresponde el texto o el scoring va a asumir el efecto completo.'
 WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'N.º 11')
   AND nivel IS NULL;

-- 3. SIN mejoras (0/6): Nekomata y Harumasa.
UPDATE agent_awakenings
   SET nivel = 0,
       activo = 0,
       nombre = 'Sin awakening',
       tipo_efecto = 'placeholder',
       descripcion = 'Sin niveles comprados al 2026-07-29 (confirmado por DaniBOD). A diferencia de los otros placeholder del roster, el despertar de este PJ SI existe y es comprable desde v3.1 — o sea que aca si hay algo que capturar el dia que DaniBOD lo compre.'
 WHERE agente_id IN (SELECT id FROM agents WHERE nombre IN ('Nekomata', 'Harumasa'))
   AND nivel IS NULL;

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada SELECT devuelve una columna `expected_N` que DEBE valer N.
SELECT 'ya no queda ningun nivel NULL (=0)' AS check_name, COUNT(*) AS expected_0
  FROM agent_awakenings WHERE nivel IS NULL;
SELECT 'total agent_awakenings (=15)'       AS check_name, COUNT(*) AS expected_15
  FROM agent_awakenings;
SELECT 'despertares en 6/6 (=7)'            AS check_name, COUNT(*) AS expected_7
  FROM agent_awakenings WHERE nivel = 6;
SELECT 'N.º 11 en 1/6'                      AS check_name, aw.nivel AS expected_1
  FROM agent_awakenings aw JOIN agents a ON a.id = aw.agente_id WHERE a.nombre = 'N.º 11';
SELECT 'Nekomata + Harumasa en 0 (=2)'      AS check_name, COUNT(*) AS expected_2
  FROM agent_awakenings aw JOIN agents a ON a.id = aw.agente_id
 WHERE a.nombre IN ('Nekomata', 'Harumasa') AND aw.nivel = 0 AND aw.activo = 0;
SELECT 'Burnice intacta con texto real'     AS check_name, tipo_efecto AS expected_stat_boost
  FROM agent_awakenings WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'Burnice');
SELECT 'activos = los de nivel > 0 (=8)'    AS check_name, COUNT(*) AS expected_8
  FROM agent_awakenings WHERE activo = 1 AND nivel > 0;
SELECT 'incoherentes activo vs nivel (=0)'  AS check_name, COUNT(*) AS expected_0
  FROM agent_awakenings WHERE (activo = 1 AND (nivel IS NULL OR nivel = 0))
                           OR (activo = 0 AND nivel > 0);
SELECT 'deuda de texto restante (=7)'       AS check_name, COUNT(*) AS expected_7
  FROM agent_awakenings WHERE tipo_efecto = 'pending_capture';
SELECT 'sin agentes con 2 despertares (=0)' AS check_name, COUNT(*) AS expected_0
  FROM (SELECT agente_id FROM agent_awakenings GROUP BY agente_id HAVING COUNT(*) > 1);

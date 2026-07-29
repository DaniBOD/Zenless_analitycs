-- =============================================================================
-- Despertares (Silueta Potencial) nuevos del patch v3.1 · 2026-07-29
-- =============================================================================
-- DaniBOD reportó que salieron despertares nuevos para: N.º 11, Harumasa,
-- Nekomata, Rina, Jane, Lycaon, N.º 0: Anby y Grace ("creo que esos eran").
--
-- De esos 8, TRES ya tenían fila (Lycaon id 3, N.º 0: Anby id 30, Grace id 41),
-- cargadas en nivel 6 / pending_capture. **No se tocan**: sobrescribir datos ya
-- confirmados a partir de un "creo que" es justo lo que prohíbe RNF-02. Si
-- efectivamente cambiaron, se corrige cuando haya captura.
--
-- Esta migración inserta las CINCO que faltaban:
--   N.º 11 (6) · Harumasa (16) · Nekomata (45) · Rina (42) · Jane (38)
--
-- POR QUÉ `nivel` VA EN NULL
--   El modelo de la tabla venía usando dos estados:
--     · nivel=6, activo=1, 'pending_capture'  -> lo tiene full, falta el texto
--     · nivel=0, activo=0, 'placeholder'      -> no tiene despertar
--   Ninguno describe la situación real de estas cinco: el despertar EXISTE en el
--   juego, pero **no está confirmado si DaniBOD lo compró ni a qué nivel**.
--   Inventar un 0 o un 6 sería afirmar algo que no sabemos, así que va NULL +
--   flag tentativo (RNF-02, CLAUDE.md §2). Precedente directo: estas dos ya se
--   habían dejado deliberadamente sin insertar por esto mismo — la nota de
--   project-context-IA decía "Harumasa y N.°11 sin insertar hasta confirmar nivel".
--
-- POR QUÉ `activo=0`
--   Conservador (CLAUDE.md §5): mientras no se confirme la compra, el scoring no
--   debe asumir un buff que puede no existir. Se pasa a 1 al capturar.
--
-- ALCANCE: esto NO carga el efecto. `descripcion` queda como marcador de deuda.
--   El texto del despertar solo se obtiene in-game (tienda Silueta Potencial) y
--   se cargará con capturas más adelante — decisión DaniBOD 2026-07-29. Sin ese
--   texto la fila sirve para inventariar la deuda, no para alimentar scoring.
--
-- Nota: el sistema de despertares NO tiene captura implementada (cero
--   referencias a awakening/silueta/despertar en app/core). La carga futura es
--   manual desde screenshots.
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App cerrada.
--   Runner: python app/scripts/qa/apply_migration.py <este archivo>
-- =============================================================================

BEGIN TRANSACTION;

INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, NULL,
       '[Despertar v3.1 — pendiente captura]',
       'Despertar anunciado como nuevo en v3.1 (reporte DaniBOD 2026-07-29). NIVEL SIN CONFIRMAR -> NULL a proposito (RNF-02): no se sabe si esta comprado ni a que nivel. activo=0 conservador hasta confirmar. Capturar in-game en la tienda Silueta Potencial: "Agotado" = nv6, "Limite xN" = parcial. Al capturar, completar nivel + nombre + descripcion + tipo_efecto y poner activo=1.',
       'pending_capture', 0, 'v3.1'
  FROM agents
 WHERE nombre IN ('N.º 11', 'Harumasa', 'Nekomata', 'Rina', 'Jane')
   AND id NOT IN (SELECT agente_id FROM agent_awakenings);

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada SELECT devuelve una columna `expected_N` que DEBE valer N.
SELECT 'filas nuevas v3.1 (=5)'      AS check_name, COUNT(*) AS expected_5
  FROM agent_awakenings WHERE version_juego='v3.1' AND tipo_efecto='pending_capture';
SELECT 'total agent_awakenings (=15)' AS check_name, COUNT(*) AS expected_15
  FROM agent_awakenings;
SELECT 'los 5 PJs quedaron cubiertos (=5)' AS check_name, COUNT(*) AS expected_5
  FROM agent_awakenings aw JOIN agents a ON a.id=aw.agente_id
 WHERE a.nombre IN ('N.º 11', 'Harumasa', 'Nekomata', 'Rina', 'Jane');
SELECT 'nivel en NULL en las nuevas (=5)'  AS check_name, COUNT(*) AS expected_5
  FROM agent_awakenings WHERE version_juego='v3.1' AND nivel IS NULL;
SELECT 'ninguna nueva quedo activa (=0)'   AS check_name, COUNT(*) AS expected_0
  FROM agent_awakenings WHERE version_juego='v3.1' AND activo<>0;
SELECT 'las 3 viejas siguen en nv6 (=3)'   AS check_name, COUNT(*) AS expected_3
  FROM agent_awakenings aw JOIN agents a ON a.id=aw.agente_id
 WHERE a.nombre IN ('Lycaon', 'N.º 0: Anby', 'Grace') AND aw.nivel=6;
SELECT 'sin agentes con 2 despertares (=0)' AS check_name, COUNT(*) AS expected_0
  FROM (SELECT agente_id FROM agent_awakenings GROUP BY agente_id HAVING COUNT(*) > 1);
SELECT 'deuda total pending_capture (=9)'  AS check_name, COUNT(*) AS expected_9
  FROM agent_awakenings WHERE tipo_efecto='pending_capture';

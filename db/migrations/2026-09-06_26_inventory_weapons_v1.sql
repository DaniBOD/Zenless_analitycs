-- =============================================================================
-- 2026-09-06_26 · inventory_weapons: la tabla que nadie escribió nunca
-- =============================================================================
-- `inventory_weapons` se creó a mano en la Fase 1 (abril 2026) y NUNCA tuvo
-- migración propia: no está en `db/migrations/`, sólo la mencionan de costado
-- las `_11` y `_13` para decir que no la tocan. Tiene **0 filas** y en todo
-- `app/` no hay un solo repo ni syncer que la escriba.
--
-- El censo de W-Engines la va a llenar por primera vez. Antes de que entre la
-- primera fila hay que arreglar tres cosas — y este es el ÚNICO momento barato,
-- porque con la tabla vacía el rebuild es gratis. Más adelante significa
-- reconstruir con filas y un índice parcial en el medio.
--
-- ## 1. Los DEFAULT convierten "no pude leer" en un dato plausible (RNF-02)
--
--     nivel        INTEGER DEFAULT 0
--     refinamiento INTEGER DEFAULT 1 CHECK(refinamiento BETWEEN 1 AND 5)
--
-- El parser devuelve `None` de forma legítima y lo deja anotado: `nivel_no_leido`,
-- `refinamiento_no_leido` (`app/core/parser_weapon_s26.py`). `read_refinamiento`
-- se abstiene a propósito cuando no encuentra las 5 estrellas, porque sin las 5
-- no se distingue una estrella gris de un recorte corrido.
--
-- CORRECCIÓN (2026-09-06, sólo este comentario; el DDL que se aplicó es idéntico):
-- la primera versión de esta nota decía que el CHECK viejo impedía guardar ese
-- `None`. Es FALSO y lo destapó un sabotaje que pasó en verde. En SQL un CHECK que
-- evalúa a NULL se considera SATISFECHO —sólo rechaza cuando da FALSE—, así que
-- `CHECK(refinamiento BETWEEN 1 AND 5)` aceptaba NULL sin chistar. Medido:
--
--     INSERT INTO viejo (weapon_id, refinamiento, nivel) VALUES (1, NULL, NULL) -> pasa
--     INSERT INTO viejo (weapon_id) VALUES (2)  ->  nivel=0, refinamiento=1
--
-- Lo que inventa es el DEFAULT, y SÓLO cuando la columna se OMITE del INSERT. Es un
-- riesgo más chico del que decía la nota, pero real: cualquier caller que omita la
-- columna (un script, un INSERT a mano) se lleva un 0 y un P1 indistinguibles de una
-- lectura de verdad, porque los dos son valores legítimos. Sin DEFAULT, ese mismo
-- caller se lleva NULL, que es la respuesta honesta.
--
-- El `IS NULL OR` del CHECK nuevo, entonces, NO cambia la conducta: documenta la
-- intención para quien lea la tabla.
--
-- SQLite no puede sacar un DEFAULT con ALTER: hay que reconstruir.
--
-- ## 2. "Un PJ equipa exactamente un W-Engine" pasa a ser una restricción
--
-- Es la clave natural de este censo — el equivalente de `(PJ, slot)` en discos —
-- y hasta ahora era sólo una premisa. Como índice único parcial, el error del
-- badge deja de ser dos filas peleándose en silencio y se vuelve un IntegrityError
-- en el momento de escribir. En discos, el caso análogo (dos filas reclamando el
-- mismo slot) pasó dos días sin que nadie lo viera y apareció consultando a mano.
--
-- ## 3. `descartado`, ahora que sale gratis
--
-- Las armas salen de la cuenta: los duplicados se consumen como material de
-- refinamiento — que es LA razón por la que hay copias repetidas en el inventario.
-- Sin baja lógica, sacarlas significaría DELETE, que es justo lo que la postura
-- del proyecto no hace (ver `marcar_descartado` en `app/db/repositories.py`).
-- Nada la escribe en v1; la columna se agrega igual porque la tabla está vacía
-- HOY y ese es el único momento en que no cuesta nada.
--
-- ## `origen_evidencia`: de qué se fía cada fila
--
-- Hay dos caminos para saber quién tiene un arma, y no valen lo mismo:
--   · 's26_desequipar' → el juego lo AFIRMA (el botón dice "Desequipar" sobre el
--                        PJ en pantalla). No pasa por la librería de badges.
--   · 's30_badge'      → lo dice el matcher de avatares. Medido en
--                        `test_s30_dueno_verdad_de_tierra.py`: 8/10, con un LIBRE
--                        falso. Nombrar es fiable; negar dueño, no.
--   · 's29_swap'       → el diálogo de sustitución, que el juego escribe en texto.
-- Ninguna otra cosa permite reconstruir después en qué se apoyó una fila.
--
-- ## Lo que esta migración NO hace
--
-- No toca `agents.weapon_id` / `weapon_nivel` / `weapon_rango` (0 de 51 con dato,
-- 0 lectores). Se conservan por criterio conservador (CLAUDE.md §5); lo que sí
-- cambia, en Python y no acá, es su clasificación en `rebuild_account_db.py`:
-- estaban en `AGENTS_NULL`, cuyo comentario promete que son "exactamente lo que
-- el pipeline sabe re-leer de pantalla" — y en cuanto `inventory_weapons` sea la
-- autoridad, esa promesa es falsa.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

SELECT 'ANTES' AS momento, COUNT(*) AS filas FROM inventory_weapons;

BEGIN TRANSACTION;

CREATE TABLE inventory_weapons_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id         INTEGER NOT NULL REFERENCES weapons(id),
    -- Sin DEFAULT a propósito: NULL = no se pudo leer, y 0 es un nivel válido.
    nivel             INTEGER,
    -- Admite NULL (el parser se abstiene si no ve las 5 estrellas) pero sigue
    -- rechazando cualquier entero fuera de 1..5.
    refinamiento      INTEGER CHECK(refinamiento IS NULL OR refinamiento BETWEEN 1 AND 5),
    agente_asignado   INTEGER REFERENCES agents(id),
    equipado          INTEGER NOT NULL DEFAULT 0 CHECK(equipado IN (0,1)),
    descartado        INTEGER NOT NULL DEFAULT 0 CHECK(descartado IN (0,1)),
    origen_evidencia  TEXT,
    fecha_obtencion   DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas             TEXT
);

-- Copia defensiva: hoy son 0 filas, pero el .sql no debe depender de eso.
INSERT INTO inventory_weapons_new
       (id, weapon_id, nivel, refinamiento, agente_asignado, equipado,
        descartado, origen_evidencia, fecha_obtencion, notas)
SELECT  id, weapon_id, nivel, refinamiento, agente_asignado,
        COALESCE(equipado, 0), 0, NULL, fecha_obtencion, notas
  FROM inventory_weapons;

DROP TABLE inventory_weapons;
ALTER TABLE inventory_weapons_new RENAME TO inventory_weapons;

-- La clave natural del censo, como restricción y no como premisa.
CREATE UNIQUE INDEX idx_invw_pj_equipada
    ON inventory_weapons(agente_asignado)
 WHERE equipado = 1 AND agente_asignado IS NOT NULL AND descartado = 0;

-- Las dos búsquedas del syncer (por PJ y por arma). La tabla es chica, así que
-- no es por velocidad: es para que el plan de consulta no dependa del tamaño.
CREATE INDEX idx_invw_weapon ON inventory_weapons(weapon_id) WHERE descartado = 0;

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM inventory_weapons;
-- Las 10 columnas del esquema nuevo.
SELECT COUNT(*) AS expected_10 FROM pragma_table_info('inventory_weapons');
-- Ni `nivel` ni `refinamiento` pueden tener DEFAULT: es el punto 1.
SELECT COUNT(*) AS expected_0 FROM pragma_table_info('inventory_weapons')
 WHERE name IN ('nivel','refinamiento') AND dflt_value IS NOT NULL;
-- Las dos columnas nuevas existen.
SELECT COUNT(*) AS expected_2 FROM pragma_table_info('inventory_weapons')
 WHERE name IN ('descartado','origen_evidencia');
-- Los dos índices nuevos.
SELECT COUNT(*) AS expected_2 FROM sqlite_master
 WHERE type='index' AND name IN ('idx_invw_pj_equipada','idx_invw_weapon');
-- El índice del PJ tiene que ser ÚNICO y PARCIAL: sin el WHERE prohibiría tener
-- dos armas sueltas sin dueño (agente_asignado NULL no colisiona, pero equipado=0
-- con dueño sí), y sin el UNIQUE no prohíbe nada.
SELECT COUNT(*) AS expected_1 FROM sqlite_master
 WHERE type='index' AND name='idx_invw_pj_equipada'
   AND sql LIKE '%UNIQUE%' AND sql LIKE '%WHERE%';
-- El catálogo no se toca.
SELECT COUNT(*) AS expected_59 FROM weapons;
-- Cómo queda, para que el log de la corrida lo muestre.
SELECT 'DESPUES' AS momento, name, type, "notnull", dflt_value
  FROM pragma_table_info('inventory_weapons') ORDER BY cid;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

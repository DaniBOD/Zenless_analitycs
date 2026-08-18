-- =============================================================================
-- roster_declarations · 2026-08-17
-- =============================================================================
-- El roster pasa a ser DECLARADO por el usuario, y el OCR queda como verificación.
--
-- POR QUÉ (QA en vivo del censo, 2026-08-17): el censo por observación funciona
-- para los PJs que se poseen (49/51 en 18 min) pero NO puede enumerar los que no:
--   · de 6 personajes no obtenidos por los que Daniel pasó, solo 1 dejó registro;
--   · 4 de 6 matchean a un PJ PROPIO por encima del umbral de identificación
--     (Norma→Nekomata 0.615 · Promeia→Pyrois 0.615 · Banyue→Anby 0.600 ·
--     Lichter→Alice 0.667), envenenando el latch que después atribuye discos.
-- O sea: pararse sobre un gris le dice al sistema que estás en otro personaje.
-- El usuario, en cambio, sabe perfectamente cuáles tiene.
--
-- Esto NO contradice RNF-02. La doctrina es "no inventar", no "no preguntar":
-- declarar ~55 casillas que el usuario sabe de memoria no es lo mismo que
-- transcribir a mano 367 discos con sus substats.
--
-- POR QUÉ UNA TABLA Y NO UNA COLUMNA: cada guardado escribe la TANDA COMPLETA
-- (todos los personajes conocidos, con su 1 o su 0). Eso da tres cosas que un
-- flag por fila no da:
--   1. Historial — la auditoría de sincronía que se pidió para el censo: se
--      re-declara después de cada parche y se puede comparar contra la anterior.
--   2. El DENOMINADOR explícito. La observación nunca puede darlo: por más que
--      el sistema recorra el menú, no sabe cuántos personajes existen en total.
--   3. El registro de los NO poseídos (poseido = 0), que es justo lo que la
--      pantalla no expone de forma fiable y lo que permite VETAR un match difuso.
--
-- POR QUÉ EN LA DB DE DOMINIO y no en `census.db`: lo declarado DEFINE el roster,
-- es dato de dominio. `census.db` guarda evidencia observacional sobre el dominio,
-- que es otra cosa.
--
-- No borra ni modifica nada existente: solo agrega una tabla y su índice.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS roster_declarations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,                      -- ISO local; igual para toda la tanda
    nombre  TEXT    NOT NULL,                      -- personaje del catálogo conocido
    poseido INTEGER NOT NULL CHECK (poseido IN (0, 1)),
    fuente  TEXT    NOT NULL DEFAULT 'usuario'     -- 'usuario' | (futuro) 'importado'
);

-- El acceso natural es "la tanda más reciente", de ahí el índice por ts.
CREATE INDEX IF NOT EXISTS ix_roster_decl_ts     ON roster_declarations(ts);
CREATE INDEX IF NOT EXISTS ix_roster_decl_nombre ON roster_declarations(nombre);

COMMIT;

-- =============================================================================
-- Validación
-- =============================================================================

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- La tabla existe y arranca vacía: la primera tanda la escribe el usuario desde
-- la pantalla, no esta migración. Declarar por él sería exactamente lo que RNF-02
-- prohíbe.
SELECT COUNT(*) AS expected_1 FROM sqlite_master
 WHERE type = 'table' AND name = 'roster_declarations';

SELECT COUNT(*) AS expected_2 FROM sqlite_master
 WHERE type = 'index' AND name IN ('ix_roster_decl_ts', 'ix_roster_decl_nombre');

SELECT COUNT(*) AS expected_0 FROM roster_declarations;

-- Nada de lo que ya estaba cambió.
SELECT COUNT(*) AS expected_51 FROM agents;

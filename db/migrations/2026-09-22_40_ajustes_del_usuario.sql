-- =============================================================================
-- Ajustes del usuario sobre los defaults · 2026-09-22 · migración 40
-- =============================================================================
-- Fase A, etapa 1, paso 5. Daniel: "Prydwen es una base, sí, pero de ahí puedo pulirlas yo a mano
-- (estos serían los defaults para todos los usuarios)". O sea DOS capas:
--
--   default  → lo que ya está: `agent_thresholds`, `agent_substat_preferences`, `disc_archetypes`
--              (Prydwen, Game8, 141store… con su `fuente`). NO SE TOCA.
--   ajuste   → lo que Daniel corrige a mano. Tablas NUEVAS, una por tipo de dato.
--
-- El repositorio las mezcla: **el ajuste gana, y si se borra la fila, vuelve el default**. Por eso
-- no se sobrescriben las tablas de default: sobrescribir perdería el valor de Prydwen, y "volver al
-- default" pasaría a necesitar una fuente que ya no estaría en la DB.
--
-- ## Por qué tres tablas y no una genérica
--
-- Cada tipo tiene su forma y sus reglas, y SQLite las puede hacer cumplir si son columnas: un rango
-- tiene piso ≤ techo; un peso vive en [-1, 1] como en `agent_substat_preferences`; un ajuste de
-- arquetipo sólo puede tocar los principales permitidos. En una tabla (clave, valor) genérica esas
-- reglas quedarían en el código de quien lee, o sea en ningún lado.
--
-- `ajustes_usuario_arquetipo.campo` acepta sólo `mains_4/5/6`, que es lo único que Daniel ajustó.
-- Ampliarlo (p. ej. los pesos de un arquetipo) es otra migración: a propósito, para que nadie
-- escriba un campo que el repositorio no sabe aplicar.
--
-- ## De dónde sale cada fila (RNF-02)
--
--   HP_DISRUPT · mains_4 = [Prob. Crítica, Daño Crítico]
--       Daniel, caso 6 (2026-09-22): el PV % en slot 4 "no sirve ni para disruptores", y al
--       preguntarle cómo quedaban eligió "sólo Prob. Crítica y Daño Crítico". El default de la DB
--       (`disc_archetypes`) acepta además PV %; queda como está.
--   Ellen · ataque · 3000-3200
--       Daniel, al plantear la fase: "un rango objetivo, como por ejemplo entre 3000 a 3200 de ataque
--       para Ellen Joe". El default de Prydwen en `agent_thresholds` es 2400-2800; queda como está.
--
-- El resto de los rangos los va a pasar Daniel por chat, en una migración aparte.
--
-- ## Vocabulario de `stat` en los rangos
--
-- El mismo que `agent_thresholds.stat` y que las columnas de `agents` (`ataque`, `prob_critico`,
-- `dano_critico`, …): el rango se compara contra el stat ACTUAL del PJ, que vive en esa columna.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE ajustes_usuario_rangos (
    agente_id   INTEGER NOT NULL REFERENCES agents(id),
    stat        TEXT    NOT NULL,
    minimo      REAL,
    maximo      REAL,
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agente_id, stat),
    CHECK (minimo IS NOT NULL OR maximo IS NOT NULL),
    CHECK (minimo IS NULL OR maximo IS NULL OR minimo <= maximo)
);

CREATE TABLE ajustes_usuario_pesos (
    agente_id   INTEGER NOT NULL REFERENCES agents(id),
    substat     TEXT    NOT NULL,
    peso        REAL    NOT NULL CHECK (peso BETWEEN -1.0 AND 1.0),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agente_id, substat)
);

CREATE TABLE ajustes_usuario_arquetipo (
    code        TEXT NOT NULL REFERENCES disc_archetypes(code),
    campo       TEXT NOT NULL CHECK (campo IN ('mains_4', 'mains_5', 'mains_6')),
    valor_json  TEXT NOT NULL CHECK (json_valid(valor_json) AND json_type(valor_json) = 'array'),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, campo)
);

INSERT INTO ajustes_usuario_arquetipo (code, campo, valor_json)
VALUES ('HP_DISRUPT', 'mains_4', '["Prob. Crítica", "Daño Crítico"]');

INSERT INTO ajustes_usuario_rangos (agente_id, stat, minimo, maximo)
SELECT id, 'ataque', 3000, 3200 FROM agents WHERE nombre = 'Ellen';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- =============================================================================
-- SMOKE CHECKS
-- =============================================================================

SELECT COUNT(*) AS expected_1 FROM ajustes_usuario_arquetipo;
SELECT COUNT(*) AS expected_1 FROM ajustes_usuario_rangos;
SELECT COUNT(*) AS expected_0 FROM ajustes_usuario_pesos;

-- El rango de Ellen quedó colgado de SU fila (el INSERT…SELECT no insertó nada si el nombre no
-- matcheaba, y eso lo diría el check de arriba; éste además confirma que es ella).
SELECT COUNT(*) AS expected_1 FROM ajustes_usuario_rangos r JOIN agents a ON a.id = r.agente_id
 WHERE a.nombre = 'Ellen' AND r.stat = 'ataque' AND r.minimo = 3000 AND r.maximo = 3200;

-- Los DEFAULTS no se tocaron: el de HP_DISRUPT sigue aceptando PV % y el de Ellen sigue en 2400-2800.
SELECT COUNT(*) AS expected_1 FROM disc_archetypes
 WHERE code = 'HP_DISRUPT' AND mains_4 LIKE '%"HP%"%';
SELECT COUNT(*) AS expected_1 FROM agent_thresholds t JOIN agents a ON a.id = t.agente_id
 WHERE a.nombre = 'Ellen' AND t.stat = 'ataque' AND t.valor_minimo = 2400 AND t.valor_optimo = 2800;
SELECT COUNT(*) AS expected_114 FROM agent_thresholds;
SELECT COUNT(*) AS expected_68 FROM agent_substat_preferences;

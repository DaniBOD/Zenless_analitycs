-- =============================================================================
-- Builds recomendados por PJ + build objetivo de Daniel · 2026-09-25 · migración 43
-- =============================================================================
-- Fase A, etapa 1. Segunda revisión de las sugerencias (SPEC, casos 12 y 13): el motor mandaba
-- Armonía umbría a Ye Shunguang ("no genera réplicas") y Balada de la rama y la espada a Nangong Yu
-- ("las 2pc son para daño crítico; ella es stunner/anómala"). Medido: el set sólo entra al puntaje
-- por `disc_set_archetype`, que es por ROL; `agents.set_4p_id/set_2p_id` están en NULL en los 52
-- (eran la build OBSERVADA y nadie la reconstruye desde el rebuild del 2026-08-17). El motor no sabe
-- qué sets usa cada PJ, ni qué stats quiere cada uno cuando se aparta de su rol.
--
-- Decisiones de Daniel (2026-09-25):
--   R18 · el set es del PJ, no del rol: base de conocimiento por PJ desde las wikis (Prydwen
--         primaria), con fuente por fila; lo no confirmado queda NULL. En la misma pasada, los
--         principales de los slots 4-6 y la prioridad de substats.
--   R19 · build objetivo: el que declara Daniel en la ficha; si no hay, los sets equipados si están
--         entre los recomendados; si no, el primero recomendado.
--   R20 · un disco de un set fuera del build objetivo no es candidato para ese PJ.
--
-- Esta migración es sólo el ESQUEMA. Los datos los carga `app/scripts/cargar_builds_prydwen.py`
-- desde `audit/prydwen/2026-09-25_builds_prydwen.json` (la captura, con la versión de cada guía).
--
-- ## Tres tablas de conocimiento (INVESTIGACION: el censo no las recupera)
--
--   pj_sets_4pc   un 4pc recomendado para un PJ, en el orden de la guía. `rango_fuente` es el
--                 número que muestra la guía (dos 4pc pueden compartir el 1: Nangong Yu) y
--                 `puntaje_fuente` el % calculado cuando la guía lo da en vez del número.
--   pj_sets_2pc   los 2pc que la guía combina con ESE 4pc. `grupo` es el renglón de la guía: dos
--                 sets en el mismo renglón son alternativas equivalentes ("Freedom Blues / Chaos
--                 Jazz"). `recomendado` = el renglón que la guía marca "(Recommended)".
--   pj_stats_recomendados
--                 los principales de los discos 4-6 y los substats, como NIVELES: "A = B > C" da
--                 A y B en el nivel 1 y C en el 2. Se guarda lo que dice la guía, no un peso: pasar
--                 de niveles a pesos es una decisión del motor, aparte. `variante` separa las
--                 builds alternativas de una misma guía ("Anomaly Build" / "CRIT Build"); 'única'
--                 = la guía tiene una sola. NOT NULL a propósito: en un UNIQUE de SQLite dos NULL
--                 son distintos, y la tabla aceptaría dos veces el mismo stat.
--
-- ## Una tabla declarada (DECLARADO)
--
--   ajustes_usuario_build
--                 el build objetivo que Daniel elige en la ficha del PJ: un 4pc y, opcional, un
--                 2pc. Sin fila = no declaró (R19 decide). Misma capa que las migraciones 40 y 42.
--
-- ## Por qué no `agents.set_4p_id/set_2p_id`
--
-- Son estado observado de la cuenta (`rebuild_account_db.AGENTS_NULL` las vacía). Poner ahí una
-- recomendación o una declaración mezclaría tres preguntas distintas en dos columnas (B1).
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE pj_sets_4pc (
    agente_id      INTEGER NOT NULL REFERENCES agents(id),
    set_id         INTEGER NOT NULL REFERENCES disc_sets(id),
    orden          INTEGER NOT NULL CHECK (orden >= 1),
    rango_fuente   INTEGER,
    puntaje_fuente REAL,
    fuente         TEXT    NOT NULL,
    url            TEXT    NOT NULL,
    version_guia   TEXT,
    capturado      DATE    NOT NULL,
    PRIMARY KEY (agente_id, set_id),
    UNIQUE (agente_id, orden)
);

CREATE TABLE pj_sets_2pc (
    agente_id    INTEGER NOT NULL,
    set_4p_id    INTEGER NOT NULL,
    set_id       INTEGER NOT NULL REFERENCES disc_sets(id),
    grupo        INTEGER NOT NULL CHECK (grupo >= 1),
    recomendado  INTEGER NOT NULL DEFAULT 0 CHECK (recomendado IN (0, 1)),
    PRIMARY KEY (agente_id, set_4p_id, set_id),
    FOREIGN KEY (agente_id, set_4p_id) REFERENCES pj_sets_4pc(agente_id, set_id)
);

CREATE TABLE pj_stats_recomendados (
    agente_id    INTEGER NOT NULL REFERENCES agents(id),
    variante     TEXT    NOT NULL,
    linea        TEXT    NOT NULL CHECK (linea IN ('principal_4', 'principal_5', 'principal_6', 'substat')),
    nivel        INTEGER NOT NULL CHECK (nivel >= 1),
    stat         TEXT    NOT NULL,
    texto_guia   TEXT    NOT NULL,
    fuente       TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    version_guia TEXT,
    capturado    DATE    NOT NULL,
    UNIQUE (agente_id, variante, linea, stat)
);

CREATE TABLE ajustes_usuario_build (
    agente_id   INTEGER PRIMARY KEY REFERENCES agents(id),
    set_4p_id   INTEGER NOT NULL REFERENCES disc_sets(id),
    set_2p_id   INTEGER REFERENCES disc_sets(id),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (set_2p_id IS NULL OR set_2p_id <> set_4p_id)
);

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;
SELECT COUNT(*) AS expected_0 FROM pj_sets_4pc;
SELECT COUNT(*) AS expected_0 FROM ajustes_usuario_build;

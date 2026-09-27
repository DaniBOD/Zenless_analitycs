-- =============================================================================
-- La ficha del PJ: sets y stats que se vuelven pesos · 2026-09-27 · migración 46
-- =============================================================================
-- SPEC: Documentacion/Dev_IA/documentacion_cruda/2026-09/2026-09-27_SPEC_Editor_de_la_ficha_sets_y_stats.md
--
-- Daniel: "el usuario no es que toque el motor, sino que al seleccionar un set y los stats
-- deseados influyen en los pesos de forma interna". El usuario elige NIVELES (Imprescindible /
-- Muy bueno / Bueno / Sirve / No sirve), principales y stats fijos; el repositorio los vuelve
-- pesos al cargar. Mismo principio que la mig 40: la guía es el default y no se toca, el ajuste
-- gana, y si se borra el ajuste vuelve la guía.
--
-- ## Tablas declaradas (DECLARADO en el rebuild)
--
--   ajustes_usuario_substats     nivel por substat: 1..4 = los niveles de la guía (1,0 / 0,8 /
--                                0,6 / 0,4) y 0 = "no sirve". Se guarda el NIVEL, no el peso.
--   ajustes_usuario_principales  los principales de un slot 4-6; reemplaza a la guía EN ese slot.
--   ajustes_usuario_fijos        un stat fijo del usuario; objetivo NULL = "desactivé el de la guía".
--
-- ## Tabla de investigación
--
--   set_condiciones_4pc          lo que el 4pc de un set exige: un stat (≥ umbral), un rol o un
--                                elemento. `alcance` dice si la condición gobierna TODO el efecto o
--                                sólo una PARTE. Verificadas el 2026-09-27 contra Fandom (la wiki
--                                oficial en inglés), texto del 4pc en `audit/set_condiciones_4pc_20260927.md`.
--                                "Anomaly Mastery" = "Tasa de Anomalía" (tabla de idiomas de la
--                                wiki) → columna `tasa_anomalia`.
--
-- ## Una sola autoridad (B1)
--
-- La condición de Monarca del Pináculo (Prob. Crítica ≥ 50 %) estaba COPIADA en `pj_stats_fijos`,
-- una fila por PJ cuya guía lista ese 4pc (mig 45, `requiere_set_4p_id = 34`, 8 filas). Pasa a
-- vivir una vez en `set_condiciones_4pc`; las copias se borran. La columna `requiere_set_4p_id`
-- queda sin uso (el UNIQUE que la incluye impide sacarla con ALTER).
--
-- `ajustes_usuario_pesos` (mig 40) guardaba el PESO crudo y está vacía (0 filas, medido el
-- 2026-09-27): se retira. El peso numérico no queda en ningún lado que el usuario toque.
--
-- De paso: la cuenta del fijo de Yuzuha decía "Maestría de Anomalía" y su kit usa Anomaly Mastery
-- ("If Yuzuha's Anomaly Mastery exceeds 100", Fandom) = Tasa de Anomalía. El stat ya era
-- `tasa_anomalia`; se corrige el texto.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE ajustes_usuario_substats (
    agente_id   INTEGER NOT NULL REFERENCES agents(id),
    substat     TEXT    NOT NULL CHECK (substat IN ('HP', 'HP%', 'ATK', 'ATK%', 'DEF', 'DEF%',
                            'Prob. Crítica', 'Daño Crítico', 'Perforación', 'Maestría de Anomalía')),
    nivel       INTEGER NOT NULL CHECK (nivel BETWEEN 0 AND 4),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agente_id, substat)
);

CREATE TABLE ajustes_usuario_principales (
    agente_id   INTEGER NOT NULL REFERENCES agents(id),
    slot        INTEGER NOT NULL CHECK (slot BETWEEN 4 AND 6),
    valor_json  TEXT    NOT NULL CHECK (json_valid(valor_json) AND json_type(valor_json) = 'array'),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agente_id, slot)
);

CREATE TABLE ajustes_usuario_fijos (
    agente_id   INTEGER NOT NULL REFERENCES agents(id),
    stat        TEXT    NOT NULL CHECK (stat IN ('prob_critico', 'ataque', 'pv', 'defensa', 'impacto',
                            'tasa_anomalia', 'maestria_anomalia', 'tasa_perforacion', 'rec_energia')),
    objetivo    REAL,
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agente_id, stat)
);

CREATE TABLE set_condiciones_4pc (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id      INTEGER NOT NULL REFERENCES disc_sets(id),
    tipo        TEXT    NOT NULL CHECK (tipo IN ('stat', 'rol', 'elemento')),
    stat        TEXT    CHECK (stat IS NULL OR stat IN ('prob_critico', 'ataque', 'pv', 'defensa',
                            'impacto', 'tasa_anomalia', 'maestria_anomalia', 'tasa_perforacion',
                            'rec_energia')),
    umbral      REAL,
    rol         TEXT,
    elemento    TEXT,
    alcance     TEXT    NOT NULL CHECK (alcance IN ('todo', 'parte')),
    texto       TEXT    NOT NULL,
    fuente      TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    capturado   DATE    NOT NULL,
    CHECK (tipo <> 'stat' OR (stat IS NOT NULL AND umbral IS NOT NULL AND rol IS NULL AND elemento IS NULL)),
    CHECK (tipo <> 'rol' OR (rol IS NOT NULL AND stat IS NULL AND umbral IS NULL AND elemento IS NULL)),
    CHECK (tipo <> 'elemento' OR (elemento IS NOT NULL AND stat IS NULL AND umbral IS NULL AND rol IS NULL))
);

INSERT INTO set_condiciones_4pc (set_id, tipo, stat, umbral, rol, elemento, alcance, texto, fuente, url, capturado)
SELECT s.id, v.tipo, v.stat, v.umbral, v.rol, v.elemento, v.alcance, v.texto, 'fandom',
       'https://zenless-zone-zero.fandom.com/wiki/' || v.pagina, '2026-09-27'
FROM (
  WITH v(nombre_en, pagina, tipo, stat, umbral, rol, elemento, alcance, texto) AS (VALUES
    ('King of the Summit', 'King_of_the_Summit', 'rol', NULL, NULL, 'Aturdimiento', NULL, 'todo',
     'Todo el efecto: "When the equipper is a Stun character and uses an EX Special Attack or Chain Attack"'),
    ('King of the Summit', 'King_of_the_Summit', 'stat', 'prob_critico', 50, NULL, NULL, 'parte',
     'El segundo +15 % de Daño Crítico al equipo: "when the equipper''s CRIT Rate is more than or equal to 50 %"'),
    ('Branch & Blade Song', 'Branch_%26_Blade_Song', 'stat', 'tasa_anomalia', 115, NULL, NULL, 'parte',
     'Daño Crítico +30 %: "When Anomaly Mastery exceeds or equals 115 points" (Anomaly Mastery = Tasa de Anomalía)'),
    ('Thorned Rose', 'Thorned_Rose', 'stat', 'defensa', 1800, NULL, NULL, 'parte',
     'Prob. Crítica +8/16 %: "When the equipper''s initial DEF is at least 1,000/1,800". El fijo es el escalón completo'),
    ('Bunny in Wonderland', 'Bunny_in_Wonderland', 'rol', NULL, NULL, 'Defensa', NULL, 'todo',
     'Todo el efecto: "When the equipper is a Defense character"'),
    ('Moonlight Lullaby', 'Moonlight_Lullaby', 'rol', NULL, NULL, 'Soporte', NULL, 'todo',
     'Todo el efecto: "When the equipper is a Support character"'),
    ('Dawn''s Bloom', 'Dawn%27s_Bloom', 'rol', NULL, NULL, 'Ataque', NULL, 'parte',
     'El segundo +20 % de daño de Ataque Básico: "When equipped by an Attack character"'),
    ('White Water Ballad', 'White_Water_Ballad', 'rol', NULL, NULL, 'Ataque', NULL, 'parte',
     'El +10 % de Prob. Crítica y ATK extra: "If the equipper is an Attack character"'),
    ('The Sky Ablaze', 'The_Sky_Ablaze', 'elemento', NULL, NULL, NULL, 'Éter', 'parte',
     'Daño Crítico +30 %: "When the equipper is an Ether attribute Agent" (el ATK +10 % vale para todos)'),
    ('Feathered Fate', 'Feathered_Fate', 'elemento', NULL, NULL, NULL, 'Lumen', 'parte',
     'Daño de Anomalía +15 %: "If the equipper is a Lumiflux character" (la Maestría +50 vale para todos)')
  )
  SELECT * FROM v
) v
JOIN disc_sets s ON s.nombre_en = v.nombre_en;

DELETE FROM pj_stats_fijos WHERE requiere_set_4p_id IS NOT NULL;

UPDATE pj_stats_fijos
SET cuenta = 'Tasa de Anomalía (Anomaly Mastery) sobre 100: +0,2 % por punto, hasta 20 % → 100 + 20/0,2 = 200'
WHERE stat = 'tasa_anomalia' AND agente_id = (SELECT id FROM agents WHERE nombre = 'Yuzuha');

DROP TABLE ajustes_usuario_pesos;

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;
SELECT COUNT(*) AS expected_10 FROM set_condiciones_4pc;
SELECT COUNT(*) AS expected_0 FROM pj_stats_fijos WHERE requiere_set_4p_id IS NOT NULL;
SELECT COUNT(*) AS expected_16 FROM pj_stats_fijos;

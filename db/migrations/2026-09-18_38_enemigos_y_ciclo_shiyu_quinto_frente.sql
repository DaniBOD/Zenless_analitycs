-- =============================================================================
-- Enemigos del Quinto Frente y el primer ciclo de Shiyu en la DB · 2026-09-18 · migración 38
-- =============================================================================
-- Primera carga real de la capa 7 (RF-13): hasta hoy `enemies` tenía 12 filas seed de abril y
-- `shiyu_cycles` estaba en 0. Daniel pidió guardar los enemigos y los buffos del ciclo que acaba
-- de superar (104 789, S+) como base para una futura IA asesora de endgame.
--
-- QUÉ HACE
--   1. `enemies` suma 5 columnas (aditivas, NULL por defecto): atk_base, def_base, daze_base,
--      stun_duracion_s, stun_dmg_mult. Todas al `nivel_referencia` de la fila. Sin ellas el Daze
--      —que decide cuánto tarda un stun— quedaba afuera, y en Shiyu es de lo que más pesa.
--   2. Alta de los 11 enemigos del Quinto Frente (3 jefes + 8 de oleada).
--   3. 66 filas de `enemy_resistances` (11 × 6 atributos).
--   4. Alta del ciclo en `shiyu_cycles`, con las 3 salas, oleadas, buffos y topes de puntaje.
--
-- DE DÓNDE SALE CADA DATO (RNF-02)
--   · Stats, RES y stun: Fandom (fuente autorizada), tabla de nivel 70. En Nodo Crítico los
--     enemigos vienen escalados; `escalado_dificultad` queda NULL porque no hay fuente.
--   · RES → multiplicador: Fandom da RES en % (−20 % débil, +20 % resiste). El daño recibido
--     escala por (1 − RES): −20 % ⇒ 1.2 y +20 % ⇒ 0.8. El seed de abril usaba 1.3/0.7 sin
--     fuente; estas filas NO lo copian.
--   · `frost` y `lumen` NO se cargan: Fandom no los lista, y Lumiflux toma el atributo del agente
--     que sigue a Remielle, así que no hay una RES fija que afirmar. La ausencia es "no sé", no
--     "neutral".
--   · nombre_es: nombre oficial en español según Fandom (Other Languages), NO leído de pantalla.
--   · Oleadas y buffos: Game8. El texto de los buffos se guarda en inglés tal cual la fuente
--     (`modificadores_en`) y traducido (`modificadores_es`).
--   · Verificado contra PANTALLA (captura del resumen, 2026-09-18): atributos recomendados y
--     "resistencia de enemigo poderoso" de las 3 salas. Sala 2: la pantalla dice sólo Etéreo.
--     Akademiya decía Éter + Físico; Fandom y Game8 coinciden con la pantalla. Manda la pantalla.
--   · Fechas: Game8 (reset viernes por medio, próximo 2026-09-18) ⇒ inicio 2026-09-04, inferido.
--   · `cycle_number` = 1 es numeración INTERNA (primer ciclo capturado), no la del juego (C2).
--
-- NO SE TOCA `lategame_runs`: su esquema es anterior al rework V2 (estrellas 0-3, frente 1-9).
-- =============================================================================

BEGIN TRANSACTION;

ALTER TABLE enemies ADD COLUMN atk_base INTEGER;
ALTER TABLE enemies ADD COLUMN def_base INTEGER;
ALTER TABLE enemies ADD COLUMN daze_base INTEGER;
ALTER TABLE enemies ADD COLUMN stun_duracion_s REAL;
ALTER TABLE enemies ADD COLUMN stun_dmg_mult REAL;

INSERT INTO enemies (nombre_es, nombre_en, tipo, faccion, hp_base, atk_base, def_base, daze_base,
                     stun_duracion_s, stun_dmg_mult, nivel_referencia, escalado_dificultad,
                     mecanicas_clave, fuente, fuente_url, notas) VALUES
('Unidad de apoyo autónoma: centinela del espacio aéreo', 'Autonomous Assault Unit - Airspace Sentinel',
 'boss', 'Special', 2299064, 1201, 953, 15008, 12, 1.50, 70, NULL,
 'Expone su núcleo en ciertos movimientos o tras parry-ear ataques específicos; golpear el núcleo expuesto hace daño extra y lo deja Impaired. Barra de Daze más alta del Quinto Frente.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Airspace_Sentinel',
 'Tipo Ethereal. Jefe sala 2 del Quinto Frente (ciclo 1). nombre_es de Fandom, no de pantalla.'),
('Cerrosorte', 'Lockspring',
 'boss', 'Special', 1451241, 1109, 953, 12959, 12, 1.50, 70, NULL,
 'Algunos golpes son tan fuertes que, aun con Defensive Assist exitoso, no se activa el Assist Follow-Up (y puede burlarse). No contar con ese daño en la rotación.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Lockspring_(Boss)',
 'Tipo Machine. Jefe sala 3 del Quinto Frente (ciclo 1). nombre_es de Fandom, no de pantalla.'),
('Tepes', 'Tepes',
 'boss', 'Ether Mutants', 1151316, 1331, 953, 13236, 12, 1.25, 70, NULL,
 'Sus martillos aplican reducción de daño. Varias Defensive Assist contra los golpes de mano los dejan Impaired: pierde la reducción de daño, abre ventanas y gana vulnerabilidad a Daze. Existe una Variation 1 con otras debilidades (Fuego/Eléctrico); la del ciclo 1 es la base.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Tepes',
 'Tipo Ethereal. Jefe sala 1 del Quinto Frente (ciclo 1). Stun DMG Multiplier 125 % (los otros dos jefes, 150 %).'),
('Bandido corrompido - Tirador codicioso', 'Corrupted Bandit - Greedy Ranger',
 'normal', 'Corrupted', 60709, 610, 635, 1002, 6.5, 1.50, 70, NULL, NULL,
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Greedy_Ranger',
 'Tipo Ethereal. Oleada 1 sala 1 (×3). nombre_es de Fandom.'),
('Pugnus ionizado', 'Ionized - Pugnus',
 'elite', 'Ether Mutants', 705321, 1026, 858, 9382, 13, 1.50, 70, NULL, NULL,
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Ionized_-_Pugnus',
 'Tipo Ethereal. Oleada 2 sala 1 (×1). nombre_es de Fandom.'),
('Bandido corrompido - Matón despiadado', 'Corrupted Bandit - Vicious Striker',
 'normal', 'Corrupted', 60709, 499, 635, 1002, 6.5, 1.50, 70, NULL, NULL,
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Vicious_Striker',
 'Tipo Ethereal. Oleada 2 sala 1 (×2). nombre_es de Fandom.'),
('Bandido frenético miasmático', 'Miasmic - Frenzied Maniac',
 'elite', 'Corrupted', 517949, 1072, 858, 7310, 10, 1.50, 70, NULL,
 'Ataques sorpresa en sigilo. Con Trinox en campo hace Perfect Dodge y ataque coordinado; si uno muere, el otro entra en Frenesí.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Miasmic_-_Frenzied_Maniac',
 'Tipo Ethereal. Oleada 1 sala 2. nombre_es de Fandom.'),
('Trinox miasmático', 'Miasmic - Trinox',
 'elite', 'Corrupted', 748136, 1072, 858, 8407, 10, 1.50, 70, NULL,
 'Parry que desvía daño y Block Counter. Ordena ataques coordinados al Frenzied Maniac; si uno muere, el otro entra en Frenesí.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Miasmic_-_Trinox',
 'Tipo Ethereal. Oleada 1 sala 2. nombre_es de Fandom.'),
('Unidad de apoyo autónoma - rondador escurridizo (II)', 'Autonomous Support Unit - Lightfoot Rover MK II',
 'elite', 'Rebel Soldiers', 383664, 730, 858, 5848, 10, 1.50, 70, NULL,
 'Invoca dos drones que pueden autodestruirse junto al objetivo.',
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Lightfoot_Rover_MK_II',
 'Tipo Machine. Oleada 1 sala 3. nombre_es de Fandom.'),
('Milicia miasmática: escudado', 'Miasmic Trooper - Shieldguard',
 'normal', 'Corrupted', 88010, 665, 730, 1102, 6.5, 1.50, 70, NULL, NULL,
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Miasmic_Trooper_-_Shieldguard',
 'Tipo Sacrifice. Oleada 1 sala 3 (×2). nombre_es de Fandom.'),
('Milicia miasmática: artillero', 'Miasmic Trooper - Cannoneer',
 'normal', 'Corrupted', 88010, 601, 635, 1102, 6.5, 1.50, 70, NULL, NULL,
 'fandom', 'https://zenless-zone-zero.fandom.com/wiki/Miasmic_Trooper_-_Cannoneer',
 'Tipo Sacrifice. Oleada 1 sala 3 (×2). nombre_es de Fandom.');

-- RES de Fandom, una columna por atributo. mult = 1 − RES.
CREATE TEMP TABLE _res (nombre_en TEXT, elemento TEXT, mult REAL);
INSERT INTO _res VALUES
('Autonomous Assault Unit - Airspace Sentinel', 'fisico', 1.0), ('Autonomous Assault Unit - Airspace Sentinel', 'fuego', 1.0),
('Autonomous Assault Unit - Airspace Sentinel', 'hielo', 1.2),  ('Autonomous Assault Unit - Airspace Sentinel', 'electrico', 1.0),
('Autonomous Assault Unit - Airspace Sentinel', 'eter', 0.8),   ('Autonomous Assault Unit - Airspace Sentinel', 'viento', 1.2),
('Lockspring', 'fisico', 1.2), ('Lockspring', 'fuego', 1.0), ('Lockspring', 'hielo', 1.0),
('Lockspring', 'electrico', 1.2), ('Lockspring', 'eter', 0.8), ('Lockspring', 'viento', 1.0),
('Tepes', 'fisico', 1.0), ('Tepes', 'fuego', 1.0), ('Tepes', 'hielo', 1.2),
('Tepes', 'electrico', 1.0), ('Tepes', 'eter', 1.2), ('Tepes', 'viento', 1.0),
('Corrupted Bandit - Greedy Ranger', 'fisico', 1.0), ('Corrupted Bandit - Greedy Ranger', 'fuego', 1.2),
('Corrupted Bandit - Greedy Ranger', 'hielo', 1.0),  ('Corrupted Bandit - Greedy Ranger', 'electrico', 1.0),
('Corrupted Bandit - Greedy Ranger', 'eter', 1.0),   ('Corrupted Bandit - Greedy Ranger', 'viento', 1.0),
('Ionized - Pugnus', 'fisico', 1.2), ('Ionized - Pugnus', 'fuego', 1.0), ('Ionized - Pugnus', 'hielo', 1.2),
('Ionized - Pugnus', 'electrico', 1.0), ('Ionized - Pugnus', 'eter', 1.0), ('Ionized - Pugnus', 'viento', 1.0),
('Corrupted Bandit - Vicious Striker', 'fisico', 1.0), ('Corrupted Bandit - Vicious Striker', 'fuego', 1.2),
('Corrupted Bandit - Vicious Striker', 'hielo', 1.0),  ('Corrupted Bandit - Vicious Striker', 'electrico', 1.0),
('Corrupted Bandit - Vicious Striker', 'eter', 1.0),   ('Corrupted Bandit - Vicious Striker', 'viento', 1.0),
('Miasmic - Frenzied Maniac', 'fisico', 0.8), ('Miasmic - Frenzied Maniac', 'fuego', 1.0), ('Miasmic - Frenzied Maniac', 'hielo', 1.0),
('Miasmic - Frenzied Maniac', 'electrico', 1.0), ('Miasmic - Frenzied Maniac', 'eter', 1.2), ('Miasmic - Frenzied Maniac', 'viento', 1.0),
('Miasmic - Trinox', 'fisico', 0.8), ('Miasmic - Trinox', 'fuego', 1.0), ('Miasmic - Trinox', 'hielo', 1.0),
('Miasmic - Trinox', 'electrico', 1.0), ('Miasmic - Trinox', 'eter', 1.2), ('Miasmic - Trinox', 'viento', 1.0),
('Autonomous Support Unit - Lightfoot Rover MK II', 'fisico', 1.0), ('Autonomous Support Unit - Lightfoot Rover MK II', 'fuego', 0.8),
('Autonomous Support Unit - Lightfoot Rover MK II', 'hielo', 1.0),  ('Autonomous Support Unit - Lightfoot Rover MK II', 'electrico', 1.2),
('Autonomous Support Unit - Lightfoot Rover MK II', 'eter', 1.0),   ('Autonomous Support Unit - Lightfoot Rover MK II', 'viento', 1.0),
('Miasmic Trooper - Shieldguard', 'fisico', 1.0), ('Miasmic Trooper - Shieldguard', 'fuego', 1.2), ('Miasmic Trooper - Shieldguard', 'hielo', 1.0),
('Miasmic Trooper - Shieldguard', 'electrico', 1.2), ('Miasmic Trooper - Shieldguard', 'eter', 1.0), ('Miasmic Trooper - Shieldguard', 'viento', 1.0),
('Miasmic Trooper - Cannoneer', 'fisico', 1.0), ('Miasmic Trooper - Cannoneer', 'fuego', 1.2), ('Miasmic Trooper - Cannoneer', 'hielo', 1.0),
('Miasmic Trooper - Cannoneer', 'electrico', 1.2), ('Miasmic Trooper - Cannoneer', 'eter', 1.0), ('Miasmic Trooper - Cannoneer', 'viento', 1.0);

INSERT INTO enemy_resistances (enemy_id, elemento, multiplicador, breakdown_status, notas)
SELECT e.id, r.elemento, r.mult,
       CASE WHEN r.mult > 1 THEN 'weak' WHEN r.mult < 1 THEN 'resistant' ELSE 'neutral' END,
       CASE WHEN e.tipo = 'boss'
            THEN 'Fandom (RES %). Resistencias del jefe verificadas contra pantalla 2026-09-18.'
            ELSE 'Fandom (RES %).' END
FROM _res r JOIN enemies e ON e.nombre_en = r.nombre_en;

DROP TABLE _res;

-- El ciclo. Los ids se resuelven por nombre_en para no depender del autoincrement.
INSERT INTO shiyu_cycles (cycle_number, fecha_inicio, fecha_fin, frentes, fuente, notas)
SELECT 1, '2026-09-04', '2026-09-18',
 json_array(
  json_object('frente', 5, 'sala', 1, 'jefe', t.id,
   'oleadas', json_array(
      json_array(json_object('id', gr.id, 'n', 3)),
      json_array(json_object('id', pu.id, 'n', 1), json_object('id', vs.id, 'n', 2)),
      json_array(json_object('id', t.id, 'n', 1))),
   'elemento_recomendado', json_array('hielo', 'eter'),
   'resistencia_enemigo_poderoso', json_array(),
   'modificadores_en', 'Agent Ether DMG and Ice DMG increases by 35%, while their CRIT DMG increases by 25%. When an Agent with Attack specialty hits a Stunned enemy, enemy DEF drops by 25% for 5s.',
   'modificadores_es', 'Daño Éter y Hielo de los agentes +35 % y su Daño CRÍT +25 %. Cuando un agente de especialidad Ataque golpea a un enemigo aturdido, la DEF del enemigo baja 25 % por 5 s.',
   'score_tope', 50000, 'score_S', 25000),
  json_object('frente', 5, 'sala', 2, 'jefe', se.id,
   'oleadas', json_array(
      json_array(json_object('id', fm.id, 'n', 1), json_object('id', tr.id, 'n', 1)),
      json_array(json_object('id', se.id, 'n', 1))),
   'elemento_recomendado', json_array('hielo', 'viento'),
   'resistencia_enemigo_poderoso', json_array('eter'),
   'modificadores_en', 'If there are 2/3 Agents with the Anomaly specialty in the squad, Attribute Anomaly DMG dealt by Agents increases by 10%/60%, and the whole squad initially gains 500/1,500 Decibels upon entering combat.',
   'modificadores_es', 'Con 2/3 agentes de especialidad Anomalía en el escuadrón, el daño de Anomalía de Atributo aumenta 10 %/60 % y el escuadrón entra al combate con 500/1 500 decibelios.',
   'score_tope', 50000, 'score_S', 25000),
  json_object('frente', 5, 'sala', 3, 'jefe', lo.id,
   'oleadas', json_array(
      json_array(json_object('id', lr.id, 'n', 1), json_object('id', sg.id, 'n', 2), json_object('id', ca.id, 'n', 2)),
      json_array(json_object('id', lo.id, 'n', 1))),
   'elemento_recomendado', json_array('electrico', 'fisico'),
   'resistencia_enemigo_poderoso', json_array('eter'),
   'modificadores_en', 'Agent DEF increases by 15%, and attacks against enemies ignore 20% of their Electric RES. After an Agent uses EX Special Attack, their CRIT Rate increases by 5% and CRIT DMG increases by 20% for 15s.',
   'modificadores_es', 'DEF de los agentes +15 % y los ataques ignoran 20 % de la RES Eléctrica. Tras usar un Ataque Especial EX, el agente gana CRÍT +5 % y Daño CRÍT +20 % por 15 s.',
   'score_tope', 50000, 'score_S', 25000)
 ),
 'game8',
 'Shiyu V2 (3.0+): Quinto Frente de 3 salas. S+ = S en todas las salas y total >= 100 000 (pantalla). '
 || 'Oleadas y buffos: Game8. Atributos recomendados y resistencia del enemigo poderoso: pantalla 2026-09-18. '
 || 'Fechas inferidas de Game8 (reset viernes por medio). Fase Prydwen 3.2.1. cycle_number = numeración interna.'
FROM enemies t, enemies gr, enemies pu, enemies vs, enemies se, enemies fm, enemies tr,
     enemies lo, enemies lr, enemies sg, enemies ca
WHERE t.nombre_en = 'Tepes' AND gr.nombre_en = 'Corrupted Bandit - Greedy Ranger'
  AND pu.nombre_en = 'Ionized - Pugnus' AND vs.nombre_en = 'Corrupted Bandit - Vicious Striker'
  AND se.nombre_en = 'Autonomous Assault Unit - Airspace Sentinel'
  AND fm.nombre_en = 'Miasmic - Frenzied Maniac' AND tr.nombre_en = 'Miasmic - Trinox'
  AND lo.nombre_en = 'Lockspring' AND lr.nombre_en = 'Autonomous Support Unit - Lightfoot Rover MK II'
  AND sg.nombre_en = 'Miasmic Trooper - Shieldguard' AND ca.nombre_en = 'Miasmic Trooper - Cannoneer';

COMMIT;

-- ---------------------------------------------------------------------------- smoke checks
-- 12 seed de abril + 11 nuevos.
SELECT COUNT(*) AS expected_23 FROM enemies;

-- Los 11 nuevos tienen stats completos; los 12 viejos quedan con las columnas nuevas en NULL.
SELECT COUNT(*) AS expected_11 FROM enemies
 WHERE atk_base IS NOT NULL AND def_base IS NOT NULL AND daze_base IS NOT NULL
   AND stun_duracion_s IS NOT NULL AND stun_dmg_mult IS NOT NULL AND hp_base IS NOT NULL;

-- 6 atributos × 11 enemigos, sin frost ni lumen.
SELECT COUNT(*) AS expected_66 FROM enemy_resistances r JOIN enemies e ON e.id = r.enemy_id
 WHERE e.atk_base IS NOT NULL;
SELECT COUNT(*) AS expected_0 FROM enemy_resistances r JOIN enemies e ON e.id = r.enemy_id
 WHERE e.atk_base IS NOT NULL AND r.elemento IN ('frost', 'lumen');

-- Lo que dice la PANTALLA, verificado en la DB: el Centinela resiste sólo Éter (Físico neutral),
-- Tepes no resiste nada, Cerrosorte sólo Éter.
SELECT COUNT(*) AS expected_1 FROM enemy_resistances r JOIN enemies e ON e.id = r.enemy_id
 WHERE e.nombre_en = 'Autonomous Assault Unit - Airspace Sentinel' AND r.breakdown_status = 'resistant';
SELECT COUNT(*) AS expected_0 FROM enemy_resistances r JOIN enemies e ON e.id = r.enemy_id
 WHERE e.nombre_en = 'Tepes' AND r.breakdown_status = 'resistant';
SELECT COUNT(*) AS expected_1 FROM enemy_resistances r JOIN enemies e ON e.id = r.enemy_id
 WHERE e.nombre_en = 'Lockspring' AND r.breakdown_status = 'resistant' AND r.elemento = 'eter';

-- El ciclo: 1 fila, 3 salas, ningún jefe sin resolver.
SELECT COUNT(*) AS expected_1 FROM shiyu_cycles;
SELECT json_array_length(frentes) AS expected_3 FROM shiyu_cycles WHERE cycle_number = 1;
SELECT COUNT(*) AS expected_0 FROM shiyu_cycles c, json_each(c.frentes) s
 WHERE json_extract(s.value, '$.jefe') IS NULL;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

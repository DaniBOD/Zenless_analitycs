-- =============================================================================
-- Stats fijos por PJ · 2026-09-25 · migración 45
-- =============================================================================
-- Caso 14 (SPEC). El motor sugirió #151 (N.º 0: Anby → Gatillo): +1,06 por Daño Crítico, pero le
-- bajaba a Gatillo 7,2 puntos de Prob. Crítica. Daniel: "tiene en la pasiva más impacto a cuanta
-- más probabilidad tenga"; y generalizó: "podemos tener intervalos de stats pero algunos PJ
-- requieren un stat fijo para aprovechar todo su potencial, como Astra Yao y Zhao, que requieren
-- de cierto ATK (Astra) y HP (Zhao) para lograr aportar el buff de sus pasivas al resto del equipo".
--
-- Un STAT FIJO es el valor que un PJ tiene que tener para que una pasiva (o el 4pc de su build)
-- rinda completa. Distinto de un rango (`agent_thresholds`, `ajustes_usuario_rangos`), que es un
-- borde blando ("rinde menos"): bajo el fijo el kit PIERDE efecto, y de ahí para arriba no suma más
-- a esa pasiva. R21: el motor no sugiere un cambio que deje al PJ por debajo de su stat fijo
-- bajándoselo.
--
-- Cada fila trae la cuenta (`cuenta`) y la fuente. Los textos del kit son de Prydwen con la pasiva
-- núcleo en su nivel máximo (Lv. 7), leídos el 2026-09-25; la cuenta es propia. `stat` usa el
-- vocabulario de `agents` (lo que lee S18): el valor es de la pantalla de atributos ("inicial").
-- `requiere_set_4p_id`: la fila vale sólo si el 4pc del build objetivo del PJ es ese set.
--
-- Fuera de esta migración, a propósito (no son un "fijo"): umbrales sin tope que suman lineal
-- (Alice AM > 140, Nangong Yu AM > 110), conversiones sin umbral (Manato/Yixuan/Billy Estelar HP →
-- Fuerza bruta), la RE de Cissia (1,4 + 3,0 = 4,4: inalcanzable en la práctica) y la de Burnice
-- (el texto leído viene con un "6" delante: puede ser de su Mindscape 6; se verifica aparte).
-- Lucy depende del nivel de su Especial (no se captura). Harumasa "75 %, no más" es un techo.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE pj_stats_fijos (
    agente_id          INTEGER NOT NULL REFERENCES agents(id),
    stat               TEXT    NOT NULL CHECK (stat IN ('prob_critico', 'ataque', 'pv', 'impacto',
                                  'tasa_anomalia', 'maestria_anomalia', 'tasa_perforacion', 'rec_energia')),
    objetivo           REAL    NOT NULL,
    requiere_set_4p_id INTEGER REFERENCES disc_sets(id),
    cuenta             TEXT    NOT NULL,
    fuente             TEXT    NOT NULL,
    url                TEXT    NOT NULL,
    capturado          DATE    NOT NULL,
    UNIQUE (agente_id, stat, requiere_set_4p_id)
);

INSERT INTO pj_stats_fijos (agente_id, stat, objetivo, cuenta, fuente, url, capturado)
WITH v(nombre, stat, objetivo, cuenta, url) AS (VALUES
  ('Gatillo',   'prob_critico',     90,   'Hab. adicional: +1,5 % de aturdimiento de réplicas por cada 1 % de Prob. Crítica sobre 40 %, hasta +75 % → 40 + 75/1,5 = 90', 'https://www.prydwen.gg/zenless/characters/trigger'),
  ('Evelyn',    'prob_critico',     55,   'Hab. adicional: Cadena y Definitiva ×1,25 con Prob. Crítica ≥ 80 % en combate, y su pasiva núcleo da 25 % → 55 % en la pantalla (nota de la guía)', 'https://www.prydwen.gg/zenless/characters/evelyn'),
  ('Dialyn',    'prob_critico',     100,  'Prob. Crítica inicial sobre 50 %: +2 de Impacto por cada 1 %, hasta +100 → 50 + 100/2 = 100', 'https://www.prydwen.gg/zenless/characters/dialyn'),
  ('Miyabi',    'prob_critico',     80,   'Acumulación de Congelación +100 % de su Prob. Crítica, hasta +80 % → 80', 'https://www.prydwen.gg/zenless/characters/miyabi'),
  ('Rina',      'tasa_perforacion', 72,   'Núcleo Lv. 7: al equipo 25 % de su Tasa de Perforación + 12 %, hasta 30 % → (30 − 12)/0,25 = 72, y 8 ATK por 1 %, hasta 576 → 72', 'https://www.prydwen.gg/zenless/characters/rina'),
  ('Astra Yao', 'ataque',           3429, 'Núcleo Lv. 7: ATK +35 % de su ATK inicial, hasta 1.200 → 1.200/0,35 = 3.428,6', 'https://www.prydwen.gg/zenless/characters/astra-yao'),
  ('Zhao',      'pv',               27000,'Hab. adicional: daño del equipo +10 %, +1 % por cada 400 PV iniciales sobre 15.000, hasta 40 % → 15.000 + 30 × 400 = 27.000', 'https://www.prydwen.gg/zenless/characters/zhao'),
  ('Seth',      'ataque',           3750, 'Escudo = 80 % de su ATK inicial, hasta 3.000 → 3.000/0,8 = 3.750', 'https://www.prydwen.gg/zenless/characters/seth'),
  ('Soukaku',   'ataque',           2500, 'Núcleo Lv. 7: ATK +20 % hasta 500 (doble con Vórtice: 40 % hasta 1.000) → 2.500', 'https://www.prydwen.gg/zenless/characters/soukaku'),
  ('Sunna',     'ataque',           1750, 'Núcleo Lv. 7: "cuando el ATK inicial de Sunna llega a 1.750, el buff de ATK al equipo es máximo"', 'https://www.prydwen.gg/zenless/characters/sunna'),
  ('Remielle Dan','ataque',         4000, 'Con 3 PJs de Anomalía: ATK del equipo +40 % de su ATK inicial, hasta 1.600 → 4.000', 'https://www.prydwen.gg/zenless/characters/remielle'),
  ('Yuzuha',    'ataque',           3000, '"Si el ATK inicial de Yuzuha llega a 3.000, da el bono de ATK completo" (40 %, hasta 1.200)', 'https://www.prydwen.gg/zenless/characters/ukinami-yuzuha'),
  ('Yuzuha',    'tasa_anomalia',    200,  'Maestría de Anomalía sobre 100: +0,2 % por punto, hasta 20 % → 100 + 20/0,2 = 200', 'https://www.prydwen.gg/zenless/characters/ukinami-yuzuha'),
  ('Ju Fufu',   'ataque',           3400, 'ATK inicial ≥ 2.800: +5 % de Daño Crítico por cada 100, hasta +30 % → 2.800 + 6 × 100 = 3.400', 'https://www.prydwen.gg/zenless/characters/ju-fufu'),
  ('Qingyi',    'impacto',          220,  'Impacto sobre 120: +6 ATK por punto, hasta 600 → 120 + 600/6 = 220', 'https://www.prydwen.gg/zenless/characters/qingyi'),
  ('Velina',    'rec_energia',      2.88, 'Núcleo Lv. 7: RE inicial sobre 1,2: por cada 0,01, +0,21 % de daño (hasta 35 %) y +0,5 de Maestría (hasta 84) → 1,2 + 1,68 = 2,88', 'https://www.prydwen.gg/zenless/characters/velina')
)
SELECT a.id, v.stat, v.objetivo, v.cuenta, 'prydwen', v.url, '2026-09-25'
FROM v JOIN agents a ON a.nombre = v.nombre;

-- 4pc Monarca del Pináculo: "si la Prob. Crítica es ≥ 50 %, +15 % extra" de Daño Crítico al equipo.
-- Vale para todo PJ cuya guía lista ese 4pc, y sólo mientras sea el 4pc de su build objetivo.
INSERT INTO pj_stats_fijos (agente_id, stat, objetivo, requiere_set_4p_id, cuenta, fuente, url, capturado)
SELECT p.agente_id, 'prob_critico', 50, p.set_id,
       '4pc Monarca del Pináculo: Daño Crítico del equipo +15 %, +15 % extra si la Prob. Crítica ≥ 50 %',
       'disc_sets + prydwen', 'https://www.prydwen.gg/zenless/characters/lycaon', '2026-09-25'
FROM pj_sets_4pc p JOIN disc_sets s ON s.id = p.set_id
WHERE s.nombre = 'Monarca del Pináculo';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;
SELECT COUNT(*) AS expected_16 FROM pj_stats_fijos WHERE requiere_set_4p_id IS NULL;

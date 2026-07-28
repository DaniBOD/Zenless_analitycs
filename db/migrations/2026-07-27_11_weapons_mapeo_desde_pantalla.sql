-- ============================================================================
-- Catálogo `weapons` — mapeo ES↔EN resuelto CON EL JUEGO COMO FUENTE
-- Fecha: 2026-07-27 · Segunda pasada (la primera: 2026-07-27_10)
--
-- Fuente primaria: 40 capturas del propio juego del usuario
--   Documentacion/Screenshots_Triggers/Engines_Triggers/Engine_vista_detallada_pj/
--   Lectura completa en audit/engines_lectura_pantalla_20260727.txt
-- Fuente de nombres EN / rareza / tipo: lista canónica de Game8 (RNF-02).
--
-- EL DISCRIMINANTE DE RAREZA. En las 40 muestras el "Ataque Base" a Nivel 60/60
-- separa las rarezas sin solaparse:  S ∈ {684, 713, 743} · A ∈ {594, 624}.
-- Eso destapó que el catálogo asignó **S de más** de forma sistemática — coherente
-- con una carga en bloque contra nombres EN equivocados. Cada corrección de acá
-- tiene DOS evidencias: el ATK observado y la traducción literal del nombre.
--
-- NO SE TOCA lo que no se pudo ver o queda ambiguo (RNF-02). Detalle al final.
-- ============================================================================

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- A. Mapeos corregidos — el nombre ES es una traducción literal del EN real,
--    y el ATK observado confirma la rareza.
-- ---------------------------------------------------------------------------

-- id 6 · 594 ⇒ A · "Proyector de celuloide" = proyector de bobina.
UPDATE weapons SET nombre_en='Reel Projector', rareza='A', tipo_especialidad='Defensa',
       atk_base=594, stat_secundario='Impact', stat_secundario_valor='15%'
 WHERE id=6 AND nombre='Proyector de celuloide';

-- id 9 · 594 ⇒ A · "Lapso de tiempo" = porción/lapso de tiempo.
UPDATE weapons SET nombre_en='Slice of Time', rareza='A', tipo_especialidad='Soporte',
       atk_base=594, stat_secundario='PEN Ratio', stat_secundario_valor='20%'
 WHERE id=9 AND nombre='Lapso de tiempo';

-- id 15 · 594 ⇒ A · "Transmorfer original" = Original Transmorpher, literal.
UPDATE weapons SET nombre_en='Original Transmorpher', rareza='A', tipo_especialidad='Defensa',
       atk_base=594, stat_secundario='HP%', stat_secundario_valor='25%'
 WHERE id=15 AND nombre='Transmorfer original';

-- id 17 · 594 ⇒ A · "Anhelo marcato" = Marcato Desire, literal.
UPDATE weapons SET nombre_en='Marcato Desire', rareza='A', tipo_especialidad='Ataque',
       atk_base=594, stat_secundario='CRIT Rate', stat_secundario_valor='20%'
 WHERE id=17 AND nombre='Anhelo marcato';

-- id 34 · 624 ⇒ A · "Amo de llaves" = ama de llaves / housekeeper.
UPDATE weapons SET nombre_en='Housekeeper', rareza='A', tipo_especialidad='Ataque',
       atk_base=624, stat_secundario='ATK%', stat_secundario_valor='25%'
 WHERE id=34 AND nombre='Amo de llaves';

-- ---------------------------------------------------------------------------
-- B. De las 13 filas con `nombre_en` inventado: las que el juego permitió resolver
-- ---------------------------------------------------------------------------

-- id 35 · 624 ⇒ A · el nombre real lleva guion.
UPDATE weapons SET nombre_en='Peacekeeper - Specialized', rareza='A', tipo_especialidad='Defensa',
       atk_base=624, stat_secundario='ATK%', stat_secundario_valor='25%'
 WHERE id=35 AND nombre='Pacificador especializado';

-- id 38 · 624 ⇒ A · "Cúter" = cutter; su atributo avanzado es Impacto ⇒ Aturdimiento
--         (el catálogo lo tenía como Ataque).
UPDATE weapons SET nombre_en='Box Cutter', rareza='A', tipo_especialidad='Aturdimiento',
       atk_base=624, stat_secundario='Impact', stat_secundario_valor='15%'
 WHERE id=38 AND nombre='Cúter';

-- id 41 · 624 ⇒ A · el nombre in-game completo es "…- Eje rojo" (Red Axis); el
--         catálogo lo tenía truncado.
UPDATE weapons SET nombre='Taladradora giratoria - Eje rojo', nombre_en='Drill Rig - Red Axis',
       rareza='A', tipo_especialidad='Ataque', atk_base=624,
       stat_secundario='Energy Regen', stat_secundario_valor='50%'
 WHERE id=41 AND nombre='Taladradora giratoria - Eje';

-- id 49 · 624 ⇒ A · atributo avanzado Recuperación de Energía ⇒ Soporte.
UPDATE weapons SET nombre_en='Kaboom the Cannon', rareza='A', tipo_especialidad='Soporte',
       atk_base=624, stat_secundario='Energy Regen', stat_secundario_valor='50%'
 WHERE id=49 AND nombre='Cañón bombástico';

-- id 51 · 594 ⇒ A · "Florescencia aurífera" = floración dorada.
UPDATE weapons SET nombre_en='Gilded Blossom', rareza='A', tipo_especialidad='Ataque',
       atk_base=594, stat_secundario='ATK%', stat_secundario_valor='25%'
 WHERE id=51 AND nombre='Florescencia aurífera';

-- id 52 · 594 ⇒ A · "Gastrónomo selvático" = gourmet de selva.
UPDATE weapons SET nombre_en='Rainforest Gourmet', rareza='A', tipo_especialidad='Anomalía',
       atk_base=594, stat_secundario='Anomaly Mastery', stat_secundario_valor='75'
 WHERE id=52 AND nombre='Gastrónomo selvático';

-- ---------------------------------------------------------------------------
-- C. Altas — vistas en pantalla y ausentes del catálogo.
--    Todas a Nivel 0/10 ⇒ `atk_base` (que es el valor a nivel 60) va NULL, igual
--    que el valor del secundario. Se completan cuando la extracción las vea al máximo.
-- ---------------------------------------------------------------------------
INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor, pasiva_modelada) VALUES
  ('Tormenta magnética - Charlie', 'Magnetic Storm - Charlie', 'B', 'Anomalía', NULL,
   'PEN Ratio', NULL, 0),
  ('Fase lunar - Plenilunio',      'Lunar - Pleniluna',        'B', 'Ataque',   NULL,
   'ATK%', NULL, 0),
  ('Turbulencia - Flecha',         'Vortex - Arrow',           'B', 'Aturdimiento', NULL,
   'Impact', NULL, 0),
  ('Turbulencia - Hacha',          'Vortex - Hatchet',         'B', 'Aturdimiento', NULL,
   'Energy Regen', NULL, 0),
  ('Repercusión - Modelo II',      'Reverb - Mark II',         'B', 'Soporte',  NULL,
   'Energy Regen', NULL, 0);

COMMIT;

-- ---------------------------------------------------------------------------
-- SIN TOCAR, y por qué (RNF-02)
-- ---------------------------------------------------------------------------
--  · id 5  "Última cena"      → observado 594 ⇒ A, pero The Restrained es S: el mapeo
--                               está mal y no hay candidato claro. Queda como estaba.
--  · id 13 "Caldero ardiente" → mismo caso (594 ⇒ A vs Roaring Fur-nace S).
--  · id 27 "Aguijón afilado" vs id 46 "Aguijón agudo" → PROBABLE DUPLICADO. La captura
--    muestra "Aguijón agudo" a 713/S con Maestría 90 = Sharpened Stinger, que id 27 ya
--    reclama. Fusionar filas toca `inventory_weapons`: decisión del usuario, no mía.
--  · id 47 "Hellfire Gears" vs id 48 "Engranaje infernal" → mismo caso. La captura
--    muestra "Engranaje infernal" a 684/S con Impacto 18 % = Hellfire Gears (S).
--  · id 37 "Primavera termal", id 42 "Cilindro neumático", id 44 "Demonio cohibido",
--    id 53 "Tránsito herciano" → no aparecen en las capturas; sin evidencia no se tocan.

PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT COUNT(*) AS expected_11 FROM weapons
 WHERE nombre_en IN ('Reel Projector','Slice of Time','Original Transmorpher','Marcato Desire',
                     'Housekeeper','Peacekeeper - Specialized','Box Cutter','Drill Rig - Red Axis',
                     'Kaboom the Cannon','Gilded Blossom','Rainforest Gourmet');
SELECT COUNT(*) AS expected_5 FROM weapons
 WHERE nombre_en IN ('Magnetic Storm - Charlie','Lunar - Pleniluna','Vortex - Arrow',
                     'Vortex - Hatchet','Reverb - Mark II');
SELECT COUNT(*) AS expected_61 FROM weapons;
SELECT COUNT(*) AS expected_0 FROM weapons WHERE rareza='S' AND atk_base IN (594, 624);

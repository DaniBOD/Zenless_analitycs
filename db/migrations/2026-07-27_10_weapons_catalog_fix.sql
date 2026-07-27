-- ============================================================================
-- Corrección del catálogo `weapons` — solo lo VERIFICABLE
-- Fecha: 2026-07-27 · Fuente: Game8 (lista canónica de W-Engines, autorizada por
-- CLAUDE.md RNF-02) + capturas del juego del propio usuario (Engines_Triggers).
--
-- Auditoría completa: audit/weapons_catalog_audit_20260727.md
--
-- ALCANCE DELIBERADAMENTE ACOTADO (RNF-02). El catálogo tiene 13 filas cuyo
-- `nombre_en` no existe en el juego — desambiguaciones hechas a mano
-- (`Hellfire Gears S`, `Bashful Demon B`, `Sharp Stinger A`, …). En esas filas la
-- rareza tampoco es confiable: se dedujo de un match contra un arma inexistente.
-- NO se tocan acá: corregirlas exige saber a qué W-Engine corresponde cada nombre
-- ESPAÑOL, y el único lugar donde ese dato es autoritativo es el juego del usuario.
-- La extracción de S17 (RF-15) lo va a leer; esta migración no adivina.
-- ============================================================================

BEGIN TRANSACTION;

-- ---------------------------------------------------------------------------
-- A. Rarezas y tipos con mapeo ES↔EN inequívoco (traducción literal, sin colisión)
-- ---------------------------------------------------------------------------

-- Starlight Engine es rango A. La versión Réplica (id 36) ya figura A y es otra arma.
UPDATE weapons SET rareza = 'A' WHERE id = 7 AND nombre_en = 'Starlight Engine';

-- Puzzle Sphere: A y de especialidad Ruptura (el catálogo decía S/Ataque).
UPDATE weapons SET rareza = 'A', tipo_especialidad = 'Ruptura'
 WHERE id = 8 AND nombre_en = 'Puzzle Sphere';

-- Cannon Rotor es rango A.
UPDATE weapons SET rareza = 'A' WHERE id = 11 AND nombre_en = 'Cannon Rotor';

-- Street Superstar es rango A (el catálogo decía B, pero su atk_base 594 ya era de A).
UPDATE weapons SET rareza = 'A' WHERE id = 50 AND nombre_en = 'Street Superstar';

-- ---------------------------------------------------------------------------
-- B. Mapeo corregido con TRIPLE corroboración
-- ---------------------------------------------------------------------------
-- `Fósil preciado` estaba mapeado a `Practiced Perfection` (S · Anomalía · 713).
-- Tres señales independientes dicen que es `Precious Fossilized Core` (A · Aturdimiento):
--   1. la captura del usuario muestra el badge de rareza **A**;
--   2. su atributo avanzado es **Impacto 15 %** — Impacto es el stat de Aturdimiento;
--   3. su Ataque Base a Nivel 60/60 es **594**, el máximo de rango A (el de S es 713).
-- Fuente de la captura: Engines_Triggers/Engine_vista_detallada_pj/Ejemplo_2.png
UPDATE weapons
   SET nombre_en = 'Precious Fossilized Core',
       rareza = 'A',
       tipo_especialidad = 'Aturdimiento',
       atk_base = 594,
       stat_secundario = 'Impact',
       stat_secundario_valor = '15%'
 WHERE id = 12 AND nombre = 'Fósil preciado';

-- ---------------------------------------------------------------------------
-- C. Altas — W-Engines vistos en el juego del usuario y ausentes del catálogo
-- ---------------------------------------------------------------------------
-- Nombre ES: leído de la captura. Nombre EN, rareza y tipo: lista canónica.
-- `atk_base` documentado como "ATK base al nivel 60": solo se carga cuando la
-- captura muestra el arma a nivel 60/60. Si no, va NULL (RNF-02: antes NULL que inventado).

-- Ejemplo_6: badge S, Nivel 60/60, Ataque Base 713, Ataque 30 %.
INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor, pasiva_modelada)
VALUES ('Sol exuvia', 'Sol Exuvia', 'S', 'Ataque', 713, 'ATK%', '30%', 0);

-- Ejemplo_1: badge A, Nivel 60/60, Ataque Base 594, Maestría de Anomalía 75.
INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor, pasiva_modelada)
VALUES ('Ecos bulliciosos', 'Boisterous Echoes', 'A', 'Anomalía', 594,
        'Anomaly Mastery', '75', 0);

-- Ejemplo_4: Nivel 0/10 — el ATK 32 y el PV 8 % son de nivel 0, NO del 60.
-- Por eso atk_base y el valor del secundario quedan NULL: se completan cuando la
-- extracción lo vea a nivel máximo.
INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor, pasiva_modelada)
VALUES ('Repercusión - Modelo III', 'Reverb - Mark III', 'B', 'Soporte', NULL,
        'HP%', NULL, 0);

COMMIT;

-- ---------------------------------------------------------------------------
-- Smoke checks — cada SELECT debe devolver exactamente su `expected_N`
-- ---------------------------------------------------------------------------
PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE id IN (7, 11, 50) AND rareza <> 'A';

SELECT COUNT(*) AS expected_1 FROM weapons
 WHERE id = 8 AND rareza = 'A' AND tipo_especialidad = 'Ruptura';

SELECT COUNT(*) AS expected_1 FROM weapons
 WHERE nombre = 'Fósil preciado' AND nombre_en = 'Precious Fossilized Core'
   AND rareza = 'A' AND tipo_especialidad = 'Aturdimiento' AND atk_base = 594;

SELECT COUNT(*) AS expected_3 FROM weapons
 WHERE nombre IN ('Sol exuvia', 'Ecos bulliciosos', 'Repercusión - Modelo III');

SELECT COUNT(*) AS expected_56 FROM weapons;

-- Ninguna de las 13 filas de mapeo roto fue tocada: siguen como estaban.
SELECT COUNT(*) AS expected_13 FROM weapons
 WHERE nombre_en IN ('Peacekeeper Specialized A', 'Hot Spring', 'Cutter',
                     'Drill Rig Axis', 'Pneumatic Cylinder', 'Bashful Demon B',
                     'Sharp Stinger A', 'Hellfire Gears S', 'Hellfire Gears A',
                     'Cannonrotor', 'Golden Bloom', 'Wild Gastronome', 'Hertz Transit');

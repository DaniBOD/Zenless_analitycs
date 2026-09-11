-- =============================================================================
-- 2026-09-10_27 · weapons: las dos armas que DE VERDAD faltaban
-- =============================================================================
-- El censo del 2026-09-08 listó 6 armas "fuera de catálogo". Medido contra las
-- 59 filas de `weapons`, 4 ya estaban: el OCR les pegó texto del arte del arma o
-- les comió espacios, y el fuzzy (corte 0.84) no las alcanzó.
--
--     leído en pantalla               ya existe como              ratio
--     Anhelomarcato DESRE          -> Anhelo marcato (17)          0.788   ← "DESIRE" del arte
--     Viajeestruendoso CRASH       -> Viaje estruendoso (40)       0.821   ← texto del arte
--     Cilindroneumatico de Bigger  -> Cilindro neumático (42)      0.756
--     Temploala granizadaestelifera-> Templo a la granizada (2)    0.760   ← ATK 743 y CRIT 24% idénticos
--
-- Darlas de alta habría creado DUPLICADOS. Su problema es de matching, no de
-- catálogo, y va aparte. Detalle en `audit/weapons_catalog_20260910.md`.
--
-- ## De dónde sale cada valor (RNF-02: lo que no se leyó, va NULL)
--
-- Todo sale de lecturas de S30 en `app.log`, no de una wiki: `weapons.nombre` es
-- el nombre ESPAÑOL de pantalla, el dato que ninguna fuente accesible publica.
--
--   Inocencia sacrificada — 6 lecturas (3 limpias + 3 con el glifo `X`), todas
--     iguales: S · Nv 60/60 · ATK base 713 · Daño Crítico 48 % · de N.º 0: Anby.
--     Nivel máximo ⇒ el ATK y el valor del stat SON los de nivel 60.
--
--   Tetera esmeraldina — 1 lectura: S · Nv 50/50 · ATK base 595 · Impacto 15.8 %
--     · de Qingyi. Nv 50 NO es el máximo: esos 595 y ese 15.8 % son los de nivel
--     50, y `atk_base` está definida como "al nivel 60". Van NULL. El NOMBRE del
--     stat sí es fijo por arma, así que se guarda.
--
-- ## Lo que queda NULL a propósito, en las dos
--
--   nombre_en          regla del catálogo (audit 2026-07-28): sólo si la traducción es
--                      palabra por palabra y verificada; si no, NULL. No se verificó.
--   tipo_especialidad  el parser no lee el ícono de especialidad del panel.
--   pasiva_*           el "Efecto de amplificador" está en pantalla pero no se extrae.
--
-- `weapons` no tiene columna de notas: la marca de tentativo vive en el audit.
-- Los nombres de stat van en inglés, como el resto del catálogo (`CRIT DMG`, `Impact`).
-- =============================================================================

BEGIN TRANSACTION;

INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor)
VALUES ('Inocencia sacrificada', NULL, 'S', NULL, 713, 'CRIT DMG', '48%');

INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad, atk_base,
                     stat_secundario, stat_secundario_valor)
VALUES ('Tetera esmeraldina', NULL, 'S', NULL, NULL, 'Impact', NULL);

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_61 FROM weapons;
SELECT COUNT(*) AS expected_2 FROM weapons
 WHERE nombre IN ('Inocencia sacrificada', 'Tetera esmeraldina');
-- Los 4 falsos huecos NO pueden haber entrado: ya existen con su nombre real.
SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE nombre IN ('Anhelomarcato DESRE', 'Viajeestruendoso CRASH',
                  'Cilindroneumatico de Bigger', 'Temploala granizadaestelifera');
-- Lo que no se leyó a nivel 60 no se inventó.
SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE nombre = 'Tetera esmeraldina' AND (atk_base IS NOT NULL OR stat_secundario_valor IS NOT NULL);
PRAGMA foreign_key_check;
PRAGMA integrity_check;

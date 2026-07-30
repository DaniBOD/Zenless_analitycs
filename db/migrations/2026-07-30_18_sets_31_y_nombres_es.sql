-- Sets del patch 3.1 + los 4 nombres españoles que no eran los del juego
-- ============================================================================================
--
-- ## El hallazgo, medido
--
-- Se transcribieron los **30 sets** de la pantalla "Preferencia de disco · Género prioritario"
-- (capturas de Daniel, 2026-07-30) y se pasaron por el resolver real
-- (`DiscSetRepo.resolve_id`, cutoff 0.86). Resultado: **6 de 30 no resuelven.**
--
-- No es cosmético: un nombre que no resuelve hace que `sync_equip` descarte el disco
-- ("Set desconocido '%s' — disco descartado"). Era el **20 % del catálogo cayéndose en
-- silencio**, y solo se veía como una línea de WARNING suelta en el log.
--
-- Los otros 24 resuelven aunque difieran en mayúsculas o acentos ('Jazz Caótico' vs 'Jazz
-- caótico'), porque el resolver normaliza. Por eso acá **no se toca el casing**: sería churn
-- sin efecto.
--
-- ## A · Dos sets nuevos (3.1)
--
-- **Hado emplumado** y **Rosa espinosa**. El primero ya venía apareciendo en el log como
-- desconocido desde el 2026-07-30 12:44.
--
-- `nombre_en` y los bonuses van NULL (RNF-02): la wiki todavía no publicó estos sets. NO es un
-- pendiente por olvido — `nombre_en` es lo que resuelve el logo (`Set-Discos_Package_Logo/`
-- está en inglés), así que inventarlo apuntaría al ícono equivocado, que es exactamente el
-- defecto que hubo que limpiar en `weapons` (`audit/weapons_catalog_20260728.md`). Sin logo el
-- toast cae a placeholder, que es el comportamiento correcto mientras tanto.
--
-- ## B · Cuatro nombres españoles corregidos
--
-- Los cuatro se verificaron **por el logo** —el tile de la pantalla contra el package badge del
-- repo—, no por parecido de texto, que es justo lo que falló al armar el catálogo de armas:
--
--   · 'Notas encadenadas' → **Diario de una prisionera**  (abanico radial negro/azul)
--   · 'Aria brillante'    → **Aria radiante**             (disco rosa)
--   · 'Soul Rock'         → **Rock espiritual**           (naranja con lettering "AJYC")
--   · 'Polar Metal'       → **Metal polar**               (verde azulado)
--
-- Los dos últimos tenían el **nombre inglés en la columna española** — el mismo defecto que
-- tenían los ids 18 y 30 de `weapons`.
--
-- `nombre_en` NO se toca: sigue siendo correcto y es lo que resuelve el logo, así que el ícono
-- de los cuatro se mantiene. Las FK son por `id`, así que ningún `inventory_discs.set_id` se
-- mueve.

BEGIN TRANSACTION;

-- A · Sets nuevos del 3.1 -------------------------------------------------------------------
INSERT INTO disc_sets (nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc)
VALUES ('Hado emplumado', NULL, NULL, NULL, NULL),
       ('Rosa espinosa',  NULL, NULL, NULL, NULL);

-- B · Nombres españoles corregidos ----------------------------------------------------------
-- El WHERE incluye `nombre_en` para que la sentencia sea un no-op si alguien ya la aplicó o si
-- la fila no es la que se cree (en vez de renombrar la equivocada).
UPDATE disc_sets SET nombre = 'Diario de una prisionera'
 WHERE nombre = 'Notas encadenadas' AND nombre_en = 'Notes From the Chained';

UPDATE disc_sets SET nombre = 'Aria radiante'
 WHERE nombre = 'Aria brillante'    AND nombre_en = 'Shining Aria';

UPDATE disc_sets SET nombre = 'Rock espiritual'
 WHERE nombre = 'Soul Rock'         AND nombre_en = 'Soul Rock';

UPDATE disc_sets SET nombre = 'Metal polar'
 WHERE nombre = 'Polar Metal'       AND nombre_en = 'Polar Metal';

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks ------------------------------------------------------------------------------
SELECT COUNT(*) AS expected_30 FROM disc_sets;

SELECT COUNT(*) AS expected_2 FROM disc_sets
 WHERE nombre IN ('Hado emplumado', 'Rosa espinosa');

-- Los dos nuevos quedan SIN nombre_en a propósito (RNF-02), no por olvido.
SELECT COUNT(*) AS expected_2 FROM disc_sets WHERE nombre_en IS NULL;

SELECT COUNT(*) AS expected_4 FROM disc_sets
 WHERE nombre IN ('Diario de una prisionera', 'Aria radiante', 'Rock espiritual', 'Metal polar');

-- Los nombres viejos ya no existen.
SELECT COUNT(*) AS expected_0 FROM disc_sets
 WHERE nombre IN ('Notas encadenadas', 'Aria brillante', 'Soul Rock', 'Polar Metal');

-- El inglés se conservó, así que el logo de los cuatro renombrados sigue resolviendo.
SELECT COUNT(*) AS expected_4 FROM disc_sets
 WHERE nombre_en IN ('Notes From the Chained', 'Shining Aria', 'Soul Rock', 'Polar Metal');

-- Ningún disco del inventario quedó huérfano por el renombre (las FK son por id).
SELECT COUNT(*) AS expected_0 FROM inventory_discs d
 WHERE d.set_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM disc_sets s WHERE s.id = d.set_id);

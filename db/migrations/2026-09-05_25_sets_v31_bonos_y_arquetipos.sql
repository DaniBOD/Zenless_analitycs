-- =============================================================================
-- 2026-09-05_25 · disc_sets: bonos y arquetipos de los dos sets de la v3.1
-- =============================================================================
-- La migración `_24` les puso `nombre_en` (lo que destrabó el nodo de farmeo).
-- Seguían sin lo que usa el motor de scoring:
--
--     bonus_2p_stat / bonus_2p_valor  -> el toast muestra "2pc=-"
--     bonus_4p_desc                   -> idem
--     disc_set_archetype              -> 0 filas: el disco se puntúa SIN contexto
--                                        de set, o sea ignorando la mitad de su valor
--
-- No es teórico: ya hay 4 discos de `Hado emplumado` equipados en la DB.
--
-- ## Fuentes (RNF-02): dos, y coinciden en los cuatro valores
--
-- 1. LA PANTALLA (autoridad para la redacción). Capturas de la ficha "Información
--    de conjunto" del 2026-09-05, aportadas por Daniel:
--
--    Hado emplumado
--      2 pistas: Maestría de Anomalía +30 ptos.
--      4 pistas: Al entrar en el campo de batalla o al pasar a ser el personaje
--                activo, el portador obtiene la siguiente bonificación: la Maestría
--                de Anomalía aumenta en 50 ptos. Si el portador es del atributo
--                lumiflujo, el daño de Anomalía de Atributo infligido aumenta en un
--                15 % durante 15 s. Este efecto se mantiene activo incluso cuando el
--                portador no es el personaje activo.
--    Rosa espinosa
--      2 pistas: Defensa +16 %.
--      4 pistas: El daño infligido por el portador aumenta en un 15 %. Si la Defensa
--                inicial del portador es igual o superior a 1000/1800 ptos., la
--                Probabilidad de Crítico aumenta en un 8/16 %.
--
-- 2. WIKIS (verificación de los números): Game8 611636 / 611637, corroborado por
--    Fandom e Icy Veins. Los cuatro valores coinciden con la pantalla.
--
-- ## Dos decisiones de redacción
--
-- · `lumiflujo` es el RÓTULO DE PANTALLA; el canónico del proyecto es **Lumen**
--   (`agents.elemento`, Remielle Dan). El rótulo de pantalla nunca es el canónico
--   — misma lección que dejó "Lumiflujo" fuera del vocabulario. Va `Lumen`.
--
-- · AMBIGÜEDAD que no se resuelve inventando: en español, el "durante 15 s" queda
--   pegado a la cláusula de lumiflujo, así que podría leerse como que sólo el +15 %
--   dura 15 s. Game8 es explícito en que los 15 s cubren el buff entero ("they gain
--   a buff for 15s: Anomaly Proficiency increases by 50, and if..."), y el español
--   no lo contradice. Se escribe con esa lectura y queda anotado acá: si algún día
--   importa la diferencia, esto es lo que hay que volver a mirar en pantalla.
--
-- ## Arquetipos: por PRECEDENTE, no por criterio propio
--
--   `Anomaly Proficiency +30` -> ANOMALY(p1)   ya lo tienen Jazz Caótico y Blues Libre
--   `DEF +16%`                -> DEFENSE(p1)   ya lo tiene Rock espiritual
--
-- Los dos 4pc lo respaldan (buff de MdA; crítico que escala con DEF). Rosa espinosa
-- podría además llevar ATK_DPS secundario por el "+15 % de daño", pero Rock
-- espiritual —mismo 2pc— está sólo como DEFENSE: se sigue el precedente.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

SELECT 'ANTES' AS momento, id, nombre, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc
  FROM disc_sets WHERE id IN (54, 55) ORDER BY id;

BEGIN TRANSACTION;

UPDATE disc_sets
   SET bonus_2p_stat = 'Anomaly Proficiency',
       bonus_2p_valor = '+30',
       bonus_4p_desc = 'Al entrar al campo o pasar a activo: Anomaly Proficiency +50 por 15s; si el equipador es Lumen, además Attribute Anomaly DMG +15%. El buff sigue activo off-field.'
 WHERE id = 54 AND nombre_en = 'Feathered Fate' AND bonus_2p_stat IS NULL;

UPDATE disc_sets
   SET bonus_2p_stat = 'DEF',
       bonus_2p_valor = '+16%',
       bonus_4p_desc = 'DMG del equipador +15%. Con DEF inicial ≥1000/1800: CRIT Rate +8%/16%.'
 WHERE id = 55 AND nombre_en = 'Thorned Rose' AND bonus_2p_stat IS NULL;

-- Arquetipos (3 = ANOMALY, 6 = DEFENSE). `INSERT OR IGNORE` para que re-aplicar la
-- migración no duplique filas: la tabla no tiene PK declarada.
INSERT OR IGNORE INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT 54, 3, 1 WHERE NOT EXISTS (SELECT 1 FROM disc_set_archetype WHERE set_id = 54);
INSERT OR IGNORE INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT 55, 6, 1 WHERE NOT EXISTS (SELECT 1 FROM disc_set_archetype WHERE set_id = 55);

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM disc_sets WHERE bonus_2p_stat IS NULL;
SELECT COUNT(*) AS expected_0 FROM disc_sets WHERE bonus_4p_desc IS NULL;
SELECT COUNT(*) AS expected_30 FROM (SELECT DISTINCT set_id FROM disc_set_archetype);
SELECT COUNT(*) AS expected_1 FROM disc_set_archetype WHERE set_id = 54 AND archetype_id = 3;
SELECT COUNT(*) AS expected_1 FROM disc_set_archetype WHERE set_id = 55 AND archetype_id = 6;
-- Ningún set con más de una fila de arquetipo primario.
SELECT COUNT(*) AS expected_0 FROM (
    SELECT set_id FROM disc_set_archetype WHERE prioridad = 1
     GROUP BY set_id HAVING COUNT(*) > 1);
-- Cómo queda, para que el log de la corrida lo muestre.
SELECT 'DESPUES' AS momento, s.id, s.nombre, s.bonus_2p_stat, s.bonus_2p_valor, a.code AS arquetipo
  FROM disc_sets s JOIN disc_set_archetype dsa ON dsa.set_id = s.id
  JOIN disc_archetypes a ON a.id = dsa.archetype_id
 WHERE s.id IN (54, 55) ORDER BY s.id;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

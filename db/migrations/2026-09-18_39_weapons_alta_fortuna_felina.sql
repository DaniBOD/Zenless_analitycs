-- =============================================================================
-- Alta de Fortuna felina (Catty Luck) · 2026-09-18 · migración 39
-- =============================================================================
-- El primer W-Engine de especialidad ARMERO del catálogo: el de Claret Flint. El censo del
-- 2026-09-17 lo vio como `Fortunafelina -01+` y lo reportó fuera de catálogo; es la única arma
-- que quedó en ese reporte. Lo equipa Claret, a Nv 50/50 y P5.
--
-- Va DESPUÉS de la 37 a propósito: estrena el catálogo con el atributo principal ya rotulado
-- (`stat_base_tipo = 'DEF'`). Antes de la 37 su 356 habría entrado a una columna llamada
-- `atk_base`. (La 38 es de otra sesión —enemigos y Shiyu— y no toca `weapons`.)
--
-- ## De dónde sale cada valor (RNF-02)
--
--   nombre                'Fortuna felina'  PANTALLA (captura local Engines_Triggers/
--                                           Engine_vista_detallada_pj/Ejemplo_50.png) y Gachabase
--                                           13017 con lang=es: idénticos.
--   nombre_en             'Catty Luck'      Gachabase 13017 (misma ficha, lang=en) y Game8. La regla
--                                           del catálogo (mig 33) pide dos fuentes: están, y además
--                                           la pasiva coincide número por número (abajo). Es
--                                           load-bearing: `engine_icon_path` busca el ícono por el
--                                           nombre inglés y sin él se abstiene.
--   rareza                'A'               PANTALLA (badge) · Gachabase · Game8.
--   tipo_especialidad     'Armero'          PANTALLA: el efecto dice "Si el portador es un agente
--                                           Armero" · Gachabase ("Armero") · Game8 ("Armorer").
--                                           Mismo vocabulario que `agents.rol` (mig 35).
--   stat_base_tipo        'DEF'             PANTALLA: "Defensa Base" · Gachabase · Game8.
--   stat_base_valor       356               NIVEL 60, que es lo que guarda el catálogo. La pantalla
--                                           dice 297 porque el arma está a Nv 50/50: ese número
--                                           NO es el del catálogo (precedente: Tetera esmeraldina,
--                                           mig 27). 356 sale de Gachabase y Game8, que coinciden.
--                                           Un tweet decía 342: es la única fuente que discrepa.
--                                           Chequeo interno: 297/356 = 0,834, y Tetera esmeraldina
--                                           leyó 595 a 50/50 contra el 713 de una S a 60: 0,834.
--                                           La misma curva, con datos que no se tocan entre sí.
--   stat_secundario       'DEF%'  '40%'     Nivel 60: Gachabase ("Porcentaje de Defensa 40 %") y
--                                           Game8. La pantalla, a nivel 50, dice 35,2 %.
--   pasiva_*                                PANTALLA (efecto a P5: 12 % y 12 % adicional, 40 s) ·
--                                           Gachabase (R1: 8 % y 8 % adicional, 40 s) · Game8
--                                           ("Lucky Pawpad", 8 % a 1★ → 12 % a 5★). Coinciden las
--                                           tres. Se describe R1 y R5 explícitos, para no dejar
--                                           ambiguo de qué refinamiento es el número.
--   pasiva_modelada       0                 El scoring no la modela.
--
-- ## Lo que NO hace
--
--   · NO inserta la fila de INVENTARIO. Esa la escribe la app por el flujo normal la próxima vez
--     que pase por S30 (decisión de Daniel en el onboarding de Claret): el nombre roto de S30,
--     `Fortunafelina -01+`, ya matchea 'Fortuna felina' por el fuzzy (verificado con
--     `match_catalogo`), y el dueño lo lee la superficie de badges — no se escribe a mano lo que
--     la app sabe leer.
--   · NO toca `pj_weapon_synergy` ni el scoring de armas.
--
-- ## Una corrección a la migración 37
--
--   La 37 llamó "invariante" a que el tipo del stat base esté EXACTAMENTE cuando está el valor.
--   Es falso como regla: el TIPO es una propiedad del arma (la etiqueta no cambia con el nivel) y el
--   VALOR del catálogo es el de nivel 60. Un arma leída sólo por debajo del máximo tiene tipo
--   conocido y valor NULL, y eso no miente: dice "sé qué stat es, no sé cuánto vale al 60". Lo que
--   SÍ es una mentira es lo contrario — un número sin decir qué stat es —, y ese es el smoke check
--   que vale (abajo). La 37 no se reescribe: es historia aplicada; se corrige acá.
-- =============================================================================

BEGIN TRANSACTION;

INSERT INTO weapons (nombre, nombre_en, rareza, tipo_especialidad,
                     stat_base_valor, stat_base_tipo, stat_secundario, stat_secundario_valor,
                     pasiva_tipo, pasiva_condicion, pasiva_valor, pasiva_descripcion,
                     pasiva_modelada)
VALUES ('Fortuna felina', 'Catty Luck', 'A', 'Armero',
        356, 'DEF', 'DEF%', '40%',
        'def_boost', 'always / on_ex_special',
        'DEF +8%; +8% adicional 40s al usar EX (R1) · +12% y +12% (R5)',
        'Sólo si el portador es Armero. Almohadillas de la suerte: la Defensa aumenta un 8 % '
        || '(12 % a R5). Al ejecutar la técnica especial EX, la Defensa aumenta un 8 % adicional '
        || '(12 % a R5) durante 40 s; la duración se reinicia con cada activación.',
        0);

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- =============================================================================
-- SMOKE CHECKS
-- =============================================================================

SELECT COUNT(*) AS expected_61 FROM weapons;
SELECT COUNT(*) AS expected_1 FROM weapons WHERE nombre = 'Fortuna felina';

-- La primera arma de Armero y el primer DEF base del catálogo: son la misma fila.
SELECT COUNT(*) AS expected_1 FROM weapons WHERE tipo_especialidad = 'Armero';
SELECT COUNT(*) AS expected_1 FROM weapons WHERE stat_base_tipo = 'DEF';
SELECT COUNT(*) AS expected_1 FROM weapons
 WHERE tipo_especialidad = 'Armero' AND stat_base_tipo = 'DEF' AND stat_base_valor = 356;

-- La pantalla leyó 297 a Nv 50/50: ese número NO puede haber entrado al catálogo, que es de Nv 60.
SELECT COUNT(*) AS expected_0 FROM weapons WHERE stat_base_valor = 297;

-- La regla que SÍ vale (ver la corrección a la 37): ningún número sin decir qué stat es.
SELECT COUNT(*) AS expected_0 FROM weapons
 WHERE stat_base_valor IS NOT NULL AND stat_base_tipo IS NULL;

-- Sin clave inglesa duplicada: `nombre_en` es la llave del ícono y dos filas con la misma
-- serían la misma arma dos veces (lo que pasó con Severed Innocence, mig 34).
SELECT COUNT(*) AS expected_1 FROM weapons WHERE nombre_en = 'Catty Luck';

-- El inventario NO se tocó: la fila de Claret la escribe la app al pasar por S30.
SELECT COUNT(*) AS expected_0 FROM inventory_weapons
 WHERE weapon_id = (SELECT id FROM weapons WHERE nombre = 'Fortuna felina');

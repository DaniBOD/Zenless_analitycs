-- =============================================================================
-- 2026-07-28_13 · weapons: fusión de duplicados + rarezas confirmadas por el usuario
-- =============================================================================
-- Tercera y última pasada del saneamiento del catálogo `weapons`.
--
-- Contexto: las pasadas 10 y 11 corrigieron rareza/tipo y resolvieron 6 de las 13
-- filas cuyo `nombre_en` no existía en el juego. Quedaban dos cosas que NO se podían
-- decidir sin el usuario, porque tocaban `inventory_weapons`:
--
--   1) dos pares de filas que parecían el MISMO W-Engine cargado dos veces,
--   2) dos filas cuya rareza medida en pantalla (ATK 594 ⇒ rango A) contradecía
--      la rareza del catálogo (S).
--
-- Daniel confirmó ambas cosas el 2026-07-28:
--   "aguijon y hellfire estan bien son duplicados, ultima cena y caldero ardiente
--    son rareza A no S, capaz los confundio"
--
-- REGLA DE ESTA MIGRACIÓN para el mapeo ES↔EN (para no repetir el pecado original
-- del catálogo, que fue emparejar por parecido):
--   · traducción PALABRA POR PALABRA  ⇒ se aplica.
--   · parecido semántico solamente    ⇒ NO se aplica: `nombre_en` va a NULL y la
--                                       hipótesis queda anotada en audit/, no en la DB
--                                       (RNF-02: dato no confirmado ⇒ NULL).
--
-- Fuente de los valores: las 40 capturas de detalle del propio juego
-- (Documentacion/Screenshots_Triggers/Engines_Triggers/Engine_vista_detallada_pj/)
-- + la lista canónica de Game8 embebida en tools/audit_weapons_catalog.py.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

BEGIN TRANSACTION;

-- -----------------------------------------------------------------------------
-- A. Fusión de duplicados
-- -----------------------------------------------------------------------------
-- En ambos pares, una fila tiene el nombre español REAL (el que se lee en la
-- pantalla del juego) y la otra tiene un nombre inventado por la carga original,
-- delatado por el sufijo artificial en `nombre_en` ("Sharp Stinger A",
-- "Hellfire Gears S"). Se conserva la fila con el nombre real —que además es la
-- única referenciada por inventory_weapons/agents— y se le corrigen los datos.
--
-- A.1 · Aguijón: id 27 "Aguijón afilado" (inventado) ⊂ id 46 "Aguijón agudo" (real).
--       Captura Ejemplo_10: Nivel 60/60 · ATK 713 · Maestría de Anomalía 90 ⇒ S.
UPDATE weapons
   SET nombre_en         = 'Sharpened Stinger',
       rareza            = 'S',
       tipo_especialidad = 'Anomalía',
       atk_base          = 713
 WHERE id = 46;

DELETE FROM weapons WHERE id = 27;

-- A.2 · Hellfire: id 47 "Hellfire Gears" (ni siquiera traducido al español)
--       ⊂ id 48 "Engranaje infernal" (real).
--       Captura Ejemplo_15: Nivel 60/60 · ATK 684 · Impacto 18 % ⇒ S.
UPDATE weapons
   SET nombre_en         = 'Hellfire Gears',
       rareza            = 'S',
       tipo_especialidad = 'Aturdimiento',
       atk_base          = 684
 WHERE id = 48;

DELETE FROM weapons WHERE id = 47;

-- -----------------------------------------------------------------------------
-- B. Rareza A confirmada por el usuario — mapeo EN descartado
-- -----------------------------------------------------------------------------
-- Ambas estaban apuntando a W-Engines de rango S. La captura las muestra a
-- Nivel 60/60 con ATK 594, que es el máximo del rango A (en las 40 muestras
-- S ∈ {684, 713, 743} y A ∈ {594, 624}, sin solape).
--
-- `tipo_especialidad` también se va a NULL: venía del mismo emparejamiento ahora
-- desmentido. Y NO se puede deducir del atributo avanzado — las capturas prueban
-- que el stat no determina la especialidad (Slice of Time es Soporte y muestra
-- Perforación; Peacekeeper - Specialized es Defensa y muestra Ataque).
--
-- B.1 · id 5 "Última cena" — era The Restrained (S/Aturdimiento).
--       Captura Ejemplo_29: 60/60 · 594 · Recuperación de Energía 50 %.
UPDATE weapons
   SET nombre_en         = NULL,
       rareza            = 'A',
       tipo_especialidad = NULL,
       atk_base          = 594
 WHERE id = 5;

-- B.2 · id 13 "Caldero ardiente" — era Roaring Fur-nace (S/Aturdimiento).
--       Captura Ejemplo_30: 60/60 · 594 · Impacto 15 %.
--       Candidatos A plausibles (The Simmering Pot, Steam Oven) son ambos
--       Aturdimiento, pero ninguno es traducción literal ⇒ no se elige.
UPDATE weapons
   SET nombre_en         = NULL,
       rareza            = 'A',
       tipo_especialidad = NULL,
       atk_base          = 594
 WHERE id = 13;

-- -----------------------------------------------------------------------------
-- C. Mapeos por traducción literal (mismo defecto, encontrado al revisar A y B)
-- -----------------------------------------------------------------------------
-- C.1 · id 39 "Cámara acorazada" tenía tomado el nombre 'Bashful Demon', que en
--       realidad le corresponde a id 44 "Demonio cohibido". "Cámara acorazada" es
--       The Vault palabra por palabra. Rareza y tipo ya eran los correctos (A /
--       Soporte), así que acá no cambia ningún dato: solo deja de usurpar el nombre.
--       Corrobora la captura Ejemplo_5 (Nivel 0/10, Recuperación de Energía 20 %).
UPDATE weapons
   SET nombre_en = 'The Vault'
 WHERE id = 39;

-- C.2 · id 44 "Demonio cohibido" = Bashful Demon (A / Soporte), no B.
--       atk_base 500 no es un valor de nivel 60 de ningún rango (A = 594/624) y no
--       hay captura ⇒ NULL en vez de inventarlo.
UPDATE weapons
   SET nombre_en         = 'Bashful Demon',
       rareza            = 'A',
       tipo_especialidad = 'Soporte',
       atk_base          = NULL
 WHERE id = 44;

-- C.3 · id 16 "Petrazufre" = The Brimstone (S / Ataque). "Petrazufre" es piedra +
--       azufre = brimstone, palabra por palabra. Estaba tomando el nombre de
--       'Bellicose Blaze' ("llamarada belicosa"), que no se parece en nada.
--       Rareza y tipo ya eran los correctos (captura Ejemplo_17: 60/60 · Ataque 30 %);
--       el ATK se corrige abajo en el bloque D.
UPDATE weapons
   SET nombre_en = 'The Brimstone'
 WHERE id = 16;

-- C.4 · id 14 "Caldero de la claridad" = Cauldron of Clarity (A / Ruptura) palabra
--       por palabra. Estaba mapeada a Half-Sugar Bunny (S / Defensa), que en español
--       no se parece en nada. Sin captura ⇒ atk_base NULL (713 era un valor de S).
UPDATE weapons
   SET nombre_en         = 'Cauldron of Clarity',
       rareza            = 'A',
       tipo_especialidad = 'Ruptura',
       atk_base          = NULL
 WHERE id = 14;

-- -----------------------------------------------------------------------------
-- D. atk_base contra la pantalla
-- -----------------------------------------------------------------------------
-- Al verificar el ATK de "Petrazufre" apareció que la columna arrastra el mismo mal
-- que `nombre_en`: valores que vinieron del emparejamiento equivocado. Comparando las
-- 40 capturas contra el catálogo salieron 5 filas más con el ATK de otra arma.
-- `atk_base` está documentado como "ATK al nivel 60", así que la captura a 60/60 es
-- fuente directa y manda sobre cualquier lista.
UPDATE weapons SET atk_base = 624 WHERE id = 40;   -- Roaring Ride            (era 594)
UPDATE weapons SET atk_base = 594 WHERE id =  7;   -- Starlight Engine        (era 684)
UPDATE weapons SET atk_base = 624 WHERE id = 36;   -- Starlight Engine Replica(era 594)
UPDATE weapons SET atk_base = 594 WHERE id = 11;   -- Cannon Rotor            (era 713)
UPDATE weapons SET atk_base = 684 WHERE id = 16;   -- The Brimstone           (era 713)

-- -----------------------------------------------------------------------------
-- E. Nombres EN inventados que quedan sin resolver ⇒ NULL
-- -----------------------------------------------------------------------------
-- Ninguno de estos tres nombres existe en el juego. Hay candidato semántico para
-- cada uno (anotado en audit/weapons_catalog_20260728.md) pero ninguno es traducción
-- literal, y una etiqueta EN equivocada arrastra después al ícono equivocado.
-- Se dejan en NULL hasta que Daniel capture la pantalla de detalle.
--   id 37 "Primavera termal"   — era 'Hot Spring'          (¿Spring Embrace?)
--   id 42 "Cilindro neumático" — era 'Pneumatic Cylinder'  (¿Big Cylinder?)
--   id 53 "Tránsito herciano"  — era 'Hertz Transit'       (¿Radiowave Journey?)
UPDATE weapons SET nombre_en = NULL WHERE id IN (37, 42, 53);

COMMIT;

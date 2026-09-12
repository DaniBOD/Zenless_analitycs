-- =============================================================================
-- 2026-09-12_30 · inventory_weapons: 'Tránsito herciano' es de Billy Estelar
-- =============================================================================
-- La pasada del 2026-09-11 escribió la fila 26 a nombre de **Billy** (id 12) y el
-- arma es de **Billy Estelar** (id 47). No son el mismo PJ ni un atuendo: en
-- `agents`, Billy es rango A / Ataque / M6 y Billy Estelar es rango S /
-- Disruptivos / M0, y cada uno tiene sus 6 discos asignados.
--
-- ## Por qué el sistema se equivocó, y por qué ya no
--
-- La librería del detalle tenía la cara de Billy Estelar guardada bajo la
-- etiqueta 'Billy'. Medido ref por ref contra el badge de Estelar (captura
-- `Ejemplo_18`): esa ref daba 0.156 y la de Billy 0.475. Como la distancia de
-- una clase es la de su MEJOR ref, Billy le ganaba a Estelar (0.16 contra 0.26)
-- en el arma de Estelar.
--
-- Corregido el 2026-09-12 moviendo esa ref a 'Billy Estelar' (no se borró;
-- backup `avatar_detbadge_v2.backup_prerelabel_20260912_024322.npz`). Verificado
-- releyendo la librería en un proceso limpio:
--
--     Ejemplo_17 (Réplica de motor estelar) → Billy          0.172 · margen 0.250
--     Ejemplo_18 (Tránsito herciano)        → Billy Estelar  0.156 · margen 0.272
--
-- ## Lo que esta migración NO hace
--
-- No escribe la `Réplica de motor estelar` para Billy. Esa fila la tiene que
-- crear una pasada en vivo, viéndola: el sistema no inventa filas y la
-- observación es la autoridad. Hoy no pudo, y con razón — el bucket B se
-- abstuvo porque Billy ya figuraba con esta arma:
--
--     Conflicto: Billy ya figura con weapon_id=53 (fila 26) y esta lectura dice
--     'Réplica motor estelar' (weapon_id=36) — no se toca ninguna de las dos.
--
-- Con la fila 26 en su dueño real, ese conflicto desaparece y la próxima pasada
-- escribe la Réplica sola.
--
-- Detalle completo: `audit/latencia_y_badges_20260912.md`.
-- =============================================================================

BEGIN TRANSACTION;

UPDATE inventory_weapons
   SET agente_asignado = (SELECT id FROM agents WHERE nombre = 'Billy Estelar'),
       notas = 'reasignada el 2026-09-12: la leyó como de Billy porque la librería tenía la '
            || 'cara de Billy Estelar etiquetada como Billy (ref movida, no borrada)'
 WHERE id = 26
   AND equipado = 1 AND descartado = 0
   AND agente_asignado = (SELECT id FROM agents WHERE nombre = 'Billy')
   AND weapon_id = (SELECT id FROM weapons WHERE nombre = 'Tránsito herciano');

COMMIT;

-- -----------------------------------------------------------------------------
-- Smoke checks: cada columna expected_N tiene que valer exactamente N
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS expected_55 FROM inventory_weapons WHERE descartado = 0;
-- La 26 quedó en Billy Estelar...
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i
  JOIN agents a ON a.id = i.agente_asignado
 WHERE i.id = 26 AND a.nombre = 'Billy Estelar';
-- ...y Billy queda SIN arma equipada, que es lo correcto hasta que se vea la Réplica.
SELECT COUNT(*) AS expected_0 FROM inventory_weapons i
  JOIN agents a ON a.id = i.agente_asignado
 WHERE a.nombre = 'Billy' AND i.equipado = 1 AND i.descartado = 0;
-- Un PJ, un arma: el índice único parcial sigue valiendo para Billy Estelar.
SELECT COUNT(*) AS expected_1 FROM inventory_weapons i
  JOIN agents a ON a.id = i.agente_asignado
 WHERE a.nombre = 'Billy Estelar' AND i.equipado = 1 AND i.descartado = 0;
PRAGMA foreign_key_check;
PRAGMA integrity_check;

# Migración 38 · Enemigos del Quinto Frente y primer ciclo de Shiyu (2026-09-18)

Salida de `apply_migration.py` sobre `db/danibod_zzz_v2.db` (con `PYTHONPATH=.`: sin eso el runner no encuentra `app.db.connection` y aborta en el backup, antes de tocar la DB — verificado: 12 enemigos, 0 ciclos, 13 columnas tras el intento fallido).

Ensayo previo sobre copia: verde (mismos 10 `expected_N`). **Sabotaje (A3):** con el dato de Akademiya (Centinela resistente a Físico) el chequeo de pantalla da 2 en vez de 1 → ROJO.

```
DB       : db\danibod_zzz_v2.db
Migración: db\migrations\2026-09-18_38_enemigos_y_ciclo_shiyu_quinto_frente.sql
Sentencias: 25
Backup   : db\danibod_zzz_v2.backup_premig_20260918_003718.db
------------------------------------------------------------------------------
[01] BEGIN TRANSACTION;  -> ok
[02] ALTER TABLE enemies ADD COLUMN atk_base INTEGER;  -> ok
[03] ALTER TABLE enemies ADD COLUMN def_base INTEGER;  -> ok
[04] ALTER TABLE enemies ADD COLUMN daze_base INTEGER;  -> ok
[05] ALTER TABLE enemies ADD COLUMN stun_duracion_s REAL;  -> ok
[06] ALTER TABLE enemies ADD COLUMN stun_dmg_mult REAL;  -> ok
[07] INSERT INTO enemies (nombre_es, nombre_en, tipo, faccion, hp_base, atk  -> ok
[08] CREATE TEMP TABLE _res (nombre_en TEXT, elemento TEXT, mult REAL);  -> ok
[09] INSERT INTO _res VALUES  -> ok
[10] INSERT INTO enemy_resistances (enemy_id, elemento, multiplicador, brea  -> ok
[11] DROP TABLE _res;  -> ok
[12] INSERT INTO shiyu_cycles (cycle_number, fecha_inicio, fecha_fin, frent  -> ok
[13] COMMIT;  -> ok
[14] SELECT COUNT(*) AS expected_23 FROM enemies;
     expected_23=23
[15] SELECT COUNT(*) AS expected_11 FROM enemies
     expected_11=11
[16] SELECT COUNT(*) AS expected_66 FROM enemy_resistances r JOIN enemies e
     expected_66=66
[17] SELECT COUNT(*) AS expected_0 FROM enemy_resistances r JOIN enemies e 
     expected_0=0
[18] SELECT COUNT(*) AS expected_1 FROM enemy_resistances r JOIN enemies e 
     expected_1=1
[19] SELECT COUNT(*) AS expected_0 FROM enemy_resistances r JOIN enemies e 
     expected_0=0
[20] SELECT COUNT(*) AS expected_1 FROM enemy_resistances r JOIN enemies e 
     expected_1=1
[21] SELECT COUNT(*) AS expected_1 FROM shiyu_cycles;
     expected_1=1
[22] SELECT json_array_length(frentes) AS expected_3 FROM shiyu_cycles WHER
     expected_3=3
[23] SELECT COUNT(*) AS expected_0 FROM shiyu_cycles c, json_each(c.frentes
     expected_0=0
[24] PRAGMA foreign_key_check;  -> ok
[25] PRAGMA integrity_check;
     integrity_check=ok
------------------------------------------------------------------------------
OK — revisá arriba que cada `expected_N` valga exactamente N.
```

Ids asignados: 13 Centinela · 14 Cerrosorte (Lockspring) · 15 Tepes · 16-23 enemigos de oleada. El JSON de `shiyu_cycles.frentes` los resuelve por `nombre_en`, no por id fijo.

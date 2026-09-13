# Migración 34 · Severed Innocence unificada (2026-09-13)

Salida de `apply_migration.py` sobre `db/danibod_zzz_v2.db`. Ensayo previo sobre copia: verde.

```nDB       : db\danibod_zzz_v2.db
Migración: db\migrations\2026-09-13_34_weapons_unifica_severed_innocence.sql
Sentencias: 14
Backup   : db\danibod_zzz_v2.backup_premig_20260913_143825.db
------------------------------------------------------------------------------
[01] BEGIN TRANSACTION;  -> ok
[02] UPDATE inventory_weapons SET weapon_id = 22  -> ok
[03] DELETE FROM weapons  -> ok
[04] UPDATE weapons SET nombre = 'Inocencia sacrificada'  -> ok
[05] COMMIT;  -> ok
[06] SELECT COUNT(*) AS expected_60 FROM weapons;
     expected_60=60
[07] SELECT COUNT(*) AS expected_1 FROM weapons
     expected_1=1
[08] SELECT COUNT(*) AS expected_0 FROM weapons WHERE id = 62 OR nombre = '
     expected_0=0
[09] SELECT COUNT(*) AS expected_1 FROM inventory_weapons
     expected_1=1
[10] SELECT COUNT(*) AS expected_0 FROM inventory_weapons WHERE weapon_id =
     expected_0=0
[11] SELECT COUNT(*) AS expected_56 FROM inventory_weapons WHERE descartado
     expected_56=56
[12] SELECT COUNT(*) AS expected_0 FROM (SELECT nombre_en FROM weapons WHER
     expected_0=0
[13] PRAGMA foreign_key_check;  -> ok
[14] PRAGMA integrity_check;
     integrity_check=ok
------------------------------------------------------------------------------
OK — revisá arriba que cada `expected_N` valga exactamente N.
```n
Cobertura de íconos de armas del inventario después:

```nSIN ICONO 54 Sol exuvia Sol Exuvia S 1
SIN ICONO 55 Ecos bulliciosos Boisterous Echoes A 1
SIN ICONO 63 Tetera esmeraldina Ice-Jade Teapot S 1
37/40 tipos con icono
```n

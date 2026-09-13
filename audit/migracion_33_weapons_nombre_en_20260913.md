# Migración 33 · weapons nombre_en (2026-09-13)

Salida de `apply_migration.py`. DB: `db/danibod_zzz_v2.db`. Ensayo previo sobre copia: verde.

```
﻿DB       : db\danibod_zzz_v2.db
Migración: db\migrations\2026-09-13_33_weapons_nombre_en_cuatro_armas.sql
Sentencias: 12
Backup   : db\danibod_zzz_v2.backup_premig_20260913_132637.db
------------------------------------------------------------------------------
[01] BEGIN TRANSACTION;  -> ok
[02] UPDATE weapons SET nombre_en = 'Steam Oven'        WHERE id = 5  AND n  -> ok
[03] UPDATE weapons SET nombre_en = 'The Simmering Pot' WHERE id = 13 AND n  -> ok
[04] UPDATE weapons SET nombre_en = 'Ice-Jade Teapot'   WHERE id = 63 AND n  -> ok
[05] COMMIT;  -> ok
[06] SELECT COUNT(*) AS expected_61 FROM weapons;
     expected_61=61
[07] SELECT COUNT(*) AS expected_3 FROM weapons
     expected_3=3
[08] SELECT COUNT(*) AS expected_5 FROM weapons WHERE nombre_en IS NULL;
     expected_5=5
[09] SELECT COUNT(*) AS expected_1 FROM weapons WHERE id = 62 AND nombre_en
     expected_1=1
[10] SELECT COUNT(*) AS expected_0 FROM (SELECT nombre_en FROM weapons WHER
     expected_0=0
[11] PRAGMA foreign_key_check;  -> ok
[12] PRAGMA integrity_check;
     integrity_check=ok
------------------------------------------------------------------------------
OK — revisá arriba que cada `expected_N` valga exactamente N.
```

Cobertura de íconos de armas del inventario: 34 → 36 de 40 (verificado sobre la DB real). Tests `-k "weapon or engine or arma"`: 929 passed.

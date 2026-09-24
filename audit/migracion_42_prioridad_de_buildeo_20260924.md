# Migración 42 · Prioridad de buildeo por PJ (2026-09-24)

Tabla `ajustes_usuario_prioridad` (capa de ajustes del usuario, como la mig 40): alta / baja por PJ;
normal = sin fila. Nace vacía. Motivo, reglas y decisiones de Daniel: cabecera del `.sql`.

**Ensayo (A3):** `app/tests/unit/test_mig42_prioridad.py` corre el `.sql` real sobre una copia de la
DB (9 verdes). Sabotajes sobre el `.sql`, cada uno con su rojo: sin el `CHECK` (4 rojos), aceptando
`'normal'` (1), sin la `REFERENCES agents(id)` (1), sin la `PRIMARY KEY` (1). sha de la DB de dominio
sin cambios en todos (`ce3d52dd4275`).

Corrida real con la app cerrada (sha antes: `ce3d52dd4275`):

```
DB       : db\danibod_zzz_v2.db
Migración: db\migrations\2026-09-24_42_prioridad_de_buildeo.sql
Sentencias: 6
Backup   : db\danibod_zzz_v2.backup_premig_20260924_124307.db
------------------------------------------------------------------------------
[01] BEGIN TRANSACTION;  -> ok
[02] CREATE TABLE ajustes_usuario_prioridad (  -> ok
[03] COMMIT;  -> ok
[04] PRAGMA foreign_key_check;  -> ok
[05] PRAGMA integrity_check;
     integrity_check=ok
[06] SELECT COUNT(*) AS expected_0 FROM ajustes_usuario_prioridad;
     expected_0=0
------------------------------------------------------------------------------
OK — revisá arriba que cada `expected_N` valga exactamente N.
```

# Migración 43 · Builds recomendados por PJ + build objetivo (2026-09-25)

Cuatro tablas, todas nacen vacías: `pj_sets_4pc`, `pj_sets_2pc`, `pj_stats_recomendados`
(conocimiento de las guías, INVESTIGACION) y `ajustes_usuario_build` (lo que declara Daniel,
DECLARADO). Motivo, reglas R18-R20 y decisiones de Daniel: cabecera del `.sql` y SPEC (casos 12-13).

**Ensayo (A3):** `app/tests/unit/test_mig43_builds_recomendados.py` corre el `.sql` real sobre una
copia de la DB (7 verdes). Sabotajes, cada uno con su rojo: sin la FK compuesta 2pc → 4pc, `orden`
repetible, `variante` anulable, `linea` libre, 2pc igual al 4pc, `ajustes_usuario_build` sin
clasificar en el rebuild. sha de la DB de dominio sin cambios en todos (`4ee982e966ec`).

`test_rebuild_account_db::test_clasificar_tablas_cubre…` dio rojo ANTES de aplicar (las cuatro
estaban clasificadas y la DB no las tenía): es la guarda funcionando, no un defecto.

Corrida real con la app cerrada (verificada por CommandLine; sha antes: `59db8b15240e`):

```
Backup   : db\danibod_zzz_v2.backup_premig_20260925_005208.db
------------------------------------------------------------------------------
[01] BEGIN TRANSACTION;  -> ok
[02] CREATE TABLE pj_sets_4pc (  -> ok
[03] CREATE TABLE pj_sets_2pc (  -> ok
[04] CREATE TABLE pj_stats_recomendados (  -> ok
[05] CREATE TABLE ajustes_usuario_build (  -> ok
[06] COMMIT;  -> ok
[07] PRAGMA foreign_key_check;  -> ok
[08] PRAGMA integrity_check;
     integrity_check=ok
[09] SELECT COUNT(*) AS expected_0 FROM pj_sets_4pc;
     expected_0=0
[10] SELECT COUNT(*) AS expected_0 FROM ajustes_usuario_build;
     expected_0=0
------------------------------------------------------------------------------
OK — revisá arriba que cada `expected_N` valga exactamente N.
```

sha después: `4ee982e966ec`.

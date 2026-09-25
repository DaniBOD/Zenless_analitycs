# Carga · builds recomendados por PJ desde Prydwen (2026-09-25)

Captura: `audit/prydwen/2026-09-25_captura_prydwen.jsonl` (52 guías, leídas con el navegador
integrado el 2026-09-25; versión de cada guía en `version_guia`). Cargador:
`app/scripts/cargar_builds_prydwen.py` (tests: `test_cargar_builds_prydwen.py`). Tablas de la mig 43.

Corrida real con la app cerrada (verificada por CommandLine):

```
sha antes 4ee982e966ec
4pc: 119 · 2pc: 461 · stats: 549
PJs: 52
backup: db\danibod_zzz_v2.backup_prebuilds_20260925_012316.db
sha despues 9904064e4da7
integrity ok fk []
pj_sets_4pc 119 · pj_sets_2pc 461 · pj_stats_recomendados 549 · ajustes_usuario_build 0
```

0 problemas reportados (ningún PJ, set o rótulo de stat sin reconocer).

Huecos de la guía (quedan sin fila, no se inventan — RNF-02): Evelyn sin 2pc para sus tres 4pc;
Ju Fufu y Zhao sin prioridad de substats. Candidatos a cruzar con Game8.

El motor todavía NO lee estas tablas: ninguna sugerencia cambia con esta carga.

# Reset del censo de discos — `inventory_discs` vuelve a 0

**2026-08-29 18:47.** Pedido por Daniel: rehacer el censo de discos desde cero, ahora que están
los dos arreglos de la pasada anterior (dueño innombrable `6d36f78`, re-arme del gemelo `35eaab4`).

## Qué se borró

| tabla | antes | después |
|---|---|---|
| `inventory_discs` | **115** | 0 |
| `inventory_disc_evaluations` | 0 | 0 |
| `sqlite_sequence['inventory_discs']` | 115 | *(fila eliminada)* |

Los 115 discos eran **todos** de una sola sesión — `fecha_obtencion` entre `2026-08-21 03:20:54` y
`03:44:18`— o sea la pasada del censo del 2026-08-20 (la DB guarda el sello en UTC). No había nada
anterior que preservar: el inventario ya se había vaciado el 2026-08-17 al reconstruir la cuenta.

Reparto de lo borrado: 87 con dueño, 28 libres.

El `sqlite_sequence` se borró para que los ids arranquen de nuevo en 1. Es seguro: la única tabla
que referencia `inventory_discs` es `inventory_disc_evaluations` (FK sobre `.id`) y estaba vacía.

## Qué NO se tocó

```
agents                 51      roster_declarations    58
disc_sets              30      agent_thresholds      111
pj_weapon_synergy     294      weapons                59
agent_awakenings       16
```

Es la misma frontera del rebuild del 2026-08-17: **se vacía lo observable, se conserva lo que no
se puede volver a observar**.

`db/census.db` tampoco se tocó. Guarda sólo corridas de **roster** (`ambito='roster'`, 2 corridas /
53 filas de cobertura / 145 observaciones); el censo de discos no lleva estado ahí — su contador
sale de la propia pantalla (`[censo-discos] N/405`), así que se reinicia solo.

## Ritual RNF-01

```
respaldo   db/danibod_zzz_v2.backup_precenso_discos_cero_20260829_184738.db  (589 824 bytes)
           creado con `app.db.connection.respaldar_db`, no con un copy a mano
           sha256 del respaldo == sha256 de la DB previa  →  verificado, bit a bit

DELETE dentro de una transacción única (`with con:`)

PRAGMA foreign_key_check   0 violaciones
PRAGMA integrity_check     ok

sha256 ANTES    29c7f2ae8c439e5fbfe7d5d908321cc7987fa305f8f5ccaa697ffcb22be62591
sha256 DESPUÉS  d3992b2ae5a02272d30bd97a61d28413c78deee14c7fcbf930885689c49bb234
```

Se verificó además que ningún proceso de la app estuviera corriendo antes de escribir.

⚠️ El respaldo vive en `db/`, que está **gitignoreado**. Es la única copia de esos 115 discos; si
alguna vez hicieran falta, hay que sacarla de ahí antes de limpiar backups viejos.

## Cuál DB se limpió, y por qué importa

La del **repo** (`db/danibod_zzz_v2.db`). Es la que escribe el censo, porque se lanza con
`tools/qa_launch.ps1`, que setea `DANIBOD_DB_PATH` al repo.

Existe una segunda copia en `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\db\danibod_zzz_v2.db` — la que
usaría el `.exe` lanzado **sin** ese override, p. ej. desde el acceso directo del escritorio. Está
en 0 discos pero su mtime es del 2026-08-18: es un snapshot viejo. Si la próxima pasada se lanza
por el acceso directo en vez de por `qa_launch`, escribiría ahí y no acá.

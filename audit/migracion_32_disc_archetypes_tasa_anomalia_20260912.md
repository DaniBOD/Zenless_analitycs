# Migración `_32` · `disc_archetypes`: Tasa de Anomalía en slot 6 + Bono Daño Viento

> **Fecha:** 2026-09-12 · **SQL:** `db/migrations/2026-09-12_32_disc_archetypes_tasa_anomalia_y_viento.sql`
> **Diagnóstico:** `Documentacion/Dev_IA/documentacion_cruda/2026-09/2026-09-12_DIAG_El_filtro_de_mains_excluye_el_30_por_ciento_de_lo_equipado.md`
> **Cierra:** el pendiente §4 de `audit/correccion_tasa_anomalia_20260603.md`

## RNF-01

| paso | resultado |
|---|---|
| app cerrada | sin procesos `python` / DaniBOD en `Win32_Process` antes de aplicar |
| ensayo sobre copia | smoke checks OK; 2ª corrida idempotente; `iterdump` vs original: **solo 5 filas de `disc_archetypes`** distintas (DEFENSE intacta, ninguna otra tabla) |
| backup | `db/danibod_zzz_v2.backup_premig_20260912_222434.db` (runtime, gitignoreado) |
| sha256 antes | `495f44faeb0d2c12748490e8fd71c56651c74ac5191fa732e456d10fe4d759da` |
| sha256 después | `8150e2fe8902f221709fc4ecafd6a7c35f7ad96fe4922095bd848c469c334ec4` |
| transacción | `BEGIN TRANSACTION … COMMIT` |
| `PRAGMA foreign_key_check` | ok |
| `PRAGMA integrity_check` | ok |
| corrida real vs ensayo | `iterdump` idéntico |

Smoke checks (todos iguales a su N):

```
expected_6=6   filas en disc_archetypes
expected_6=6   JSON válido en mains_4/5/6
expected_1=1   ANOMALY.mains_6 = ["Tasa de Anomalía","ATK%"]
expected_0=0   ningún mains_6 con "Maestría de Anomalía"
expected_1=1   ANOMALY.mains_4 conserva ["Maestría de Anomalía","ATK%"]
expected_5=5   arquetipos con "Bono Daño Viento" en mains_5
expected_0=0   ninguno duplicado
expected_1=1   DEFENSE.mains_5 = ["DEF%","HP%"] (sin tocar)
expected_0=0   ningún "Lumen"
```

## Cambio

| arquetipo | columna | antes | después |
|---|---|---|---|
| ANOMALY | mains_6 | `["Maestría de Anomalía","ATK%"]` | `["Tasa de Anomalía","ATK%"]` |
| ATK_DPS, HP_DISRUPT, ANOMALY, STUN, SUPPORT_ER | mains_5 | … `"Bono Daño Éter"` … | … `"Bono Daño Éter","Bono Daño Viento"` … |
| DEFENSE | — | sin cambios | — |

Counts de tablas: sin cambios (6 arquetipos; no hay INSERT/DELETE).

## Efecto medido (copias de la DB antes/después, `persist=False`)

| | antes | después |
|---|---|---|
| discos equipados (slots 4–6) excluidos por el arquetipo de su propio PJ | 46 | **37** |
| PJs afectados | 29 | **23** |
| PJs ANOMALY con `Tasa de Anomalía` en el slot 6 de la mejor build | 0 / 11 | **10 / 11** |
| `score_actual` que cambia | — | 9 PJs ANOMALY, **+1.0 exacto** cada uno (bono de main) |
| latencia máx. del optimizador | 79.5 ms | 88.6 ms (dentro de RNF-06; diferencia no significativa) |

Los 37 restantes son de diseño (arquetipo más angosto que la build real, incluido Miyabi slot 4
`Daño Crítico`): no se tocaron.

## Fuera de alcance

La DB del `.exe` en `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\db\` (copia del 2026-08-18) tiene el mismo
`disc_archetypes` viejo. Esta migración se aplicó solo a `db/danibod_zzz_v2.db` del repo.

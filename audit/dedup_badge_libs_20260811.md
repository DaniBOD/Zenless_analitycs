# Limpieza de refs clonadas en las librerías de badges — 2026-08-11

Corrida de `tools/dedup_badge_lib.py --save-snapshot` sobre las tres librerías del runtime.
Spec: `Documentacion/Dev_IA/2026-08-11_SPEC_Dedup_Cosecha_Badges.md`.

## Qué se quitó

| superficie | refs antes | refs después | clases antes | clases después |
|---|---|---|---|---|
| `row` | 365 | **62** (17%) | 50 | **50** |
| `grid` | 486 | **356** (73%) | 56 | **56** |
| `detail` | 193 | **85** (44%) | 50 | **50** |

**Ninguna clase se perdió.** Se quitaron 541 copias; no se quitó una sola imagen distinta.

Backups automáticos en `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\*.backup_20260811_*.npz`. Baselines
versionados nuevos en `audit/avatar_*_snapshot_20260811_dedup.npz`; los anteriores quedan como
historia y no se reescribieron.

## El número que hay que saber leer

`tools/measure_badge_lib.py`, leave-one-out bajo guard 0.80:

| superficie | antes (con clones) | **después (real)** | wrong después |
|---|---|---|---|
| `row` | 96.4% | **35.5%** | 6.5% |
| `grid` | 91.2% | **81.2%** | 1.4% |
| `detail` | 88.6% | **42.4%** | 3.5% |

**La caída no es una regresión.** Con clones adentro, sacar una referencia dejaba a su gemela
idéntica matcheando a 0.000: el leave-one-out medía "¿quedó una copia mía?" en vez de
discriminación. Los wrongs suben por lo mismo — antes un clon devolvía el acierto gratis y tapaba
que la clase no discrimina.

La prueba de que el número nuevo es el bueno: el QA en vivo del inventario S30 (2026-08-11) dio
**5/11 = 45% de naming**, contra el 42.4% de `detail` dedupeado y el 88.6% de antes.

## Cómo quedó cada superficie

- **`grid` (81.2%)** — la sana, y se entiende: su tile CAMBIA con cada disco, así que la cosecha
  por disco produce imágenes distintas de verdad.
- **`detail` (42.4%)** — el avatar del panel no cambia con el disco seleccionado ⇒ seis discos,
  seis copias.
- **`row` (35.5%, 6.5% wrong)** — la peor, y la más inflada: 40 de 50 PJs tenían una sola imagen
  repetida cuatro veces. Es la superficie que identifica al PJ en S8/S18/S19. El riesgo está
  acotado por diseño —el latch se siembra con el OCR del menú S15, el matcher se abstiene bajo
  guard y el monitor sostiene al último conocido— pero es el próximo lugar a mirar.

## Qué cambia de acá en adelante

El indicador de salud de una librería pasa a ser **refs distintas**, no refs. Un contador que dice
4 y son la misma imagen es peor que uno que dice 1: nadie va a mirar.

`BadgeSurface.learn` ya no admite clones nuevos, así que esto no se vuelve a acumular.

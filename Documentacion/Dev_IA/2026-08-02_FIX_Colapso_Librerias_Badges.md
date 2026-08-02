# 2026-08-02 · FIX — El colapso de las librerías de badges (grid + row)

> **Síntoma reportado:** «antes el sistema reconocía bien los badges en los discos de los
> personajes; ahora caen todos en Cissia o Remielle».
>
> **Causa:** ninguna de las que se sospechaban. No era el descriptor, ni los umbrales, ni la
> cosecha. **La carpeta de librerías del runtime se vació** y el grid volvió a aparecer
> regenerado solo con la semilla `-ico`.
>
> **Commits:** `bf5fffd` · `7794843` · `276b2c8` · `c8e62cd`

---

## 1. El diagnóstico

`%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\` se vació — la misma desaparición que había dejado la
librería del *detail* en cero el 2026-07-28 (ver `2026-07-28_IMPL_RF15_S26_Detalle_WEngine.md`
§"el archivo no existe"). Esa se restauró del snapshot de `audit/`; la del grid nunca, y la del
`row` directamente no volvió a existir.

Lo que hacía el fallo difícil de ver es que **el archivo del grid reaparecía**: `_seed_ico()` lo
regeneraba en cada arranque. Pero el `-ico` es arte de comunidad recortado del splash — **otro
dominio** que el badge in-game. Y acá está la lección que vale más que el fix:

> **Una librería degradada no se abstiene. Nombra mal, con confianza.**

De 56 clases, 51 tenían **2 refs idénticas** de `-ico` (distancia intra-clase `0.0`, producto de
un bucle de duplicación, §3) y solo 5 tenían **una ref del dominio real**: Antón, Ben, Cissia,
Harumasa y Remielle Dan, las cosechadas esa semana. Como la distancia de una clase es un `min`
sobre sus refs (`avatar_descriptor.py`), sin normalizar por dominio ni por cardinalidad,
**cualquier badge real se parece más a la única ref real ajena que al arte oficial del PJ
propio**. Por eso ganaban siempre los mismos cinco.

### El harness que lo detectó, y el que no podía

`tools/measure_badge_lib.py --against-labeled` — matchea los 164 badges REALES etiquetados de
`audit/labeled_badges/<PJ>/S17_*.png` contra la librería que la app carga de verdad.

| librería del grid | top-1 | abstiene | wrong |
|---|---|---|---|
| degradada (117 refs) | **4.3 %** | 81.1 % | 14.6 % — Cissia ×14, Harumasa ×6, Remielle ×4 |
| snapshot restaurado (459 refs) | **93.3 %** | 4.3 % | 2.4 % |

**El leave-one-out no puede ver este fallo**: mide un `.npz` contra sí mismo, así que a una
librería sin cosecha le da perfecto. Es la misma trampa que volvió a aparecer con el `row` (§4).
Regla operativa: ante «la identificación empeoró sin motivo», correr `--against-labeled`
**antes** de tocar un umbral.

---

## 2. Restauración y red de emergencia

- **grid** ← `audit/avatar_badge_v2_snapshot_20260612_full47.npz` (47 clases, 459 refs). El
  recorte no cambió desde que se cosecharon: `_GRID_REGION` y `_BADGE_CX_F/CY_F/R_F`
  (`detector.py`) vienen del commit `8e18b9c`, el mismo hito 5R que produjo el snapshot.
- **row** ← reconstruido de cero, no existía el archivo.
- **Auto-restauración**: `BadgeSurface(baseline_path=...)` repone del snapshot versionado de
  `audit/` con un **WARNING** (no DEBUG) cuando la librería del runtime no está.

  Aplica **solo a la ubicación real**. Con `library_path` explícito o con `DANIBOD_AVATAR_LIB`
  —que es como el `conftest` aísla cada test en su tmp— no aplica: ahí que el archivo falte es
  información deliberada, y volcarle 459 refs rompía el aislamiento. Dos tests de armas lo
  avisaron apenas se cableó mal.
- **`load()` loguea la cobertura** por superficie (`50 clases · 365 refs · la más flaca tiene 1`).
  El modo de falla fue una librería **presente pero degradada**, que el auto-restore no ve y que
  no tenía una sola línea en el log que lo delatara.

---

## 3. El bucle que duplicaba la semilla

`_seed_ico()` corría **antes** de `load_s17()` y extendía sin tope; `load_merge` tampoco aplica
`_MAX_REFS_PER_NAME`. Como el `.npz` ya contenía una copia guardada de la semilla, cada ciclo
`seed → load → save` sumaba otra.

Ahora la semilla se aplica **después** de cargar y **solo en las clases que quedaron sin refs**
(`_seed_ico_refs`). Sigue cumpliendo su función declarada —cobertura día-1 de los PJs grises que
no se poseen— y deja de competir con la cosecha real. `_ico_names` se sigue poblando con **todos**
los stems, porque `prune_to_roster` lo usa para proteger a los no obtenidos.

---

## 4. El `row`: el mismo error de dominio, en chico

El QA en vivo del grid dio 6/6 (§5), pero destapó otra cosa: la página de **Remielle Dan** se
identificaba como **Vivian**. Dos causas, las dos medidas:

**(a) `identify_face` no aplicaba guard.** Devolvía cualquier match que pasara los gates internos
del matcher (`min_conf=0.45`, `min_margin=0.04`) — la mitad del guard que usa el resto del
sistema. Vivian pasó con **0.550**, y dos frames de eso fijaron el latch.

El umbral nuevo sale medido, no elegido: leave-one-out sobre las refs de fila, la confianza
**mínima** de un match correcto es **0.928** (mediana 1.000). A 0.80 no cae ni un acierto y el
falso queda afuera con margen. Un PJ sin refs **abstiene**, y el monitor sostiene al último
conocido en vez de saltar a otro (RNF-02).

**(b) Las refs del row tenían otro encuadre.** Los S8/S18 pre-cortados de `labeled_badges` son
37×37 circulares; `crop_selected_avatar` da 52×52 cuadrados sobre una captura del mismo tamaño.
Medido sobre un frame real de Nangong Yu (genuinamente retenido):

| fuente de las refs | conf |
|---|---|
| pre-cortados de `labeled_badges` | 0.833 |
| frames de `audit/harvest` recortados con la función de la app | **0.958** |

y sobre Remielle sin refs: los pre-cortados decían `Vivian 0.550`, la nueva **abstiene**.

⚠️ **`audit/harvest/` son frames COMPLETOS (1440×2560), no recortes.** Meterlos enteros como refs
es basura con nombre de PJ. Hay que pasarles el `crop_fn` — que además es lo que garantiza el
like-with-like de la Fase 5R.

Reconstruir el row desde harvest sumó 4 clases que `labeled_badges` no tenía (Antón, César,
Lucía, N.º 11): **sus carpetas existen pero están vacías**.

---

## 5. QA en vivo

**Grid, 6 PJs (2026-08-01):**

| PJ | `grid_votes` | veredicto |
|---|---|---|
| Ellen | Ellen 0.85–1.00 | ✅ |
| Pulchra | Pulchra 0.92–1.00 | ✅ |
| Billy Estelar | Billy Estelar 0.83–0.98 | ✅ |
| Pyrois · Velina · Remielle Dan | `-` | ✅ abstiene — no estaban en el snapshot |

Cero apariciones de Cissia robando discos ajenos. En Pyrois, con el grid abstenido,
`det_votes=[Pyrois:3.85]` sostuvo la identificación solo.

**Cosecha de los 3 nuevos (2026-08-02):** el lazo se cierra solo — apenas cosecha un disco, el
siguiente ya lo nombra (Remielle 0.88 → 0.95; Velina y Pyrois → 1.00). Funciona **porque el grid
arrancaba abstenido** en ellos: sin refs no hay veto que estorbe y el ancla trae el nombre leído
del menú S15.

**Verificación de no-regresión:** sumar 3 clases dejó la medición **idéntica** (93.3 % / 2.4 %,
mismos 4 wrong). Ese chequeo es obligatorio al cosechar: una ref mal etiquetada se nota ahí y en
ningún otro lado.

---

## 6. Estado final

| superficie | clases | refs | baseline versionado en `audit/` |
|---|---|---|---|
| `row` | 50 | 365 | `avatar_row_v2_snapshot_20260801.npz` |
| `grid` | 56 | 486 | `avatar_badge_v2_snapshot_20260802_roster50.npz` |
| `detail` | 50 | 166 | `avatar_detbadge_v2_snapshot_20260731_cosecha50.npz` |

Las 56 clases del grid son 50 del roster + 6 `-ico` de PJs no obtenidos (Aria, Banyue, Hugo,
Lichter, Promeia, Yidhari).

---

## 7. Límites conocidos (no son bugs)

- **Billy vs Billy Estelar**: mismo personaje, distinto atuendo. En el `row` distan **0.015** y el
  matcher se abstiene por margen; en el grid son los 4 únicos wrong de la medición (conf
  0.94-0.99). No se arregla con umbrales — el recorte es solo la cara. En vivo lo cubre el nombre
  leído del menú S15.
- **`decide_owner` deja que un solo frame del grid con `conf ≥ 0.80` decida sin contrapeso**
  (`owner_vote.py`), y el guard anti-imán solo cubre la rama detail-solo. Con la librería sana no
  molesta (93 %); con una degradada es lo que la deja mentir con confianza. Endurecerlo es un
  cambio aparte, y conviene medirlo antes.
- **Identificar a qué PJ pertenece un screenshot no se pudo automatizar**: contra el arte `-ico`
  las distancias quedan en ~0.44-0.49 (otro dominio) y por firma de color del splash el resultado
  ni siquiera es una biyección — dos archivos al mismo PJ. **Preguntar antes de etiquetar.**

---

## 8. Protocolo derivado

Todo lo operativo —qué hacer cuando entra un PJ nuevo— vive en
[`Onboarding_Badges_PJ_Nuevo.md`](../Onboarding_Badges_PJ_Nuevo.md).

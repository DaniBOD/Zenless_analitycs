# FIX · El optimizador medía la build actual contra una tabla vacía

> **Fecha:** 2026-09-12 · **Tipo:** FIX · **Alcance:** `app/core/optimizer.py`, `app/db/repositories.py`
> **Prácticas en juego:** A1 (medir antes de afirmar), A3 (romper el test), A5 (grep sin recortes), B1 (una autoridad)

---

## 1. El hallazgo

Apareció armando la pantalla en vivo: para dibujar el hexágono de un PJ hacía falta "qué discos
tiene equipados", y la respuesta natural (`inventory_discs` con `agente_asignado=? AND equipado=1
AND descartado=0`) no era la que usaba el optimizador. `BuildOptimizer.best_builds` calculaba el
baseline así:

```python
current_discs = self._agent_disc_repo.get_by_agent(agente_id)   # SELECT * FROM agent_discs …
score_actual  = self._build_total_score(current_discs, agent, arch)
```

`agent_discs` quedó en **0 filas** con la reconstrucción de la DB del 2026-08-17
(`rebuild_account_db.py` la vacía, ver `audit/rebuild_db_20260817_193905.md`) y **nada en el código
la vuelve a llenar**: no hay un solo `INSERT`/`UPDATE` sobre esa tabla fuera del script de
reconstrucción. La autoridad real se movió a `inventory_discs` y el optimizador se quedó mirando
la vieja.

## 2. Medición (A1) — antes de tocar nada

Sobre una **copia** de `db/danibod_zzz_v2.db` (sha256 `495f44fa…` idéntico antes y después), con
`persist=False`:

| medida | valor |
|---|---|
| filas en `agent_discs` | **0** |
| discos equipados en `inventory_discs` | 305, de **51** PJs |
| PJs con `score_actual == 0` | **51 / 51** |
| Miyabi: `score_actual` reportado / real | 0.0 / **8.70** |
| Miyabi: delta reportado / real | 23.25 / **14.55** |

O sea: todo delta salía inflado exactamente por el score total de la build que el PJ ya lleva.

### ¿Llegó a producción? — no, y hay que decirlo

La premisa con la que se abrió el hallazgo era *"en producción `score_actual` es siempre 0 y puede
estar escribiendo filas engañosas en `optimizer_pending_actions`"*. Medido:

- `optimizer_pending_actions`: **0 filas** en la DB del repo.
- `app.log` (desde 2026-08-10, 9.247 líneas): `grep -c "Optimizer PJ="` = **0**,
  `grep -c "Error en optimizer"` = **0**, `grep -c "Sync OK"` = **0**.
- El único disparador es `DiscSyncer._schedule_optimizer`, llamado solo desde
  `DiscSyncer.on_disc_detected`. El controller de la app **no llama a `on_disc_detected`**: usa
  `persist_s17_disc`, `dar_de_baja_desmontados` y el syncer de armas.

El bug era **latente**: correcto como defecto, sin daño hecho todavía. Pero cualquier cosa que
conecte el optimizador a la UI (la pantalla en vivo va hacia ahí) lo habría heredado, y el test
de integración que existía no podía verlo (§4).

## 3. El arreglo

- `BuildOptimizer` lee el baseline con `InventoryDiscRepo.find_equipped_by_agent(agente_id)`
  (`{slot: Disc}`), el mismo método que usa la pantalla en vivo. Una sola respuesta a "qué tiene
  equipado este PJ" (B1).
- **`AgentDiscRepo` se borró.** Grep excluyendo `app/build/` (bundle de PyInstaller), sin recortes:
  sus únicas referencias eran el import y la instancia en `optimizer.py`, más un parámetro
  `agent_disc_repo` de `_compute_swaps` que **nunca se usaba** en el cuerpo. Dejar la clase era
  dejar la segunda autoridad esperando al próximo que la encuentre.
- `find_equipped_by_agent` ya existía como cambio sin commitear de la sesión de UI en el checkout
  principal; se agregó acá con el **texto idéntico**, en el mismo lugar, para que el merge sea
  trivial.

### Lo que NO se tocó (E3)

- **La tabla `agent_discs` sigue en el esquema.** Borrarla es una migración (escritura RNF-01) y
  `rebuild_account_db.py` + su test la nombran en la lista de tablas a vaciar. Ya no la lee nadie
  en `app/`. ❓ **Decisión de Daniel:** migración `DROP TABLE agent_discs` (y sacarla del rebuild),
  o dejarla muerta.
- Los docs de Fase 1 que la describen como "build actual" (`Modelo_Relacional/README.md`,
  `QA-01`, `RF-Logic_Captura_Discos.md` §7) quedan como están. Sí se corrigió la tabla de entradas
  de `RF-Logic_Optimizador_Build.md` §3.1, porque describe exactamente este código.

## 4. Tests (A3)

`app/tests/unit/test_optimizer_build_actual.py` — copia de la DB de dominio con **inventario
controlado** (no depende del censo: el esquema y el catálogo sí, el inventario lo pone el test):
los únicos discos activos son los 6 que Miyabi tiene equipados.

1. `score_actual` == score de esa build (calculado con la misma `_build_total_score`).
2. Sin otros discos, la mejor build **es** la actual ⇒ delta 0, verificado en la **fila persistida**
   de `optimizer_pending_actions`, no en el objeto.

Antes del fix: fallaban los dos (`0.0 != 9.70`, `delta 9.7 != 0`).

**Romperlo a propósito** — tres mutaciones, las tres en rojo:

| mutación | resultado |
|---|---|
| baseline `current_discs = []` (el bug original) | 2 failed |
| query sin `equipado=1` | 2 failed |
| query sin `descartado=0` | 2 failed |

La primera versión del test **no tenía dientes** para la segunda mutación: el ruido (disco
desequipado y disco descartado del mismo slot) eran clones del disco real, así que colarlos al
baseline daba el mismo número y el test pasaba en verde. Ahora el desequipado puntúa peor y el
descartado mejor.

Por qué el test existente no lo veía: `test_optimizer_miyabi.py::test_best_build_beats_baseline`
afirma `score_total > score_actual`. Con baseline 0 eso es verdad por construcción — el bug hacía
pasar el test.

## 5. Observaciones abiertas (no verificadas, no tocadas)

Con el arreglo, sobre la copia de la DB real: 0/51 PJs con baseline 0, pero **51/51 siguen
mostrando delta > 0**, con mediana de delta 12.8 contra mediana de `score_actual` 11.9 — el
optimizador dice que casi todo PJ puede duplicar su score. Dos causas candidatas, a medir antes de
afirmar nada:

1. **Swaps con neto ≤ 0 igual entran a la build.** RF-06 §4.3 dice *"sólo se proponen swaps con
   swap_neto > 0"*. En el código, `_compute_swaps` filtra la *lista de swaps*, pero el disco ajeno
   ya quedó elegido en `chosen_discs`: la build lo usa aunque el neto sea negativo.
2. **El filtro de mains por arquetipo excluye builds reales.** El disco de slot 4 de Miyabi es
   `Daño Crítico`, y su arquetipo (ANOMALY) solo admite `Maestría de Anomalía` / `ATK%` en slot 4:
   su propio disco no es candidato. (Por eso el test usa `ATK%` en ese slot.) Si el arquetipo
   primario de Miyabi es el correcto es una pregunta de datos, no de este fix.

## 6. Verificación

- Tests nuevos: 2 passed; 3 mutaciones en rojo.
- Suite completa: **exit code 0** — 2081 passed, 482 skipped, 15:30 (en paralelo corría la suite de
  otra sesión). `test_optimizer_miyabi.py` corre (no skip) y sigue verde con el baseline real.
- DB de dominio: sin escrituras (sha256 igual; el fixture de sesión `_domain_db_untouched` lo
  vuelve a verificar al final de la suite).

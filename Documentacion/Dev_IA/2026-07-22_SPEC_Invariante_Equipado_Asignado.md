# SPEC — Invariante `equipado` / `agente_asignado` en `inventory_discs`

**Fecha:** 2026-07-22
**Estado:** 📋 ESPECIFICADO — **NO implementado** (decisión de Daniel: la DB está muy desactualizada
respecto del juego; no se toca hasta re-sincronizar).
**Origen:** conversación con Daniel a raíz del "agujero del disco suelto" (ver
[2026-07-19_IMPL_Reemplazo_Disco_S23.md](./2026-07-19_IMPL_Reemplazo_Disco_S23.md)).

---

## 1. El problema que lo disparó

Al explicar por qué equipar un disco suelto atribuido a otro PJ inserta un duplicado, Daniel
objetó el estado en sí:

> "dices que si inserto un disco libre pero que esta atribuido a otro pj eso no tiene sentido"

Tenía razón. El estado existe hoy porque `set_unequipped` conserva el dueño al desplazar un disco,
lo que produce una tercera combinación de campos que **no corresponde a nada del juego**.

Inventario al 2026-07-22 (367 discos no descartados):

| `equipado` | `agente_asignado` | cantidad | significado |
|---|---|---|---|
| 1 | NOT NULL | 292 | lo lleva ese PJ |
| 0 | NULL | 72 | libre |
| 0 | NOT NULL | **3** | ⚠️ "libre pero de alguien" — el estado espurio |

Los 3: id=153 y id=155 (Manato, desplazados por Tecno Plácido), id=25 (Velina, Jazz Caótico
desplazado por Salón huracanado en el QA del 2026-07-20). **No son data sucia**: son el residuo
normal de cada swap. El pool crece con el uso.

---

## 2. La regla (dictada por Daniel)

> "cuando ocurre un reemplazo solo cambia la asignacion y cuando se equipa un disco libre viniendo
> de un disco ya equipado (ejem velina tiene slot 1 equipado pero lo cambio por un disco slot 1
> libre el primero se le quita asignado y equipado)"

Formalizada:

**R1 — Reemplazo entre PJs (S23).** El disco que se mueve **conserva su fila** y solo cambia
`agente_asignado` (origen → destino). `equipado` sigue en 1. No se borra ni se reinserta.

**R2 — Disco desplazado.** Cuando un disco entrante ocupa un slot ya ocupado, el saliente pierde
**ambos** campos: `equipado=0` **y** `agente_asignado=NULL`. Queda libre de verdad.

**Invariante resultante — solo dos estados legales:**

```
(equipado=1, agente_asignado=X)     → lo lleva X
(equipado=0, agente_asignado=NULL)  → libre
```

`(equipado=0, agente_asignado NOT NULL)` pasa a ser **estado ilegal**.

### Por qué R2 es la correcta

ZZZ **no recuerda** quién llevaba un disco que sacaste: vuelve al inventario general y listo.
Conservar el dueño anterior es información que la app se inventa — no la observó, la dedujo — y
además contradice lo que el jugador ve en pantalla. Bajo RNF-02, un campo que no se puede
confirmar contra el juego debe ser NULL, no un valor histórico.

---

## 3. Estado del código (verificado 2026-07-22)

| Regla | Código | Veredicto |
|---|---|---|
| **R1** | [`sync_equip.py:430`](../../app/core/sync_equip.py) — `update_assignment(to_move.id, agente_id, equipado=1)` sobre la fila existente | ✅ **ya se cumple** |
| **R2** | [`repositories.py:391-395`](../../app/db/repositories.py) — `set_unequipped()`: `UPDATE ... SET equipado=0`, docstring dice explícitamente *"Conserva agente_asignado y data"* | ❌ **no se cumple** |

Llamadores de `set_unequipped` (los dos son desplazamiento, ambos deben cumplir R2):
- `sync_equip.py:428` — desplazado por un disco que se mueve (trigger `s17_move` / `s17_reequip`).
- `sync_equip.py:439` — desplazado por un disco nuevo (trigger `s17_swap`).

---

## 4. ⚠️ Acoplamiento — no se puede aplicar R2 sola

`find_swap_candidates_by_identity` ([`repositories.py:330-365`](../../app/db/repositories.py))
busca la fila existente para **mover en vez de duplicar**. Acepta dos orígenes:

```sql
  (equipado=1 AND agente_asignado IS NOT NULL AND agente_asignado<>?)   -- equipado por OTRO PJ
  OR (equipado=0 AND agente_asignado IS NOT NULL AND agente_asignado=?) -- desequipado DEL DESTINO
```

La segunda rama (línea 352) **depende de que el desplazado conserve el dueño**. Si se aplica R2,
el desplazado pasa a `agente_asignado=NULL` y esa rama deja de encontrarlo → **cada re-equipar un
disco propio desplazado insertaría un duplicado**. Es exactamente el caso de Velina devolviéndose
su Jazz Caótico.

**Conclusión: R2 y la ampliación de la búsqueda de candidatos son un solo cambio, no dos.**

### Ampliación propuesta (a validar cuando se implemente)

Aceptar como candidato **cualquier disco no descartado** con identidad coincidente —incluidos
sueltos sin dueño— y compensar el riesgo endureciendo la abstención: contar los matches sobre el
**inventario completo** y mover **solo si hay exactamente uno**. Hoy el filtro es angosto y por eso
el "exactamente uno" es fácil de cumplir; la propuesta invierte el criterio: **buscar ancho, exigir
unicidad estricta**.

Riesgo residual: la identidad es (set, slot, nivel, main, {substat+rolls}) — **omite los valores
numéricos** por ruido de OCR. Dos discos gemelos por esa firma son indistinguibles; ante ≥2
matches se abstiene y se inserta fila nueva (duplicado). Es el trade-off aceptado de RNF-02:
mejor duplicar que robarle un disco a otro PJ por colisión de firma.

### No afectado

[`optimizer.py:360`](../../app/core/optimizer.py) — `if not disc.equipado or disc.agente_asignado is None`
exige **ambas** condiciones, así que ignora los sueltos con o sin dueño. Sin cambios.

---

## 5. Trabajo pendiente cuando se implemente

Precondición: **re-sincronizar la DB con el juego** (hoy divergen; ver §1). Sin eso, cualquier
migración de los 3 estados espurios opera sobre data que no refleja la cuenta.

1. `set_unequipped` → `UPDATE ... SET equipado=0, agente_asignado=NULL`. Actualizar el docstring
   (hoy afirma lo contrario).
2. Ampliar `find_swap_candidates_by_identity` según §4 + unicidad estricta sobre inventario completo.
3. Migración de saneamiento: `UPDATE inventory_discs SET agente_asignado=NULL WHERE equipado=0
   AND agente_asignado IS NOT NULL AND descartado=0` (3 filas hoy) — con backup + transacción +
   `PRAGMA foreign_key_check` + `PRAGMA integrity_check` (RNF-01).
4. Considerar un `CHECK` en el schema que haga el estado ilegal imposible de escribir, en vez de
   depender de que todos los callers se acuerden.
5. Tests: el invariante como propiedad (ningún camino de escritura produce el tercer estado) +
   regresión del re-equipar-propio-desplazado sin duplicar.

---

## 6. Decisiones abiertas

- **¿Los 72 sueltos sin dueño entran en la búsqueda de candidatos?** Con R2 aplicada la pregunta
  se vuelve obligatoria: los desplazados caen en ese pool. Recomendación: sí, con unicidad
  estricta (§4).
- **¿`CHECK` en schema o disciplina en los repos?** El `CHECK` es más barato de mantener pero
  requiere migración de schema.

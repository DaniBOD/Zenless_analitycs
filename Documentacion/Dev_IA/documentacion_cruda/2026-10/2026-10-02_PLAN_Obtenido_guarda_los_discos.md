# PLAN · El "Obtenido" guarda los discos (2026-10-02)

SPEC: `2026-10-02_SPEC_Obtenido_guarda_los_discos.md` (puntos 1-6). Aprobado por Daniel el
2026-10-02. Orden: primero la regla que arregla los datos mal guardados (T1-T3), después las
pantallas que confirman (T4) y recién al final el camino nuevo que escribe (T5).

## Reglas para todas las tareas

- Un commit por tarea, mensaje por archivo, `Co-Authored-By: Claude Opus 5.5`.
- Tests que leen la DB de dominio, sobre una COPIA. sha256 de la DB real igual antes y después.
- Un sabotaje por regla (`count == 1`, `scratchpad/sabotaje_generico.py`): tiene que salir ROJO.
- Ediciones grandes por script Python (`PYTHONIOENCODING=utf-8`). Sin subagentes, sin rebuild.
- Suite completa con la app cerrada (verificado por CommandLine) antes del push.

## T1 · `es_el_mismo_disco(antes, ahora)` — la única autoridad

`app/core/mismo_disco.py`, función pura. Quien llama ya comprobó **set y slot** (cada uno con su
resolver); acá se mira lo que distingue dos discos del mismo set y slot:

- **main** igual (normalizado con `_norm_key`);
- **nivel** que no baja (si alguno es `None`, no se usa);
- con **el mismo nivel**: los mismos substats con los mismos rolls (nada pudo cambiar);
- con **nivel mayor**: los substats de antes ⊆ los de ahora, y cada roll de ahora ≥ el de antes
  (al subir, los substats sólo se suman y los rolls sólo crecen).

Acepta `DiscParsed` (`main_stat_canon`/`raw`, subs con `nombre_canon`/`raw` y `rolls`) y `Disc`
(`main_stat`, subs `(nombre, valor, unidad, rolls)`).

Tests (`test_mismo_disco.py`) con los casos reales del QA:
- #408 PRE (CD, Maestría, DEF) vs #396 (DEF%, ATK, DEF, Prob. Crítica) → **distinto**;
- PRE Nv 0 (Maestría, Prob. Crítica, DEF) vs POST Nv 3 (+ DEF%) → **el mismo**;
- #402 viejo (PV%, ATK%, DEF, ATK) vs nuevo (DEF%, Maestría, ATK%, PV%) → **distinto**;
- mismo nivel, un substat distinto → distinto; un roll que baja → distinto; main distinto →
  distinto; Nv 0 de 3 substats vs Nv 0 de 4 → distinto; `Disc` vs `DiscParsed` → anda.

Sabotajes: sin la guarda de main; sin la de rolls; con el mismo nivel aceptando ⊆.

## T2 · La confirmación de una mejora usa la regla (punto 4)

`sync_upgrade.UpgradeSyncer.on_post_upgrade_disc`: además de `_same_disc_canon` (set + slot),
`es_el_mismo_disco(pre.parsed, disc)`. Si no, `return` sin tocar el pendiente (sigue esperando a
su disco o vence).

Tests: el caso #408/#396 (otro disco del mismo set y slot NO confirma, el pendiente sigue vivo y
después confirma con el bueno); el camino feliz sigue igual. Ajustar los tests de
`test_sync_upgrade*` que armen POST con substats que no contienen a los del PRE.

Sabotaje: sin la llamada.

## T3 · S17 no pisa la fila con otro disco del mismo set (punto 6)

`sync_equip.persist_s17_disc` (`:482`): `slot_disc.set_id == set_id and
es_el_mismo_disco(slot_disc, parsed)` → `s17_update`; si no, el camino de disco DISTINTO que ya
existe (`_find_disc_to_move` → re-equipa la fila libre del entrante; si no hay, `s17_swap`).

Tests sobre una copia: el caso #402/#419 (el entrante libre se re-equipa, el viejo queda libre, no
se pisa ni se inserta); el refresco tras una mejora sigue siendo `s17_update`.
FK e integridad después.

Sabotaje: volver a comparar sólo el set.

## T4 · El "Ver" y el inventario confirman la mejora (puntos 3 y 5)

`monitor.py`:
- `_process_disc` (S6/S7, one-shot): con `disc_is_mature(disc)` → `on_post_upgrade_disc(disc)`,
  en su try, antes de `on_disc` (como S17).
- `_emit_s9_disc` (o donde S9 emite el disco maduro): lo mismo.

Tests con un `UpgradeSyncer` espía: S7 maduro confirma; S7 inmaduro no; S9 confirma.

Sabotajes: sin la llamada en S6/S7; sin la guarda de madurez; sin la llamada en S9.

## T5 · S22 guarda el disco, con memoria por tanda (puntos 1 y 2)

- **Monitor:** `_process_s22_detail` marca `d.equip_libre = True` (como `rareza="S"`).
- **`persist_s17_disc(..., es_drop=True, trigger=...)`:** el trigger deja de estar fijo en
  `s3_drop_insert`; S22 usa `s22_drop_insert`.
- **`FarmSession`:** `guardados` = ids de filas insertadas por S22 en la tanda; `nueva_tanda()`
  los vacía (lo llama `set_usos`, S21 = otro "Obtenido"); van al breadcrumb y `restore` los
  recupera.
- **Controlador**, rama S22 (como S3, en su propio try): si alguna fila de `guardados` es el mismo
  disco (`es_el_mismo_disco(fila, parsed)`, mismo set y slot) → no inserta, usa esa fila para la
  sugerencia. Si no → inserta y anota el id. Readonly: no inserta ni anota.

Tests sobre una copia: primer clic inserta (`s22_drop_insert`); el mismo disco otra vez no;
mejorado (POST) tampoco; otra tanda sí; restore del breadcrumb mantiene la memoria; readonly no
escribe; FK e integridad.

Sabotajes: sin `equip_libre`; sin el chequeo de la memoria; sin `nueva_tanda`; sin el breadcrumb.

## T6 · Cierre

Suite completa + push. QA en vivo con Daniel (farmear por baterías, clic en el Obtenido →
`s22_drop_insert`; "Ver" → mejorar → "Ver" → `s10_upgrade_update`; volver al Obtenido → no
reinserta; S9 → `libre_update`; cambiar un disco por otro del mismo set en S17 → `s17_reequip`).
SPEC con la tabla de commits, índice, memoria.

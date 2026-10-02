# SPEC · El "Obtenido" de las baterías guarda los discos (2026-10-02)

**Estado:** alcance decidido por Daniel el 2026-10-01 a la noche (dos preguntas, las dos en la
opción recomendada). Aprobado el 2026-10-02 ("R14 se queda igual entonces, veamos el 1 del spec de
obtenido"). Plan: `2026-10-02_PLAN_Obtenido_guarda_los_discos.md`.

## Qué pidió Daniel

Farmeando por baterías para Claret Flint, mejoró un disco desde el "Obtenido" (S22 → "Ver" → S10)
y la DB no cambió. Al explicarle que S22 sólo lee:

> "si, que el obtenido guarde los discos en la DB"

Y, preguntado:

| pregunta | decisión |
|---|---|
| ¿la mejora confirmada en el "Ver" (S6/S7) actualiza la fila? | **Sí, las dos partes** |
| reinicio de la app con el Obtenido abierto | **Recordar lo guardado** (no reinsertar) |

## Lo que hay hoy (leído en el código, 2026-10-01)

- **S22 sólo lee.** `Monitor._process_s22_detail` parsea el panel DETAIL (el disco
  seleccionado, completo) y lo manda por `on_disc` con `rareza="S"`. El controlador lo enruta a
  `_build_payload` (sugerencia + toast) y **no persiste**. La grilla (`_process_s22_grid`) sólo
  da set y slot por corrida: no tiene stats, no se puede guardar.
- **S3 sí guarda** desde el 2026-09-05: `persist_s17_disc(parsed, es_drop=True)` →
  `_persist_disco_libre`, que con `es_drop` **inserta siempre** (un evento, no una
  observación), trigger `s3_drop_insert`. Exige `equip_libre=True`. Respeta readonly.
- **La mejora** se persiste sólo desde el camino CONFIRMADO: `UpgradeSyncer.on_post_upgrade_disc`,
  llamado desde S17 (equipamiento) y S5 (afinación), con el disco **maduro**.
  `actualizar_por_mejora` busca la fila por la identidad **del PRE** y valores; con exactamente
  un libre la actualiza. El "Ver" (S6/S7) **no confirma**: el recorrido de Daniel
  (S22 → S7 → S10 → S20 → S7) termina en el resumen "sin confirmar" y no escribe.
- **El dedup de S22** (`_s22_disc_ids`, identidad = set, slot, main, nombres + rolls de los
  substats) **se borra cada vez que el estado deja de ser S22** (`monitor.py:1341`). Hoy da igual
  —es display—, pero con persistencia volver al Obtenido después de un "Ver" o de un parpadeo
  del detector **reinsertaría** el mismo disco.
- **Contexto de farmeo:** S22 no hace nada sin `_farm_session` (lo arma S13). En producción un
  reinicio de la app lo pierde; sólo en QA (`-RestoreFarm`, breadcrumb `DANIBOD_FARM_STATE`)
  se recupera. O sea: el reinsertado por reinicio sólo puede pasar donde hay breadcrumb.

## Diseño

### 1 · S22 persiste el disco del panel DETAIL

- El controlador trata S22 como S3: `persist_s17_disc(parsed, es_drop=True)` en su propio try
  (el toast no depende de que la DB escriba), y el `result` pasa a `_build_payload` → la
  sugerencia se calcula sobre la fila guardada.
- El monitor marca `equip_libre=True` en el disco de S22: todo drop entra libre (mismo invariante
  que `rareza="S"`: el Obtenido sólo lista lo que acaba de entrar).
- Trigger propio para la auditoría: `s22_drop_insert` (hoy el nombre está fijo en
  `s3_drop_insert`).
- Sólo se guarda **lo que se clickea**: un disco que no se selecciona en el Obtenido no tiene
  stats leídos. La grilla sigue logueando el conteo por corrida, que es lo que permite ver la
  diferencia.

### 2 · Memoria de "ya guardado" por tanda, no por pantalla

- La identidad de lo guardado se recuerda en la **tanda de farmeo** (`FarmSession`), no en el
  estado del monitor: sobrevive a un "Ver", a una mejora y a los parpadeos de S22.
- Se vacía cuando empieza **otra tanda** (S21 con un uso nuevo: otro "Obtenido").
- Con breadcrumb (`DANIBOD_FARM_STATE`) se escribe ahí también, y `-RestoreFarm` la recupera:
  un reinicio con el Obtenido abierto no reinserta (decisión de Daniel).
- El dedup visual de hoy (`_s22_disc_ids`, el aviso "ya capturado") queda como está.

### 3 · La mejora confirmada en el "Ver" actualiza la fila

- `_process_disc` (S6/S7, one-shot) llama a `on_post_upgrade_disc(disc)` **sólo si el disco está
  maduro** (`disc_is_mature`, la misma guarda que S17). Un frame inmaduro se abstiene → queda el
  resumen "sin confirmar", como hoy (RNF-02: no escribir substats sin confirmar).
- `actualizar_por_mejora` no cambia: busca por el PRE (la fila que insertó S22) y la migra.
- La memoria de la tanda **suma la identidad del POST**: si después se vuelve al Obtenido y el
  panel muestra el disco ya mejorado, no se inserta un segundo.

### 4 · La confirmación de una mejora exige que sea EL MISMO disco (bug visto en vivo)

QA 2026-10-02 00:01: `_same_disc` / `_same_disc_canon` comparan **sólo set + slot**. Daniel mejoró
un Rosa espinosa slot 1 libre (#408, Nv 0) y fue al equipamiento de Claret, que lleva OTRO Rosa
espinosa slot 1 (#396): ese disco confirmó la mejora y `actualizar_por_mejora` le escribió a #408 los
stats de #396. Con más pantallas confirmando (punto 3), el error se multiplica.

- La confirmación exige además **el mismo main** y que **los substats del PRE estén todos en el
  POST** (al subir de nivel los substats sólo se suman: el 4.º aparece en +3, ninguno se va).
- Si no coincide, no confirma: el pendiente sigue esperando o vence (resumen "sin confirmar").

### 5 · El inventario (S9) también confirma

QA 2026-10-02 00:02: Hado emplumado slot 1 mejorado 0 → 3 desde el "Ver" y mirado en S9 →
`libre_insert` #412 al lado de la fila vieja #411 (Nv 0): fantasma. S9 emite el disco maduro igual
que S17; pasa a llamar `on_post_upgrade_disc` con la guarda del punto 4.

### 6 · S17 no pisa la fila del slot con OTRO disco del mismo set (bug 3 del QA, diagnosticado)

QA 2026-10-02 00:22: Daniel le cambió a Claret el slot 4 Rosa espinosa por OTRO Rosa espinosa.
`persist_s17_disc` (`sync_equip.py:482`) decide "mismo disco (refresco tras upgrade)" con **sólo
`slot_disc.set_id == set_id`** → `s17_update` sobrescribió #402 con el disco nuevo. El viejo
desapareció de la DB y el nuevo quedó dos veces (#402 y el `libre_insert` #419 de 5 s antes). Pasó
también con los slots 1 y 2 (la DB quedó bien de casualidad: ver el audit).

- "Mismo disco" pasa a ser la regla del punto 4 (mismo main, substats del de antes ⊆ los de
  ahora, nivel que no baja). Si no se cumple, sigue el camino que ya existe para un disco
  DISTINTO y el viejo se desequipa (`set_unequipped`) en vez de pisarse.
- **Corrección al implementar:** ese camino NO encuentra la fila libre del entrante (#419):
  `find_swap_candidates_by_identity` deja afuera a los libres a propósito (entre gemelos se
  adoptaría el equivocado). La evidencia la tiene el monitor: el check "LIBRE → PJ · CAMBIÓ ✓"
  (badge Y botón) vio ESTE disco pasar de libre a este PJ, y su comentario decía "no hay fila que
  mover" — falso desde agosto, cuando los libres empezaron a guardarse. Ahora marca
  `equipado_desde_libre` y `_find_disc_to_move` adopta la fila libre **sólo si hay exactamente
  una** con esa identidad (gemelos → se abstiene e inserta, como hoy). Trigger `s17_equipa_libre`.
  Mismo patrón que el hint del diálogo S23.

### Una sola autoridad para "¿es el mismo disco?" (B1)

Los puntos 4 y 6 son la misma pregunta. Va UNA función pura, `es_el_mismo_disco(antes, ahora)`
(`app/core/mismo_disco.py`), que usan `sync_upgrade` (confirmación) y `sync_equip` (refresco de
S17). Acepta un `DiscParsed` o un `Disc` de la DB.

## Lo que queda afuera (dicho, no olvidado)

- **Gemelos dentro de una tanda:** dos drops con el mismo set, slot, main y los mismos 3
  substats (a Nivel 0 los valores son fijos por stat) tienen la misma identidad: el segundo no se
  guarda. Es la limitación que ya tiene el dedup visual; la grilla muestra el conteo real y el
  censo del inventario lo reconcilia. Contarlos por la grilla es otro cambio.
- **Discos no clickeados** en el Obtenido: no se guardan (no hay stats).
- Toast, sugerencia y card: sin cambios (paso 8).

## A verificar en el QA en vivo

1. ~~¿Al volver al Obtenido después de mejorar desde el "Ver", el panel muestra el disco mejorado
   o el de Nivel 0?~~ **Verificado en vivo (2026-10-02 00:05:31): lo muestra MEJORADO** (Rosa
   espinosa slot 5, Nv 0 → 15 desde el "Ver", y al volver el Obtenido lo lee Nv 15/15 con sus 4
   substats). La memoria de la tanda tiene que sumar la identidad del POST: hace falta.
2. El recorrido completo: farmear → clic en el Obtenido (inserta, una línea `s22_drop_insert`)
   → "Ver" → mejorar → "Ver" (actualiza, `s10_upgrade_update`) → S9 encuentra la fila (no inserta
   otra).
3. RNF-01: backup de sesión, FK e integridad después de la tanda.

## Implementación (2026-10-02)

| tarea | commit | qué | sabotajes |
|---|---|---|---|
| T1 | `d11a0b2` | `es_el_mismo_disco` (`app/core/mismo_disco.py`), la única regla | 5 |
| T2 | `bdb48dc` | la confirmación de una mejora la exige (punto 4) | 2 |
| T3 | `42ed8e5` | S17 no pisa la fila; el libre recién equipado se adopta con `equipado_desde_libre` (punto 6) | 5 |
| T4 | `0e371e2` | el "Ver" (S6/S7) y S9 confirman la mejora, sólo con el disco maduro (puntos 3 y 5) | 4 |
| T5 | `13590b7` | S22 guarda (`s22_drop_insert`) con la memoria de la tanda en `FarmSession` (puntos 1 y 2) | 9 |

Hallazgos al implementar:

- **Punto 6 corregido:** `find_swap_candidates_by_identity` deja afuera a los libres a propósito
  (gemelos), así que el camino de "disco distinto" no encontraba la fila libre del entrante. La
  evidencia la tenía el monitor (check "LIBRE → PJ · CAMBIÓ ✓"), cuyo comentario decía "no hay fila
  que mover" — falso desde que los libres se guardan.
- **El desplazado conserva el dueño** (`set_unequipped`): el invariante R2 del 2026-07-22 sigue
  frenado por Daniel; los tests lo asumen así.
- **Un test viejo** (`test_persist_s17_update_mismo_pj_slot`) armaba como "refresco" dos discos Nv 15
  con substats distintos — imposible en el juego. Sus datos ahora son un refresco posible.
- **La memoria de la tanda no se acopla a la mejora:** guarda ids de filas y pregunta
  `es_el_mismo_disco(fila, lo_visto)`, que acepta el disco crecido. Cubre el POST sin que S10 avise.
- **Riesgo aceptado:** si S17 o el "Ver" leen mal un substat de un disco ya guardado, la regla lo
  ve como OTRO disco (antes, con sólo el set, se pisaba igual). Lo protege la madurez del
  aggregator; si aparece, el QA lo muestra como `s17_swap` donde se esperaba `s17_update`.

## Reglas

RNF-01 (el camino nuevo escribe la DB: backup, transacción, `foreign_key_check`,
`integrity_check` en los tests sobre una copia). Un sabotaje por regla, sha256 de la DB real igual
antes y después de cada corrida. Suite completa antes del push, con la app cerrada.

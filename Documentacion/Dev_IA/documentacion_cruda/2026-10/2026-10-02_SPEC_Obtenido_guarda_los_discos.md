# SPEC · El "Obtenido" de las baterías guarda los discos (2026-10-02)

**Estado:** alcance decidido por Daniel el 2026-10-01 a la noche (dos preguntas, las dos en la
opción recomendada). Falta aprobar este SPEC y el plan.

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

## Reglas

RNF-01 (el camino nuevo escribe la DB: backup, transacción, `foreign_key_check`,
`integrity_check` en los tests sobre una copia). Un sabotaje por regla, sha256 de la DB real igual
antes y después de cada corrida. Suite completa antes del push, con la app cerrada.

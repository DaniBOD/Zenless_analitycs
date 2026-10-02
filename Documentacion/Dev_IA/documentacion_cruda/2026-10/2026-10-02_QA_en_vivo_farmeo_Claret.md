# QA en vivo · farmeo de Claret Flint con la app escribiendo (2026-10-01/02)

Primera sesión larga con el **paso 8** (sugerencias en vivo) y la app en **modo escritura**:
farmeo por baterías (S21/S22), afinación (S4/S5), mejoras (S10), equipamiento (S17), inventario
(S9) y desmontaje (S11). ~23:35 → 00:23. Log: `app.log` de esa ventana. Correcciones de la DB:
`audit/correcciones_farmeo_claret_20261002.md`.

**Resultado para Daniel:** Claret terminó con su build completa y el slot 6 **DEF%** que le faltaba
(#417); slot 4 cambiado por uno con DEF% +2.

## Lo que anduvo

- **Lectura de discos:** S22 (panel DETAIL), S5, S6/S7, S9, S17 y S10 leyeron set, slot, main,
  substats y rolls sin errores de OCR en los stats en toda la sesión.
- **Mejoras confirmadas por la afinación (S5→S10→S5):** el resumen y la confirmación salieron bien
  (Rosa espinosa slot 4 y slot 5, 0→15).
- **S17** registró los cambios de equipo de Claret por (PJ, slot); el desmontaje dio de baja lo que
  estaba en la DB (2 + 1) y separó lo que no (19 + 10 + 4) sin ambiguos.
- **Paso 8:** ningún error del cálculo de la sugerencia (`[sugerencia] falló` = 0).

## Bugs encontrados (por orden de gravedad)

1. **La confirmación de una mejora compara sólo set + slot** (`_same_disc` / `_same_disc_canon`,
   `sync_upgrade.py`). Con un disco del mismo set y slot equipado en el PJ que se mira después, ese
   disco confirma la mejora y `actualizar_por_mejora` le escribe sus stats a la fila mejorada.
   Pasó **dos veces** (#408 ← stats de #396; #406 ← stats de #397). → SPEC punto 4.
2. **Mejorar desde el "Ver" (S6/S7) o mirar el disco después en el inventario (S9) no confirma
   la mejora** → la fila vieja queda en Nv 0 y S9 inserta otra: **fantasma** (#409, #411, #413).
   → SPEC puntos 3 y 5.
3. **Un disco recién equipado visto como LIBRE se inserta otra vez** (#419, 5 s después de que S17
   lo guardara en #402). La guarda "libre con la identidad de un equipado" frenó el caso del slot
   6 (#416) pero no éste. **Sin diagnosticar**: comparar las dos líneas del log antes de teorizar.
4. **Badge de dueño mal leído en S9:** el Rosa espinosa de Claret se leyó con el badge de Sunna →
   `s17_move` a Sunna y #33 desplazado. S17 lo devolvió a Claret, pero #33 quedó desplazado.
   (Un mismo disco en S9 y S17 con dueños distintos: S17 manda, pero el desplazado no se repara.)
5. **El cambio de slot 6 (#416 → #417) no se registró:** el check del pendiente vio un disco que no
   coincidía y se abstuvo. Correcto por RNF-02, pero el usuario lo vio como "no lo detecta".
6. **Título "(1)" del Obtenido** — ARREGLADO en la sesión (`c404d3b`): el OCR se comía el "1".
7. **Grilla de S22 cierra una corrida con "0 discos S"** después de haber mostrado ≥3 (00:06:19).
   Display-only.

Corregido en la DB (con la app cerrada, ensayo en copia, backup, FK e integridad): ver el audit.

## Lo que Daniel pidió que falta: "mejorá este disco para ver si le sirve a un PJ"

> "siento que si recomendaba guardar discos pero le faltaba la predicción de 'mejora este disco
> para ver si le sirve a un pj' — como pudiste ver realicé eso varias veces"

**Lo que hace hoy el motor** con un disco < Nv 15 (`_recomendar_por_potencial`, casos 6/7, R11-R14):
calcula el **valor esperado** subido y

- **MEJORAR → PJ** si lo esperado le gana a lo que ese PJ lleva en el slot (R12);
- **GUARDAR (sin subir)** si sirve pero lo esperado no le gana a nadie;
- descartar si tiene dos líneas muertas (R13).

Y R14 (septiembre) dice: *"Daniel igual sube todo para ver el valor final, pero la recomendación es
frenar"*. O sea: **el "subir para ver" quedó fuera del motor a propósito.** Lo que Daniel pide ahora
lo trae adentro.

**El caso que lo muestra:** Rosa espinosa slot 4 Prob. Crítica, Nv 0 (DEF% 4,8 · ATK% 3 · Maestría
9). Por lo esperado no le ganaba al slot 4 de Claret → no decía MEJORAR. Subido cayó DEF% +2 y PV% +2
y **sí le ganó**: Daniel se lo equipó.

**Idea a diseñar (no decidida):** además de lo esperado, la **probabilidad de que le gane** a lo
que el PJ lleva — p. ej. "PROBAR → Claret (≈ 1 de 3)". Se puede enumerar: 5 mejoras hasta el 15,
cada una a uno de los substats. Lo que **no** sabemos es la probabilidad de cada substat cuando se
desbloquea el 4.º, ni si el reparto de rolls es uniforme: RNF-02, no inventarla — o se toma de una
fuente, o se acota (peor/mejor caso) sin pesos.

## Siguiente

1. Aprobar el SPEC de S22 (`2026-10-02_SPEC_Obtenido_guarda_los_discos.md`, puntos 1-5) y su plan.
2. Diagnosticar el bug 3 con el log.
3. Decidir con Daniel la predicción de "probar".

---

# Sesión 2 · QA en vivo del SPEC del "Obtenido" (2026-10-02, 10:22 → 11:58)

App en modo escritura con los 5 commits del SPEC activos (`d11a0b2`…`13590b7`). Correcciones de la
DB al cierre: `audit/correcciones_farmeo_claret_20261002.md` §4.

## Lo que se verificó en vivo

| paso del SPEC | visto | resultado |
|---|---|---|
| S22 guarda lo que se clickea | ~20 `s22_drop_insert` (#420…#461) | ✅ |
| volver al Obtenido no reinserta | "ya guardado en esta tanda" (#422, #426, #461) | ✅ (salvo #444, ver bug 1) |
| la mejora desde el "Ver" se confirma | #420, #443 | ✅ |
| S9 confirma la mejora | #432, #434, #449, #423, #404 | ✅ (2 s en el camino feliz) |
| S17 no pisa la fila con otro disco del mismo set | Remielle s3 (#3 → #463), Claret s1 (#396 → #465) | ✅ el viejo conserva SUS stats |
| el libre recién equipado se adopta | — | ❌ no se armó el aviso (bug 4) → duplicados #443/#463, #404/#465 |
| refrescos de S17 sin cambio | Remielle 6/6, Claret 6/6 | ✅ `s17_update` |

## Bugs (en orden de lo que cuestan en datos)

1. **El Obtenido leyó un roll de menos** ("Maestría de Anomalía 18" con 0 rolls) → la memoria de la
   tanda no reconoció al #443 mejorado → #444. **ARREGLADO** en la sesión (`b177e4e`): rolls desde
   el valor con `VALOR_POR_MEJORA`. Decisión de Daniel ("hacé el 1").
2. **Mejoras que no se confirman** → la fila queda vieja (#422, #426, #431). Tres causas distintas:
   - S10 leyó el PRE ya en Nv 3/4 (mejora rápida: 2-3 s en S10) → "no subió de nivel";
   - el "Ver" descartado por confianza 0,69 (< 0,70) dos veces seguidas;
   - **la captura se reinició** (10:36:36, 10:39:25, 10:53:12; `controller.stop`) y el pendiente
     se perdió. **Fue Daniel** (confirmado): "siempre que no capta algo trato de reiniciar el
     detector". O sea: el reinicio es el síntoma de que algo no se detectó, y borra los pendientes
     que viven en el monitor (mejora, swap, libre→PJ).
   Daniel: "a veces no detecta la mejora porque no me dan materiales de vuelta" — a contrastar con
   estas tres causas antes de teorizar otra.
   **Arreglo propuesto (no hecho):** cuando el Obtenido muestra un disco de la tanda más crecido,
   actualizar esa fila (es de la tanda y `es_el_mismo_disco` lo confirma).
3. **Demora de 37 s** en confirmar el #443 (el "Ver" lo vio en Nv 15 a las 10:33:27, la fila se
   actualizó a las 10:34:04): mientras tanto la card mostró DESCARTAR sobre el Nv 0.
4. **La grilla de selección leyó "equipado · dueño incierto" un disco LIBRE** (#443, 10:55:21) → no
   se armó "libre → PJ", S17 hizo `s17_swap` y el disco quedó dos veces. Pasó también con Claret
   s1 (#404 → #465). Es el caso común de "equipar lo que sugiere el motor".
   Opciones: armar el aviso también con "equipado · dueño incierto" + botón "Reemplazar", o leer
   mejor el badge de la grilla.
5. **El resumen de la mejora no muestra el substat nuevo** (`_roll_diff`: entra con 0 rolls → delta
   0) → "nivel 0→4 · sin cambio de roll" con DEF% recién destrabado. Sólo el mensaje.
6. **Stats de Claret en S18** (10:58:53): Prob. Crítica 112,3 % (¿12,3 %?), ATK y Recarga sin leer,
   y el log igual dice "11/11 stats capturados". Velina, leída justo antes, salió perfecta →
   hipótesis: el perfil de Armero (LAC/AF) corre las filas.
7. **Ruido conocido:** el "Obtenido" de la moneda del evento (gastar baterías) entra como S24 y se
   abstiene ("sin tanda de desmontaje abierta"). Correcto; aclarado por Daniel.

## Siguiente

Prioridad por datos: bug 4 (duplicado en cada equipamiento sugerido) y bug 2 (el arreglo propuesto
del Obtenido + diagnosticar los reinicios). Después 3, 6 y 5.


## Arranque de la próxima sesión: el duplicado al equipar (bug 4)

Daniel (2026-10-02): "si arranca por el duplicado". Estado del diagnóstico, para no rehacerlo:

- **Lo que pasa:** en el equipamiento (S17), al elegir un disco LIBRE de la grilla para un slot
  ocupado, el badge de la grilla lo lee "equipado · dueño incierto" (`monitor.py:5919`,
  `[grilla] disco equipado · dueño incierto.`) en vez de LIBRE (`:5906`). `_arm_libre_pending`
  (`monitor.py:2346`) exige `merged.equip_libre` **y** botón "equipar"/"reemplazar" → no arma →
  al confirmar, `_check_libre_equipado` nunca marca `equipado_desde_libre` → `persist_s17_disc`
  va al `s17_swap` (inserta una fila nueva; el viejo se desequipa bien). Casos: Remielle s3
  (#443 libre → #463, 10:55:21 / 10:57:19) y Claret s1 (#404 libre → #465, 11:58:23).
- **Sin verificar todavía:** si el badge falla siempre en ese flujo o sólo a veces (¿los discos
  recién mejorados? ¿el slot ocupado?). Buscar en `app.log` del 2026-10-02 los `[grilla]` previos a
  cada `s17_swap` y a los `s17_equipa_libre` (no hubo ninguno en vivo).
- **Opción A (monitor):** armar el pendiente también con "equipado · dueño incierto" + botón
  "reemplazar"/"equipar". El botón "reemplazar" aparece también para un disco de OTRO PJ (S23),
  pero ahí la DB desambigua: un disco de otro PJ no tiene fila LIBRE, así que
  `_find_disc_to_move` no adopta nada (y el camino S23 sigue igual). La guarda de "exactamente una
  fila libre" queda como red.
- **Opción B (badge):** leer mejor el badge de la grilla en ese flujo. Más cara; ver
  `project-fase5R-identidad-grilla` ("presencia gana a libre": la regla que hace que un dudoso
  salga "equipado").
- **Datos:** después de arreglarlo, en el QA: equipar un libre sugerido → `s17_equipa_libre`, sin
  fila nueva.

## Sesión 3 (sin juego, 2026-10-02 tarde): el duplicado y la mejora en vivo

Daniel: "arrancá con el duplicado, voy por la opción B" + "[la mejora] debe detectar el nivel y
constantemente verificar las stats en la pestaña de mejora y ahí mismo actualizar la db".

### El duplicado al equipar: eran DOS causas, no una

Verificado en el `app.log` (las líneas `[grilla]` y `[equipado]` antes de cada `s17_swap`):

| caso | qué pasó | causa |
|---|---|---|
| Claret s1 (#404 → #465) | el aviso libre→PJ **se armó** (11:00:14) y **se confirmó** (11:00:33 "CAMBIÓ ✓"), pero no salió ningún "Disco detectado" | el gate de `_disc_emitted` corría el check y no re-emitía; sin latch (volvía de S10) el dueño quedaba sólo observado y la clave del dedup no cambiaba → la marca nunca llegó a la DB. Una hora después, `s17_swap`. Pasó igual a las 00:01:36 y 00:08:03 |
| Remielle s3 (#443 → #463) | la grilla leyó "equipado · dueño incierto" el libre (10:55:21) → no se armó el aviso | **sin diagnosticar**: no hay capturas de ese momento |

- **Claret: ARREGLADO** (`b8f8636`). La confirmación (badge + botón) deja al destino como dueño certero
  y el gate re-emite una vez.
- **Remielle (opción B, la elegida):** las 11 capturas de libres de
  `17_Inventario_Disco_Vista_Individual_libres` siguen saliendo LIBRE con las librerías de hoy (sin
  votos, sin cara), así que un libre QUIETO se lee bien. Hipótesis sin verificar: un frame de
  transición (el detalle todavía con el avatar de Remielle, del disco anterior, con la firma nueva);
  con "presencia gana a libre" un solo frame con cara bloquea LIBRE hasta el próximo disco.
  Instrumentado (`7cab9fa`): las líneas de "dueño incierto" llevan `traza=` (una ficha por pasada:
  grilla `n/g/G` + detalle `-/t/c`, mayúscula si votó) y los votos; con `-GridDiag` se vuelca
  también el recorte del DETALLE. `gc g- g- g-` = transición; `gc gc gc gc` = cara sostenida.

### La mejora se escribe en vivo

- `99d8955`: cada subida de nivel que se VE en S10 actualiza la fila en ese momento, sin esperar la
  pantalla posterior ni el vuelto de materiales. Sólo con lectura coherente: `es_el_mismo_disco` +
  #substats + Σrolls − nivel//3 constante. Medido antes: la regla vale para 426 de 427 discos de la
  DB, y S10 lee los rolls bien en 17 de 17 capturas (05/06/19_Upgrade_*).
- `31ad52f`: el PRE leído tarde (S10 ya en Nv 3/4, la fila en Nv 0) busca la fila de un nivel
  anterior de ese disco (`find_estados_previos`: mismo disco, umbrales, valores de los substats sin
  roll nuevo). Es otra de las tres causas de las mejoras sin confirmar.
- Lo que **no** cambió: el disco equipado lo sigue actualizando la S17 por (PJ, slot). Pendiente de
  decisión de Daniel (ver abajo).

### Qué mirar en el próximo QA

1. Equipar un libre sugerido a un slot ocupado → `s17_equipa_libre`, sin fila nueva. Si la grilla
   vuelve a dudar: copiar la línea con `traza=` (y, con `qa_launch ... -GridDiag`, los
   `det_*.png`).
2. Mejorar un libre de 0 a 3 y salir → `Disco LIBRE actualizado … s10_upgrade_update` justo
   después de `[mejora] nivel 0→3`, sin esperar nada.
3. Si aparece `la lectura no cuadra con la anterior`, anotar el disco: es un paso que S10 leyó mal.

### Decisión pendiente

¿La escritura en vivo actualiza también al disco EQUIPADO? Hoy no: `actualizar_por_mejora` lo deja a
la S17 posterior por (PJ, slot), con un test que lo fija ("tocar la fila acá sería una segunda
autoridad"). Mejorando desde el equipamiento, la S17 lo refresca al volver; desde el inventario
(S9) o la tienda (S5) depende de esa pantalla.

# SPEC · RF-15 — Cosecha del detalle-badge desde S26 (+ instrumentación del dueño)

> **Fecha:** 2026-08-10
> **Estado:** diseño aprobado, pendiente de plan de implementación
> **Alcance:** display-only. Cero escrituras a la DB. Lo único que cambia de estado es la librería
> `avatar_detbadge_v2`, bajo el gate de persistencia que ya existe.

---

## 1. El problema

El QA en vivo del 2026-08-07 (`2026-08-07_QA_S30_en_vivo_y_los_tres_arreglos.md`) dejó el inventario
de W-Engines con **presencia 7/7 y nombre 3/7**: el sistema ve que el arma tiene dueño pero no sabe
decir quién. Es lo último que falta para cerrar la lectura del inventario general.

La causa está medida y es la profundidad de la librería que nombra ese badge:

| superficie | clases | refs | PJs con <3 refs |
|---|---|---|---|
| grid | 56 | 486 | 6 |
| row | 50 | 365 | 5 |
| **detail** | **50** | **184** | **9** |

`detail` es la que usan las armas y tiene **menos de la mitad** de refs que las otras dos. Ocho PJs
tienen **una sola** referencia — Antón, Ben, Billy Estelar, Cissia, Harumasa, Lycaon, N.º 0: Anby y
Rina — y con una sola ref el matcher no llega al guard y **se abstiene**, que es el comportamiento
correcto (RNF-02: un nombre equivocado es peor que ninguno).

Verificado el 2026-08-10 comparando los snapshots `..._20260731_cosecha50.npz` (166 refs) y
`..._20260807_cosecha184.npz` (184 refs): esos 8 PJs tenían **1 ref en las dos fechas**. Los +18 refs
del período fueron cosecha incidental de 3 PJs durante las sesiones de QA. La cobertura del roster
(50/50 clases) sí está resuelta desde el 2026-08-02; lo que nunca se hizo es la **profundidad**.

## 2. La asimetría que lo explica

**Las pantallas de armas consumen `avatar_detbadge_v2` pero nunca la alimentan.**

- El único punto que cosecha esa superficie es el flujo de discos: `learn_s17_detail(det, latch)` en
  `monitor.py` (S17), con el latch de identidad como etiqueta certera.
- S26 y S30 solo la *consultan* (`surfaces["detail"].match(badge.crop)`).

O sea que la calidad del dueño de un arma depende de que el usuario haya paseado antes por la
pantalla de **discos** de ese PJ. Nada en el flujo de armas mejora el flujo de armas.

Y sin embargo el flujo de armas tiene todo lo necesario:

1. **El recorte ya es compatible.** `read_weapon_owner_badge` (S26) y `read_weapon_owner_badge_s30`
   conservan a propósito el encuadre de `crop_detail_badge` (Hough + `_DET_HOUGH_PAD`) — está
   declarado en ambos docstrings, justamente para no romper la regla *like-with-like* de la Fase 5R.
   Un recorte de arma **es una referencia válida** para esa librería.
2. **Hay una etiqueta certera.** Cuando `clasificar_tenencia` devuelve `equipada`, es porque el botón
   de acción dice *Desequipar*: el juego afirma que el PJ que estás mirando la lleva puesta. El
   dueño sale del **latch**, no del badge — no es el matcher validándose a sí mismo.

## 3. La trampa: `add_reference` no dedupea

`AvatarMatcher.add_reference` agrega al final y, pasado `_MAX_REFS_PER_NAME = 10`, **desaloja la más
vieja**. No hay deduplicación por similitud.

Cosechar en cada frame o en cada visita degradaría la librería: un PJ del que se miren diez veces las
mismas armas termina con diez recortes casi idénticos —que discriminan como uno solo— **habiendo
expulsado las refs diversas que venían de los discos**. Sería el modo de falla de julio otra vez,
esta vez causado por nosotros. Los candados de §4.2 existen por esto.

## 4. Diseño

### 4.1 Dónde se cosecha

**Solo en S26.** Cuando el handler resuelve `d.tenencia == "equipada"`, se cosecha `badge.crop` con
la etiqueta del latch, reusando `learn_s17_detail`.

**S30 no cosecha, y es deliberado.** Ahí no hay botón que confirme nada: el dueño sale del propio
badge. Cosechar con la etiqueta que produjo el mismo matcher lo realimenta con sus propios aciertos
y errores — es exactamente el efecto "imán" documentado en la cosecha de julio, donde una única ref
recién incorporada atraía matches ajenos. S30 sigue siendo **consumidor puro**.

### 4.2 Los tres candados

1. **Conflicto de señales.** Si el badge nombró a un PJ distinto del latch con confianza, **no se
   cosecha**. Es la regla ya vigente en discos (`anchor_badge_conflict`): ante desacuerdo se le cree
   al badge —que en QA fue 0-wrong— y no se aprende nada. Cosechar ahí metería la cara de un PJ bajo
   el nombre de otro, que es la forma más cara de romper una librería.
2. **Anti-homogeneización.** Como máximo **una ref por par (PJ, arma) por sesión**, y solo si ese PJ
   está **por debajo del techo** de `_MAX_REFS_PER_NAME`. Un PJ con 1 ref puede absorber 9; uno con
   10 no se toca, así la cosecha nunca desaloja diversidad ganada en los discos. El arma se
   identifica con la clave que el handler ya calcula para la votación del dueño
   (`nombre`, `nivel`, `refinamiento`, `atk_base`).
   **Por sesión**, sin archivo de estado: el registro vive en memoria y se pierde al cerrar la app.
   Es más simple y se auto-corrige — si una sesión cosechó un recorte pobre, la siguiente puede
   mejorarlo.
3. **Gate de persistencia.** Ninguno nuevo. `BadgeSurface.learn` ya respeta readonly +
   `DANIBOD_BADGE_HARVEST`, así que la cosecha solo persiste cuando corresponde.

### 4.3 Instrumentación (`DANIBOD_ID_DIAG`)

En **S26 y S30**, por cada badge de arma evaluado, una línea con:

- si Hough localizó el círculo (o `NOLOC`);
- el **top-1 con su confianza y margen aunque no alcance el guard** — este es el dato clave: hoy una
  abstención no deja rastro de a quién estuvo cerca;
- el PJ del latch;
- el desenlace: `nombrado` · `abstuvo` · `osciló` · `cosechado` · `veto_conflicto` · `veto_techo`.

Sin esto no podemos responder *cuáles* PJs falla — la pregunta que el QA del 07/08 dejó abierta, y
sin la cual dentro de una semana volvemos a discutir de memoria en vez de con datos.

## 5. Lo que este trabajo NO hace

- No toca la DB ni `inventory_weapons`. La reconciliación del inventario está atada al censo.
- No lee los **tiles** de la grilla de S30 (sigue pendiente, es otro tramo).
- No toca la ruta de discos, que está calibrada y escribe la DB.
- No modifica guards ni umbrales del matcher. Si el naming no sube, el problema no era la
  profundidad y hay que medir de nuevo — no aflojar el guard.

## 6. Tests

Sobre los fixtures existentes (40 de S26, 6 de S30):

| caso | esperado |
|---|---|
| `tenencia == equipada` | cosecha, una vez |
| `otro_pj` / `libre` / `incierto` | **no** cosecha |
| badge nombra distinto del latch | **no** cosecha (veto por conflicto) |
| misma arma vista dos veces | cosecha solo la primera |
| PJ ya en el techo de refs | **no** cosecha |
| readonly sin `DANIBOD_BADGE_HARVEST` | no persiste |
| `ID_DIAG` apagado | ninguna línea de diagnóstico |

Los tests aíslan la librería vía `DANIBOD_AVATAR_LIB` (lo que ya hace `conftest.py`), así que ninguno
toca la librería real del usuario.

## 7. QA en vivo y criterio de éxito

Una sola pasada:

```
tools\qa_launch.ps1 -ReadOnly -BadgeHarvest -IdDiag -FromSource
```

`-FromSource` no es opcional: el `.exe` es del 2026-06-20 y no tiene nada de esto.

Recorrido: armas equipadas en S26 (entrando desde el menú de personajes, que siembra el latch con el
nombre leído en pantalla) y después el inventario general S30.

**Éxito:**

1. El total de refs de `detail` sube respecto de las 184 de partida.
2. Los PJs que ganaron refs son los flacos, no los que ya estaban ricos.
3. El naming del dueño en S30 sube del 3/7 de partida.
4. Ningún PJ pierde refs (verificación directa del candado anti-homogeneización).

Medición antes y después con el conteo por PJ del `.npz`, más el leave-one-out de
`tools/measure_badge_lib.py`.

## 8. Riesgos

- **La cosecha depende de que mires armas equipadas.** Un PJ cuyas armas nunca mires no gana refs.
  Esto no lo resuelve el diseño: lo hace barato, no automático.
- **El latch puede estar equivocado** si entraste a la pantalla sin pasar por el menú. El candado de
  conflicto ataja el caso en que el badge sabe algo distinto, pero no el caso en que el badge también
  se abstiene. Es el mismo riesgo que ya corre la cosecha de discos.
- **Ocho PJs flacos son pocos recortes.** Si tras el QA el naming sigue bajo, la conclusión honesta es
  que la profundidad no era la única causa, y toca medir con los datos del `ID_DIAG` antes de tocar
  nada más.

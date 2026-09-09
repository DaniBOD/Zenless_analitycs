# Los tres verbos: que la DB siga al juego sola

**2026-09-06.** Cierra el ciclo de vida del disco LIBRE. El principio lo dictó Daniel:

> *La gracia es que el usuario no tenga que tocar la DB, sino que crezca y se modifique en base a
> lo que hace en el juego: disco farmeado = INSERT, disco mejorado = UPDATE, disco desmontado =
> update en blanco y queda libre.*

## Lo que faltaba, y por qué se notaba tan poco

Un disco **EQUIPADO** ya tenía su ciclo resuelto desde siempre: `persist_s17_disc` lo escribe por
la clave natural `(PJ, slot)`, que sobrevive a cualquier cambio del disco — incluida una mejora.

El disco **LIBRE** no tiene esa clave. Y ahí faltaban los tres verbos enteros. Medido en la
sesión de farmeo del 2026-09-05: **6 corridas, 10 drops parseados enteros, 0 escrituras**.

La DB coincidía con la realidad sólo porque se había re-censado desde cero. Con ~5 corridas
diarias se aleja sola, y hasta ahora únicamente un censo completo la corregía.

---

## Verbo 1 · INSERT — el drop entra

`_emit_s3_disc` afirma `equip_libre = True` (un drop es libre por regla del juego, no por un badge
leído) y el controller rutea `S3` a la persistencia **sin perder el toast** — la rama vieja hacía
`return` antes de `_build_payload`, así que guardar el disco habría apagado justo lo que el
usuario mira mientras farmea.

### Un drop es un EVENTO, no una observación de estado

`_persist_disco_libre` se **abstiene** cuando la identidad de un disco libre choca con la de uno
equipado, y hace bien: mirando el inventario no se distingue *"el mismo disco recién
desequipado"* de *"su gemelo"* (hay 22 pares indistinguibles en el inventario real).

**Para un drop esa duda no existe.** Acaba de entrar un disco a la cuenta: coincida su identidad
con lo que sea, hay uno más. Por eso `es_drop=True` saltea el dedup e inserta siempre — y por lo
mismo tampoco actualiza una fila libre idéntica: farmear el gemelo de algo que ya tenías da DOS
discos, no uno actualizado.

### Alcance honesto

S3 parsea el disco **cuyo detalle abrís**. En la sesión medida: 17 anunciados por `Farmeo
detectado`, 10 con ficha completa. Los que no se abren no tienen main ni substats, así que no hay
fila posible. Es *"cada disco farmeado **que abras**"*.

**Validado en vivo (2026-09-06):** 6 drops abiertos → 6 filas (ids 389-394) con trigger
`s3_drop_insert`, 384 → 390, todas sin dueño / `equipado=0` / nivel 0 / substats completos, y los
toasts salieron.

---

## Verbo 3 · Baja — el desmontaje libera la fila

Sin esto, el verbo 1 hace crecer la DB sin techo. Se implementó **antes** que el verbo 2 por eso.

### `descartado`, un soft delete que estaba escrito y dormido

El esquema ya tenía `descartado INTEGER DEFAULT 0 CHECK(descartado IN (0,1))`, un índice parcial
(`idx_inv_pending`) y **cinco consultas que ya lo filtraban**. Nadie lo escribía nunca en 1.

Es la forma correcta de *"queda en blanco y libre"*: la fila deja de existir para todo el sistema
sin romper la FK de `inventory_disc_evaluations` ni reciclar ids. Junto con `descartado=1` se
limpian `agente_asignado` y `equipado`, para que un disco destruido no siga ocupando el slot de
nadie ni contando en la composición de set del PJ.

### ⚠️ El riesgo acá es el INVERSO al de insertar

Un insert de más se corrige en el próximo censo. Una baja equivocada **le borra al usuario un
disco que sí tiene**. Por eso el matcher exige **identidad ∧ VALORES**, que es lo que el propio
`teardown_batch._record` había dejado pedido por escrito:

> *"el matcher futuro debe usar identidad ∧ valores y, ante ≥2 candidatos, reportar ambigüedad en
> vez de dar de baja la fila equivocada"*

La razón concreta: **en Nivel 0 todos los rolls valen 0**, y casi todo lo que se desmonta es Nivel
0. Ahí la firma de identidad colapsa a `(set, slot, main, nombres de substat)` y dos discos
distintos del mismo set la comparten. Lo único que los separa son los valores.

**Validado en vivo (2026-09-06):** los mismos 6 discos desmontados → `6 dados de baja · 0
ambiguos · 0 no estaban en la DB`, conteo activo de vuelta a 384 exacto, 0 descartados fuera del
rango 389-394, `integrity ok`.

### Dos cosas del log en vivo que valen más que el resultado

**Una lectura falló entera y la recuperó el usuario sin saberlo.**

```
15:01:18  +1 → 5/300 · Rosa espinosa (6) 5 (6) Nv0 · ? None ·      ← sin main, CERO substats
15:01:30  −1 → 4/300 · destildado
15:01:32  +1 → 5/300 · Rosa espinosa (6) Nv0 · DEF% 12.0% · HP 112 / Perf 9 / ATK 19 / DEF 15
```

Ese `? None` es un disco sin ninguna identidad. Si quedaba tildado, la tanda cerraba con *"5 con
datos, 1 sin"* y ese disco seguía vivo en la DB para siempre. Se salvó porque el usuario destildó
y volvió a tildar — **la app no avisó nada**: el contador del juego decía 5/300 igual, con datos o
sin ellos. Deuda anotada para los toasts: *"1 disco desmontado no se pudo leer"* es exactamente lo
que un toast debería interrumpir a decir.

**El slot se leyó mal dos veces y no importó.** `Rosa espinosa (6) 5 (6)` es un glitch del parseo,
y el 394 entró con `Recarga de Energía None` (sin valor de main). El matcher lo dio de baja bien
igual, porque la identidad **no depende del valor del main**: se apoya en set + slot + nombre del
main + nombres de substat, y desempata por los valores de los substats, que sí salieron completos.
La guarda funcionando en el sentido correcto — tolerante donde el dato falta (`_cerca` acepta un
`None` de cualquier lado), estricta donde el dato distingue.

---

## Verbo 2 · UPDATE — la mejora sigue al disco libre

El más chico de los tres, y el que menos duele si tarda: un disco mejorado se corrige solo cuando
lo equipás.

**La fuga:** subir de nivel **cambia la identidad**. Un drop a Nv0 tiene 3 substats; a +3 se
desbloquea el cuarto y los rolls se mueven. La identidad de dedup incluye nivel, substats y rolls,
así que el mismo disco físico ya no matchea su propia fila ⇒ la próxima captura INSERTA una
segunda. La fila vieja queda de fantasma para siempre.

### El match va contra el PRE, y exige valores

`UpgradeSyncer.on_s10_enter` ya guardaba el snapshot **PRE** con el `DiscParsed` completo. Ese PRE
es lo que está escrito en la fila, así que es la clave de búsqueda correcta.

Se exige **identidad ∧ VALORES** por la misma razón que en la baja, y acá pega todavía más fuerte:
lo que se mejora **viene de Nivel 0**. Farmeando el mismo nodo se juntan pilas de discos que
comparten la firma colapsada, y actualizar al gemelo equivocado le pisa los datos a un disco real.
Para eso se extrajo `row_matches_parsed_values`, complemento de `row_matches_parsed_identity`.

### Reparto de los candidatos

| candidatos | qué pasa | por qué |
|---|---|---|
| exactamente 1 libre | `update_from_parsed` · `s10_upgrade_update` | el caso |
| ≥2 libres | se abstiene y avisa con los ids | elegir sería acertar la mitad |
| 0 libres, ≥1 ocupado | no toca nada | está equipado: lo resuelve la S17 por `(PJ, slot)` |
| 0 candidatos | no toca nada | nunca se capturó; entra en la próxima pasada |

Las filas marcadas `dueno_no_identificado` **no cuentan como libres**: la marca AFIRMA que alguien
lo tiene y no se pudo leer quién.

### Sólo se escribe en el camino CONFIRMADO

`_persistir_mejora` se llama **únicamente** desde `on_post_upgrade_disc` — la pantalla posterior
(S17 o S5) con los rolls asentados. Los dos fallbacks de `_flush_pending` **no** persisten a
propósito:

- el **proyectado** resume con el nivel de la pill del preview, sin haber visto los rolls;
- el **visto en S10** vio el level-up pero nadie confirmó que fuera el estado final.

Escribir un POST sin confirmar dejaría la fila con una identidad que tampoco coincide con la
realidad: la próxima captura insertaría el duplicado **igual**, más los datos pisados. Abstenerse
deja el estado de antes, que el censo detecta.

### ⭐ Un bug latente que el verbo 2 volvía seguro: el valor del main

Escribiendo esto apareció algo que no era del verbo 2 pero que el verbo 2 garantizaba activar.
**`update_from_parsed` no escribía `main_valor`** — y ningún otro camino lo escribía tampoco: se
ponía sólo en el `INSERT`.

El problema es que **el valor del main sube con el nivel**. Medido sobre el inventario real, es
función determinista de `(slot, main, nivel)` y siempre exacta:

```
slot 2 · ATK    Nv0: 79 (n=5)   Nv12: 268 (n=1)   Nv15: 316 (n=60)
slot 1 · HP     Nv0: 550        Nv3: 880          Nv12: 1870   Nv15: 2200 (n=59)
slot 5 · ATK%   Nv0: 7.5        Nv3: 12           Nv15: 30 (n=19)
```

Los 60 discos a Nv15 valen 316 los 60. Así que una fila migrada a Nv15 conservando el 79 queda
**internamente contradictoria**, y el scoring la puntúa con un ataque cuatro veces menor al real.

No había mordido nunca porque el censo capturó cada disco al nivel que tenía entonces — la DB hoy
está consistente, verificado. Pero el verbo 2 existe *justamente* para filas que cambian de nivel:
sin este arreglo, su primera corrida habría dejado una fila peor que el duplicado que viene a
evitar (el duplicado, al menos, tenía el main correcto en la fila nueva).

El valor se pisa **sólo si el parseado trae uno**: un `None` es falta de lectura, no un dato
(RNF-02), y sobrescribir con él borraría lo que ya estaba bien. No es hipotético — el modal de
mejora devolvió `main_valor=None` en vivo ese mismo día.

Es la forma de **A2** otra vez: el silencio no era un aprobado. Ese `UPDATE` venía corriendo desde
siempre por `s17_update` y `libre_update`, y nunca se notó porque no se lo ejercía con un cambio
de nivel.

### Validado en vivo (2026-09-06): 3 de 4, y el cuarto se abstuvo bien

```
id=377  Blues Libre     slot 2  Nv0→3   main  79 → 126    + Prob. Crítica 2.4  (4º substat)
id=379  Metal polar     slot 4  Nv0→6   main   6 → 13.2   + DEF% 9.6 (r1)
id=374  Armonía umbría  slot 5  Nv0→3   main 7.5 → 12     + DEF 15
```

**Cero duplicados.** Las activas pasaron de 384 a 385 y ese +1 es `id=395`, una Rosa espinosa
slot 2 con substats distintos a las seis desmontadas — un disco real que la DB nunca había visto.
Sin el verbo 2 esas tres mejoras habrían dejado **seis** filas donde hay tres. El arreglo del main
quedó probado en campo y la invariante sigue intacta: 0 combinaciones `(slot, main, nivel)` con más
de un valor.

#### El cuarto: `id=370` (Floración del alba, Bono Daño Éter)

```
[mejora] Floración del alba slot 5 · nivel 0 → proyectado 3 · main Bonode dajoetéreo 7.5% +4.5% ?
Mejora: set=Floración del alba slot=5 nivel=0 no estaba en la DB — entrará en la próxima captura.
```

Ese `?` final es el **valor del main en `None`**: el número quedó pegado adentro del nombre
(`'Bonode dajoetéreo 7.5% +4.5%'`), y con el nombre así el match por identidad no encuentra la
fila. El vocabulario **sí** rescata `Bonode dajoetéreo` → `Bono Daño Éter`; lo que rompe es tener
los valores dentro del nombre.

**⚠️ Una hipótesis mía, desmentida por la medición.** Pensé que entrar al modal con los materiales
ya cargados ensuciaba esa línea — era el único de los cuatro que entró así. Parseé los **8 fixtures
de S10**, los 6 de `19_Upgrade_PRE_materiales_cargados` incluidos: los 8 dan nombre, valor, unidad
y canónico limpios. Lo que queda en pie es la combinación *etiqueta larga + materiales
precargados*, que ningún fixture cubre, y con **n=1** no alcanza para afirmarla. Hace falta una
captura de esa pantalla para cerrarlo.

Lo que sí queda firme: **la abstención es el modo de falla correcto** (dejó la fila vieja en vez de
pisar otra). Consecuencia concreta anotada: `id=370` quedó desactualizada (Nv0 en la DB, Nv3 en el
juego) y la próxima captura como libre va a insertar un duplicado.

### Un contrato que cambia a propósito

`UpgradeSyncer` estaba declarado **display-only** desde 2026-07-10. Dejó de serlo. Sigue **sin DB
propia**: le pide al `DiscSyncer` que escriba (B1 — una sola autoridad por pregunta). El parámetro
`disc_syncer` es opcional y sin él el comportamiento es exactamente el de antes.

---

## Verificación

| | |
|---|---|
| tests nuevos | 17 (`test_update_por_mejora.py`) + 7 (`test_sync_upgrade.py`) + 1 (wiring) |
| sabotajes (A3) | 7, cada uno cayó en el test correcto |
| lint | 0 findings nuevos en los archivos tocados (conteo antes/después idéntico) |

Los cinco sabotajes y el test que cada uno rompió:

```
sin comparación de VALORES        → test_en_nivel_0_los_valores_deciden_cual_de_los_gemelos...
len(libres) > 1  →  > 2           → test_ante_dos_libres_indistinguibles_no_actualiza_ninguno
el ocupado/marcado cuenta libre   → test_el_disco_equipado_lo_resuelve_la_s17 (+ el de la marca)
_flush_pending también persiste   → test_el_fallback_visto_en_s10_tampoco_persiste
el controller no cablea el syncer → test_el_upgrade_syncer_recibe_el_disc_syncer
el UPDATE no escribe el main      → test_la_mejora_actualiza_el_valor_del_main
el UPDATE pisa el main con None   → test_un_main_sin_leer_no_pisa_el_valor_que_ya_estaba
```

El último existe por la práctica **A2**: el cable entre `UpgradeSyncer` y `DiscSyncer` es UNA
línea de `start()`. Sin ese test, sacarla dejaba todo lo demás en verde mientras el verbo 2 no
corría nunca en la app real.

## Queda abierto

- **La línea del main en S10 con etiqueta larga**: `id=370` no se actualizó porque el valor quedó
  dentro del nombre. Falta la captura de esa pantalla para separar las dos causas candidatas.
- **Un par de filas idénticas anterior a este trabajo**: `id=93` (libre, censo del 31/08) e
  `id=385` (equipado por Ju Fufu, 05/09), Monarca del Pináculo slot 3 DEF Nv15. Sale de la regla
  deliberada de que S17 no adopta filas LIBRES. Sólo la pantalla dice si son uno o dos discos:
  material para el segundo censo.
- El aviso de disco desmontado sin datos (arriba), para el tramo de toasts.
- El segundo censo de discos es el juez final: si los tres verbos andan, tiene que encontrar la DB
  ya alineada en vez de tener que corregirla.

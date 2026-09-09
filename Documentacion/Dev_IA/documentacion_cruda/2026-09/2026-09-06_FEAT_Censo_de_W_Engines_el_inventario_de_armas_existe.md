# Censo de W-Engines: que el inventario de armas exista

**2026-09-06.** Segundo tramo de la hoja de ruta del uso diario, después de los tres verbos de
discos. Hasta hoy `inventory_weapons` tenía **0 filas** y *nadie la escribía nunca*:
`app/db/repositories.py` no contenía una sola referencia a armas.

## Lo que estaba y lo que faltaba

**El lado de la captura estaba listo, y lo medí antes de creerlo.** `parse_weapon_s30` contra las
10 capturas reales de `Engines_Triggers/Inventario_general_engines`: **60/60 campos, 100%**,
incluidos los dos casos que el propio catálogo documenta como filosos ("Repercusión - Modelo II",
donde el OCR lee `lll` y el candidato equivocado gana por 0.02; "Última cena", que sale
`Uitimacena`).

Faltaba **toda la escritura**: repo, syncer y censo.

## Tres mediciones antes de diseñar

| | |
|---|---|
| `Amplificadores [57/2000]` | el inventario **tiene contador**, igual que el de discos ⇒ el censo puede saber cuándo terminó |
| 8 de las 10 capturas del inventario tienen **dueño nombrado** | la grilla muestra las armas EQUIPADAS ⇒ el contador las incluye y el ancla es válida |
| 42 armas faltan en `weapons`, **37 son armas que Daniel no posee** | como mucho **5 de sus 57** son impersistibles por la FK |

La segunda era un gate: si el contador excluyera las equipadas, `registrados` nunca podría
converger al total y la cobertura sería un número sin sentido. **No lo resolví mirando la captura**
—que era la tentación— sino contra `test_s30_dueno_verdad_de_tierra.py`, donde Daniel ya había
dictado la verdad de tierra de esas mismas diez.

---

## La regla de v1: se escribe lo que se NOMBRA, nunca lo que se declara libre

Sale de una medición, no de una intuición. `test_s30_dueno_verdad_de_tierra.py` da **8/10**, y el
desglose es lo que manda:

- los **6 que nombra salen los 6 bien**;
- 1 se abstiene con el ranking correcto;
- **1 AFIRMA que un arma está libre y es de Grace.**

Nombrar es fiable; negar dueño, no — la misma asimetría que ya dejó escrita la práctica *"reportar
y aprender piden evidencia distinta"*. Escribir `agente_asignado = NULL` desde esa lectura sería el
"falso LIBRE" que en discos habilitó reemplazos erróneos.

Y la guarda que en discos cubre ese caso —un libre que choca con una fila EQUIPADA se abstiene—
**no sirve al principio de una pasada de censo**: todavía no hay filas contra las cuales chocar.
Por eso acá la abstención es previa, no reactiva.

| observación en S30 | qué pasa |
|---|---|
| dueño **nombrado** y resuelto contra el roster | INSERT/UPDATE fila equipada · `origen_evidencia='s30_badge'` |
| S30 dice **LIBRE** | se registra en el censo, **no se escribe** |
| dueño presente pero sin identificar | se registra, no se escribe |
| fuera de catálogo | se registra, no se escribe, **y se reporta con el nombre crudo** |

---

## Los siete pasos

### 1 · Migración `_26`: la tabla, antes de su primera fila

Con 0 filas el rebuild es gratis; con filas cuesta un rebuild con un índice parcial en el medio, y
SQLite no sabe sacar un `DEFAULT` con `ALTER`.

- **sin DEFAULT** en `nivel` ni `refinamiento`;
- **`descartado`** (las armas salen de la cuenta: los duplicados se consumen como material de
  refinamiento — que es *la razón* por la que hay copias);
- **`origen_evidencia`**, que registra si la fila se apoya en el camino certero (el botón
  'Desequipar', que el juego afirma sin la librería de badges) o en el frágil;
- y la clave natural convertida en **restricción**:

```sql
CREATE UNIQUE INDEX idx_invw_pj_equipada ON inventory_weapons(agente_asignado)
 WHERE equipado = 1 AND agente_asignado IS NOT NULL AND descartado = 0;
```

*"Un PJ equipa exactamente un W-Engine"* era una premisa; ahora un error del badge se vuelve un
`IntegrityError` en el momento de escribir. En discos, el caso análogo (dos filas reclamando el
mismo slot) pasó dos días sin verse y apareció consultando a mano.

#### ⚠️ Una de mis razones era falsa, y la destapó un sabotaje que pasó en verde

Escribí que el CHECK viejo **impedía guardar** un `refinamiento` NULL. **No es cierto:** en SQL un
CHECK que evalúa a NULL se considera *satisfecho* — sólo rechaza cuando da FALSE. Medido:

```
INSERT ... (weapon_id, refinamiento, nivel) VALUES (1, NULL, NULL)  -> pasa
INSERT ... (weapon_id) VALUES (2)                                   -> nivel=0, refinamiento=1
```

Lo que inventa es el **DEFAULT**, y sólo cuando la columna se **omite**. El riesgo era más chico
del que dije, pero real. Y mis dos primeros tests pasaban las columnas **explícitas**, así que no
tocaban el DEFAULT: restaurarlo los dejaba verdes a los dos. Hizo falta un tercero que inserta
omitiendo. **A3 otra vez: verificar el efecto, no la intención.**

#### El choque B1: `agents.weapon_id`

Existen `agents.weapon_id` / `weapon_nivel` / `weapon_rango`, están **0 de 51** con dato y no las
lee nadie — pero estaban en `AGENTS_NULL` de `rebuild_account_db.py`, cuya docstring promete *"esto
lo sabe re-leer el pipeline de pantalla"*. Con `inventory_weapons` como autoridad, eso es falso.

No se dropearon (criterio conservador). Se movieron a `AGENTS_MUERTAS_ARMA`, que **se suma
explícitamente al vaciado** — moverlas sin eso las habría convertido en silencio en columnas que
sobreviven a un reconstruir.

### 2-3 · Repos y `WeaponSyncer`

Cuatro buckets, y los tres primeros se abstienen:

| | condición | acción |
|---|---|---|
| A | el PJ ya tiene ESA arma | `update_estado` · `s30_update` |
| B | el PJ figura con OTRA arma | **abstiene y avisa** — un PJ lleva un arma sola, así que una de las dos lecturas está mal y no se sabe cuál |
| C | el arma figura equipada por OTRO PJ | **abstiene y avisa** — mover sobre la lectura equivocada le SACA el arma a quien sí la tiene |
| D | nada matchea | `insert` · `s30_insert` |

**Sin fuzzy en el repo, a propósito.** El parser ya canoniza con `match_catalogo` (difflib 0.84 +
el colapso de tokens i/l/1). Re-resolver en el repo sería una segunda autoridad, y peor (B1).

**`AgentRepo.get_by_nombre` arrastraba el esquema de scoring de discos.** Para armar el `Agent`
completo, `_load()` lee `disc_archetypes`, `agent_score_thresholds` y `agent_substat_preferences`
— la vista de *scoring*. Resolver "qué id tiene el PJ que se llama X" no tiene por qué acoplarse a
eso: lo destapó un test que reventó con `no such table: disc_archetypes`. Se agregó
`get_id_by_nombre`, en el mismo repo (la autoridad sigue siendo una; lo que cambia es el costo).

### 4 · El contador, compartido

`parse_s9_header_counter` tenía la ROI y la capacidad **3000** cocidas en un regex de módulo. Se
extrajo a `app/core/parser_inventory_header.py` con la capacidad por parámetro; el nombre viejo
quedó como delegación de dos líneas y sus 26 tests siguen verdes.

**El rótulo NO es el ancla, la capacidad sí.** Parecía un problema —`detector.py` documenta que
Paddle nunca lee "Amplificadores" limpio— pero el rótulo no se usa: sin la capacidad, cualquier par
de números se leería como inventario (la batería del header dice `237/240`). Con ella, además,
`57/2000` leído con capacidad 3000 devuelve `None`: **una pantalla no puede hacerse pasar por la
otra**.

Medido antes de escribir nada: la ROI calibrada para discos contiene el header de armas y Paddle
lee `/2000` limpio **10 de 10**. Por eso no hay `str.translate` — el docstring de discos se negó
explícitamente a agregar uno para un fallo no observado, y esa regla se respeta.

### 5 · `DiscCensus` → `InventoryCensus`

No había nada específico de discos adentro: `identidad` es una tupla opaca a propósito, y
`libre`/`dueno`/`confirmada`/`faltan`/`excedente` aplican igual. Duplicarlo habría dejado dos
implementaciones de la misma aritmética de cobertura, condenadas a derivar en silencio (B1).

Rename + alias (`DiscCensus = InventoryCensus`), **sin parametrizar conducta**. Lo único que
depende de la entidad es un texto, y no por cosmética:

> En discos la brecha son **gemelos que la deduplicación colapsa**. En armas, **copias que la capa
> de OBSERVACIÓN no distingue**: dos copias del mismo W-Engine son idénticas en todo campo
> observable, y `weapon_panel_signature_s30` es un hash del panel — mover la selección de una a su
> gemela ni siquiera vuelve a disparar el parser.

Más `en_catalogo` / `fuera_de_catalogo`: una causa de brecha que discos no tiene. Meterla en
`faltan` haría el número ilegible; es una parte esperada y explicable de la diferencia.

### 6 · Cableado, y un bug que el cableado destapó

Transcripción del censo de discos: apertura perezosa al entrar a S30, contador con cadencia propia
(`_S9_CONTADOR_PERIODO_S` pasó a `_INV_CONTADOR_PERIODO_S` — una autoridad para "cada cuánto vale
releer un header"), censo **después** de persistir, y F8 cerrando discos → armas → roster.

La persistencia cuelga de un callback **propio** (`on_weapon_detected`), no de `on_weapon_seen`:
ese se emite en cada lectura que pasa el dedup del *log*, y colgarse de él ascendería una guarda de
logging a guarda de escritura.

#### ⭐ S30 nunca escribía el dueño de vuelta en el objeto parseado

S26 hace `d.tenencia, d.dueno = clasificar_tenencia(...)`. **S30 no.** Resolvía el dueño en una
variable local y lo usaba sólo para armar el string del log. Todo lo que consumiera el
`WeaponParsed` —la persistencia, el censo— lo veía en `None`.

O sea: el syncer se habría abstenido **siempre** y el censo no habría registrado **un solo dueño**,
con el log diciendo "la tiene Vivian" en la línea de al lado. Un fallo perfectamente mudo.

Lo destapó el cableado, no un razonamiento. Hay test propio
(`test_el_dueno_resuelto_llega_a_la_persistencia`) porque el primer sabotaje rompía 19 tests con
`AttributeError` —ruidoso pero no aislante— y hacía falta uno que señalara la causa.

`tenencia` **no** se copia, y no es olvido: la de S26 es un vocabulario de cuatro valores y la de
S30 es una cadena para mostrar. Pisar el campo haría que un consumidor comparara contra valores que
nunca van a coincidir — justo el que S30 no puede afirmar: `libre`.

### 7 · El reporte de cierre

El censo de discos no produce archivo. Acá sí, por una razón concreta: **la pasada descubre las
armas que el catálogo no tiene, con su nombre español leído de pantalla**, que es el dato que
ninguna wiki accesible publica. El reporte (`audit/censos/*_censo_armas.md`) es la entrada de la
migración curada que después las da de alta — **nada se da de alta solo**, porque auto-insertar con
lo que devuelva el OCR repetiría el pecado original del catálogo.

Incluye una sección **"Lo que esta corrida NO prueba"**, misma doctrina que el reporte del roster.

---

## Verificación

| | |
|---|---|
| tests nuevos | **73** en 6 archivos |
| sabotajes (A3) | **15**, cada uno cayó en el test correcto |
| lint | 0 findings nuevos en 8 de 9 archivos tocados; +2 en `controller.py`, y son repeticiones de patrones que el archivo ya usa (`BLE001`, `S110`) copiados del bloque hermano del `DiscSyncer` |
| RNF-01 | app cerrada verificada con `tasklist` **antes** de escribir; ensayo contra copia; backup `backup_premig_20260906_224003`; 7 smoke checks; `foreign_key_check` y `integrity_check` ok |

## Estado al cerrar la sesión del 2026-09-06

Todo lo de arriba está **commiteado y pusheado** (`737da77`), con la suite en verde
(2635 passed, 17 skipped, 1 xfailed, 42:58). La DB tiene el esquema nuevo y **cero filas**:

```
inventory_weapons : 0 filas · 2 índices (idx_invw_pj_equipada, idx_invw_weapon)
weapons           : 59 filas (catálogo, completo)
integrity ok · foreign_key_check sin violaciones
```

**La pasada en vivo no se corrió todavía.** Es lo primero que sigue.

### Cómo se corre

1. Lanzar la app con `powershell -ExecutionPolicy Bypass -File tools/qa_launch.ps1 -FromSource`
   (la lanza Claude, no Daniel: si la lanza Daniel, la virtualización del contenedor MSIX hace
   que la shell lea una copia congelada del log y no se vea nada).
2. Abrir el **inventario de amplificadores** — la pantalla del header `Amplificadores [57/2000]`.
3. Recorrer los tiles **uno por uno**. Lo que se lee es el panel derecho, así que cada tile hay
   que seleccionarlo; no alcanza con que esté a la vista.
4. Cerrar con **F8**.

### Qué tiene que aparecer en el log

```
[censo-armas] pasada abierta
Arma persistida id=1 s30_insert Engranaje infernal · Dialyn · Nv60 · P2
[censo-armas] 1/57
...
[censo-armas] pasada cerrada — N/57 registradas · N con dueño · N sin resolver · N fuera de catálogo
[censo-armas] → ...\audit\censos\<TS>_censo_armas.md
```

### Los números que deciden el tramo siguiente

| número | qué significa | qué desbloquea |
|---|---|---|
| **con dueño** | las que se persistieron | si es la mayoría, la pasada por las 51 fichas de PJ no hace falta |
| **sin resolver** | el badge no las nombró | si son muchas, la segunda pasada por S26 sí vale |
| **fuera de catálogo** | se esperan ~5 | el reporte las lista con su nombre español de pantalla; con eso se arma la migración curada que las da de alta |

### Dos cosas a mirar de cerca

- **Un `Conflicto:`** (WARNING) es el índice único haciendo su trabajo: *"X ya figura con
  weapon_id=N"* significa que dos tiles nombraron al mismo PJ, y como un PJ lleva un arma sola,
  una de las dos lecturas está mal sin forma de saber cuál. **No se escribe ninguna** y quedan los
  ids en el log — abstención por diseño, no un fallo.
- **Una `Copia:`** (INFO) es otra cosa y no es un problema: el arma ya figuraba en otro PJ y se
  inserta igual como fila nueva. Ver la corrección del 2026-09-08 más abajo.
- **El excedente sobre el contador.** Si las identidades registradas superan las que declara el
  header, sale un WARNING. Significa que una copia se contó dos veces, y el contador manda.

## La pasada en vivo del 2026-09-08, y la premisa que refutó

Dos cosas que sólo se veían corriendo.

### El contador dice 185, no 57

`[censo-armas] N/185`. El 57 salía de una captura vieja de `Amplificadores [57/2000]`. No cambia
nada del diseño —el contador se lee de pantalla justamente para no depender de un número
heredado (A1)— pero sí la escala de la pasada.

### Bucket C era más estricto que el invariante

El log mostró `Última cena` equipada por **Gatillo, Koleda y Lycaon**, y se escribió una sola: las
otras dos salieron por el bucket C con un WARNING que decía *"una de las dos lecturas del badge
está mal"*. **La premisa era falsa.** Los W-Engines son fungibles: dos copias son idénticas en todo
campo observable, y de una A de gacha estándar tener varias es lo normal, no un síntoma.

El invariante que hay que defender es *un PJ lleva un arma sola*, y de ese ya se ocupan el bucket B
y el índice único parcial. Pedir además que un arma tenga un solo dueño no lo protegía de nada —
y era **incoherente**: ante el mismo badge mal leído, si el arma no estaba ya en otro PJ el bucket D
insertaba igual. La guarda tapaba un subconjunto arbitrario de los errores que decía cubrir, al
precio de perder todas las copias legítimas.

Ahora C **inserta como fila nueva** y avisa en INFO (`Copia:`), nombrando las filas hermanas porque
son la única pista de que el badge *podría* haberse equivocado. Lo que no cambia: la fila ajena no
se toca. Mover sobre una lectura equivocada le saca el arma a un PJ que sí la tiene —destructivo e
invisible—; insertar de más se corrige en el próximo censo. Es la misma asimetría de
`dar_de_baja_desmontados`.

Dos tests fijan las dos mitades, y el segundo existe **porque el primero solo no alcanza**: que se
inserte la copia no dice nada sobre si la fila vieja sobrevivió intacta.

| test | qué fija |
|---|---|
| `test_una_segunda_copia_del_mismo_engine_entra_como_fila_nueva` | se escribe, y con trigger `s30_insert_copia` para poder contarlas aparte |
| `test_una_segunda_copia_no_le_saca_el_arma_al_primer_pj` | la fila que ya estaba queda idéntica, nivel y refinamiento incluidos |

**El gemelo libre sigue siendo invisible, y es correcto.** Daniel reportó que su segunda
`Última cena` LIBRE no dispara. El gate `weapon_panel_signature_s30` hashea dos bandas que viven
enteras en el panel derecho (`x ≥ 0.72`): la grilla no entra a propósito, porque el rectángulo que
la incluía se comía el arte animada y el gate no cortaba nunca. El matiz que importa: el badge del
dueño **sí** cae en la banda B, así que copias con dueños distintos re-disparan (por eso salieron
las tres de arriba). Lo invisible es el par idéntico *incluyendo la tenencia*. Como las libres no se
escriben en v1, el costo es sólo de conteo y se reporta como brecha.

## Queda abierto

> Estado al 2026-09-08, después de la primera pasada. Los números y el detalle completo están en
> [`audit/censo_armas_20260908.md`](../../../../audit/censo_armas_20260908.md): **28 filas escritas**,
> 53/185 identidades, sólo rangos S y A.

- ~~Segunda pasada por los 4 engines duplicados~~ **HECHA el 2026-09-08**: las 9 filas entraron,
  `inventory_weapons` quedó en **37**. Cerrada con F8, reporte en `audit/censos/`.
- **Los tiles de rango B**, sin recorrer.
- **La migración curada del catálogo** — **6** armas, no 7: `Cúter` (de Pulchra) y `Última cena`
  estaban en el catálogo y salieron listadas como huecos porque el nombre traía un glifo suelto a
  la izquierda. Corregido en `match_catalogo`; el resto sigue con su nombre español de pantalla
  en el audit. Ninguna se da de alta sola.
- **El resumen del censo vive sólo detrás de F8.** Parar el monitor o cerrar la app lo descarta en
  silencio: ni reporte, ni desglose, ni un aviso de que se perdió. El audit del 2026-09-08 existe
  porque se pudo reconstruir del log, y eso no siempre va a estar.
- **La app se lee a sí misma.** Una lectura de la pasada fue el panel de la propia app
  (`X Monitor: OFF granajeinfernal 385 305 0/385`), con sus contadores de discos adentro. La
  rechazó el catálogo por casualidad; nada en el pipeline lo impide.
- **Refs de Zhao** para la superficie `detail`: su `Transmorfer original` sale
  `con dueño (sin identificar)`. Es la clase floja conocida, y **no** es el mismo bug que el falso
  LIBRE de abajo — presencia sí, nombre no.
- **Escribir las armas LIBRES.** Se desbloquea con: la pasada por fichas de PJ (S26 asserta libre
  con *pinza* — badge ausente **y** botón 'equipar'/'reemplazar', dos señales independientes), o
  arreglar la detección del círculo del dueño en S30 (`test_compilador_quimerico_no_esta_libre`
  queda como `xfail(strict=True)`: si alguien la arregla, el test falla **por pasar**, y eso es lo
  que dispara revisar esta decisión).
- **S29 como pendiente de swap.** Es la fuente más certera de PJ+arma —el juego lo escribe en
  texto, sin librería de badges— y su propio docstring dice *"el día que el flujo de armas escriba
  la DB, esta es la fuente del origen"*. Antes hay que probar en vivo que el handler dispara: que
  el detector lo clasifique no es que el handler haya corrido (A2).
- **La baja por reciclaje.** El botón "Reciclar" está en la pantalla y es el verbo 3 de las armas.
  No hay estado de detector ni fixtures. La columna `descartado` ya está para que ese tramo no
  requiera rebuild.
- **Scoring de armas (RF-14).** `weapon_passives_structured` y `weapon_evaluations` siguen vacías.

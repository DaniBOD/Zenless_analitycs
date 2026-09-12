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

> ⚠️ **Superado el 2026-09-10 por decisión de Daniel**: quiere que el sistema reconozca las dos
> copias, y además la explicación de arriba estaba incompleta — el gate no era la única capa que
> se tragaba la segunda copia. Ver la sección siguiente.

## Copias libres idénticas: dónde moría la segunda (2026-09-10)

Daniel tiene cinco `Última cena`: tres equipadas y **dos libres, una al lado de la otra**. Aportó
dos capturas (`Inventario_general_engines/Ejemplo_11` y `_12`) con cada una seleccionada, y pidió
que el sistema detecte la primera y después la segunda.

### Tres capas, no una

El 09-08 atribuí todo al gate de la firma. La medición sobre sus dos capturas lo corrigió:

| capa | qué pasaba con la segunda copia |
|---|---|
| **gate de firma** | las firmas difieren **0.2** de media (0 píxeles con diferencia visible) contra **10.3** entre dos armas distintas. Es ruido: re-disparar o no era suerte |
| **dedup por contenido** | `log_sig` es idéntica para dos libres iguales → `return` **antes** de persistir y de censar. Este es el que mataba siempre. Su comentario decía *"contenido idéntico es literalmente la misma lectura"*: **la misma premisa falsa que el bucket C** |
| **identidad del censo** | para una libre es `(nombre, nivel, refinamiento)`, que el propio docstring admitía que *colapsa las copias siempre* |

El log de la sesión cuadraba exacto con esto: pasaron una lectura degradada y una limpia de la
misma copia (difieren en `P?`), y la otra copia rebotó en el dedup.

### El arreglo: la posición de la selección, en las tres capas

Lo único que cambia entre dos copias idénticas es **dónde está el recuadro de la grilla**. El
remedio ya existía para los gemelos de disco (S9, 2026-08-29), y se reusó sin tocarlo:

- `s9_selected_tile_pos` funciona tal cual sobre la pantalla de armas — la grilla de la mochila es
  la misma. Localiza la selección en **los 12 fixtures de S30**; entre las dos Última cena libres
  salta **180 px sobre un tile de ~175**.
- **Gate y dedup**: "otra copia" lo decide `_s9_pos_movio` (más de medio tile), la misma autoridad
  que ya lo decide para discos (B1).
- **Censo**: `_ordinal_de_copia` numera las copias idénticas por lugar. La primera conserva su
  identidad de siempre; sólo la segunda en adelante recibe el sufijo, así ninguna identidad
  existente cambió.

**Costo:** localizar la selección cuesta **~16 ms por frame** contra 0,6 ms de la firma del panel,
en cada ciclo de S30. Es el mismo precio que S9 ya paga por el mismo problema.

### Lo que no cambia, a propósito

- **Sin posición, no decide.** Si no hay tile localizable, se comporta como antes. RNF-02: no
  inventar una pieza que no se vio.
- **Las libres se reconocen y se cuentan, pero no se escriben.** La regla de v1 sigue: S30 afirma
  LIBRE falsos (el `Compilador quimérico` de Grace), y escribir un `agente_asignado = NULL` desde
  esa lectura es el falso LIBRE que en discos habilitó reemplazos erróneos.

### El límite que no tiene arreglo desde la pantalla

Si hacés scroll y volvés a una copia ya vista, aparece en otra posición y **cuenta como una más**.
Sale como *excedente* sobre el contador del header, que sigue siendo la autoridad del total. Las
copias de un W-Engine no tienen identidad observable: sólo lugar.

### Verificación

127 tests de armas en 6 archivos, antes y después. **10 tests nuevos**, uno de ellos con los
píxeles reales de las capturas 11 y 12, sin stubs. Seis sabotajes, cada uno rojo en su test:

| sabotaje | queda rojo |
|---|---|
| el gate ignora la posición | `dos_copias_libres_identicas_se_leen_las_dos`, `la_segunda_copia_llega_a_la_persistencia_y_al_censo` |
| el dedup se traga el contenido idéntico | los mismos dos |
| el ordinal del censo siempre en 0 | `la_segunda_copia_llega…`, `dos_copias_libres_cuentan_dos`, `volver_a_la_misma_copia_no_la_cuenta_otra_vez` |
| `None` fuerza relectura en el gate | `panel_quieto_no_reocrea`, `sin_posicion_no_decide` |
| `None` inventa una copia en el censo | `sin_posicion_las_copias_colapsan_como_antes` |
| cualquier temblor cuenta como moverse | `el_temblor_del_localizador_no_inventa_una_copia` |

**Dos de esos seis estuvieron mal la primera vez, y los destaparon los propios sabotajes:**

- `test_sin_posicion_no_decide` contaba **líneas de log**, y pasaba con el gate roto: el dedup
  tapaba la línea repetida mientras el OCR de ~500 ms corría en cada ciclo. Se endureció para que
  cuente **relecturas del panel**. El nombre prometía más de lo que verificaba.
- El primer sabotaje de "`None` inventa una copia" usaba `id(object()) % 997 + 1` como ordinal
  nuevo en cada llamada. CPython reutiliza la dirección del objeto recién liberado, así que las dos
  llamadas devolvieron **el mismo número**: el sabotaje nunca cambió el comportamiento, y el
  "ningún test lo atrapó" era un defecto del sabotaje, no del test. Rehecho con un contador.

### Validación en vivo (2026-09-10, 23:39)

| | |
|---|---|
| primera Última cena libre | `LIBRE` · censo **4/75** |
| segunda Última cena libre | `LIBRE` · censo **5/75** |
| frame de transición | no apareció |
| cierre con F8 | **5/75 · 3 con dueño · 2 sin resolver · 2 provisorias** — las dos libres, cada una por su lado |
| DB | sin cambios: 38 filas, Última cena con sus 3 equipadas; las libres no se escriben |

Reporte: `audit/censos/20260910_234255_760944_censo_armas.md`.

Lo que **no** se ejerció en vivo: volver a la primera copia. Lo esperado ahí no es silencio — sale
una tercera línea `LIBRE`, porque la selección se movió, pero el censo se queda en 5/75. Lo cubre
`test_volver_a_la_misma_copia_no_la_cuenta_otra_vez`.

### El primer reporte después del arreglo explicaba la brecha con la causa vieja

Ese mismo reporte decía que faltaban armas porque *"la firma del panel no las distingue"* y, en lo
que la pasada no prueba, que *"ni siquiera vuelve a disparar el parser al saltar de una a otra"* —
sobre una corrida donde las dos copias **sí** se contaron por separado. Eran textos fijos en
`census_inventario.py` que describían el comportamiento anterior, y el arreglo los dejó mintiendo.

Se reescribieron para decir lo que hoy es cierto: las copias se separan por la posición de la
selección, y lo que queda como límite es la copia vista sin posición localizable (cuenta como una)
y el scroll (cuenta de más). Un test nuevo, `test_el_reporte_no_dice_que_las_copias_son_invisibles`,
prohíbe las dos frases viejas y exige que el reporte diga qué separa a las copias; saboteando cada
texto por separado, queda rojo las dos veces.

**La forma que se repite:** un comportamiento cambia y la prosa que lo explicaba —en un reporte, un
docstring, un comentario— sigue diciendo lo anterior con toda seguridad. Al cambiar un
comportamiento, hay que buscar las frases que lo describen, no sólo el código que lo implementa.

## Estado al cerrar la sesión del 2026-09-10

**Números:** `inventory_weapons` **38** (todas equipadas, `origen_evidencia='s30_badge'`) ·
`weapons` **61**. Commits `79b7fbf` (copias idénticas), `4721153` (reporte), `a2189a4` (catálogo).
La app quedó **cerrada** (se cerró para aplicar la migración).

### El catálogo: de los 6 "huecos", sólo 2 eran reales (migración `_27`)

Antes de insertar se buscó cada uno en las 59 filas. `Anhelo marcato`, `Viaje estruendoso`,
`Cilindro neumático` y `Templo a la granizada` **ya estaban**: el OCR les pegó texto del arte del
arma (*DESIRE*, *CRASH*) o les comió espacios, y el fuzzy los dejó en 0.76-0.82 contra el corte de
0.84. Darlos de alta habría duplicado el catálogo. Entraron sólo `Inocencia sacrificada` (Anby, 6
lecturas a Nv 60) y `Tetera esmeraldina` (Qingyi, 1 lectura a Nv **50** ⇒ ATK y valor del stat en
NULL). Detalle: `audit/weapons_catalog_20260910.md`.

### Decisiones de Daniel que no están en ningún otro lado

- **Rango B: fuera de alcance por ahora** — los A son asequibles. El `185` del header es el total
  con los B; el `56` y el `75` eran vistas filtradas por rareza. Pregunta cerrada.
- **Guardar las libres:** sin decisión ⇒ siguen sin escribirse (regla de v1).
- **Claret:** se incorpora cuando salga del gacha (`audit/patch_notes_v3.2.md` tiene el riesgo del
  parser de S18 con la especialidad nueva).

### Para retomar, en este orden

1. ✅ **Hecho el 2026-09-11 (mig `_28`).** Las capturas (`Ejemplo_13` a `_15`) dieron la razón al
   OCR: el catálogo tenía **cortados** `Cilindro neumático de Bigger` y `Templo a la granizada
   estelífera`. Renombrados, `match_catalogo` resuelve las 4 lecturas crudas (antes ninguna), y las
   3 capturas quedaron como verdad de tierra en `test_parser_weapon_s30`. `Tetera esmeraldina`:
   segunda lectura idéntica, confirmada. De paso la captura desmintió el `HP% 20%` de la fila 42
   (dice **Defensa**) ⇒ `DEF%`, valor NULL. **La lección:** los dos nombres largos ya estaban en el
   repo (verdad de tierra de S26 desde julio, diálogo de S29); un `grep` del nombre en `app/` antes
   de la `_27` lo resolvía sin capturas. Detalle y lo que queda de la fila 42:
   `audit/weapons_catalog_20260910.md`.
2. ✅ **Hecho el 2026-09-11 — pero no como prefijo.** `match_catalogo` recorta un token final en
   MAYÚSCULAS (el arte: *DESRE*, *CRASH*; nunca un romano) y resuelve el resto con el matching de
   siempre. El prefijo cruzaba `Modelo II`/`III` y se habría tragado cualquier arma nueva que empiece
   como una del catálogo; el recorte no puede ninguna de las dos. En campo: 10 de las 12 lecturas
   "fuera del catálogo" del log resuelven, y las 2 restantes no son armas. Detalle en
   `audit/weapons_catalog_20260910.md`.
3. ✅ **Hecha el 2026-09-11, 12:41.** Las 5 armas que el catálogo y el matching ya reconocen, todas
   con dueño nombrado, entraron como `s30_insert`: Inocencia sacrificada (Anby), Tetera esmeraldina
   (Qingyi), Cilindro neumático de Bigger (Ben), Templo a la granizada estelífera (Miyabi) y Anhelo
   marcato (Orfia y Magas). `inventory_weapons` 38 → **43**; reporte
   `audit/censos/20260911_124216_511537_censo_armas.md` con **0 fuera de catálogo**;
   `integrity_check` ok, FK limpias, ningún PJ con dos equipadas.
4. ✅ **Hecho el 2026-09-11.** El criterio es **"sin rareza = panel a medio dibujar"**, no "sin
   refinamiento": en 127 lecturas de S30 del log la rareza vino vacía sólo 2 veces y ninguna era un
   arma asentada (la transición `Última cena · ? · P? · dueño ?` y el panel de la propia app),
   mientras que `P?` aparece en paneles asentados y válidos (Petrazufre, Cañón bombástico). El
   handler no reporta ni persiste ese frame; el asentado vuelve a cambiar la firma y se lee entero.
5. ✅ **Decidido por Daniel el 2026-09-11: las libres se escriben — pero primero se arregló la causa
   del falso LIBRE**, que seguía vivo (Compilador quimérico, de Grace, salió LIBRE **3 veces** en
   campo, y por eso Grace no tenía fila). De "Hough no vio la cara" se concluía "no hay cara". Ahora
   `read_weapon_owner_badge_s30` **mide el lugar del dueño** (nitidez en un disco anclado a la fila
   del círculo de especialidad): dueños 51-100, libres 0.5-0.7 — **73× de gap** sobre las 15
   capturas, y Compilador da 60.5. Sin círculo de especialidad no hay ancla ⇒ "no sé", nunca
   "libre". Con cara pero sin localizar ⇒ presente **sin recorte** (no se nombra con un encuadre
   estimado). Ninguna de las 11 capturas con dueño sale libre; las 4 libres reales siguen libres.

   **Y el mismo día, a Grace se la nombra.** Daniel capturó su arma otra vez (`Ejemplo_16`). La
   librería no era el problema: recortada en el lugar correcto, Grace sale primera con 0.09-0.12
   contra 0.33 de Gatillo (margen > 0.2). Fallaba LOCALIZAR la cara: su avatar tiene menos
   contraste en el borde y Hough, con `param2=20`, no la ve. Cuando la nitidez ya dijo "hay cara",
   se reintenta con `param2=16` sólo en la banda del dueño y a la altura del círculo de
   especialidad (±10 px); el centro sigue saliendo de Hough y el radio de la constante, así que el
   encuadre es el de la librería. Las libres no llegan al reintento: su nitidez es 0.5.

   **Validación en vivo (2026-09-11, 14:04-14:06).** 13 armas vistas, reporte
   `audit/censos/20260911_140625_068464_censo_armas.md`:

   | | |
   |---|---|
   | Compilador quimérico | `la tiene Grace` → fila 46, `s30_insert` (antes: LIBRE, sin fila) |
   | libres | 11 filas `s30_libre_insert` (44-45, 47-55), sin dueño |
   | Última cena libres | copia 0 y copia 1 → filas 47 y 48 |
   | Rotor de cañón libres | copia 0 y copia 1 → filas 49 y 50 — **a confirmar con Daniel** |
   | frame de transición | 1 vez (14:05:56), descartado; la lectura siguiente salió entera |
   | DB | 43 → **55**, `integrity_check` ok, FK limpias |

   **El Rotor de más (resuelto el dato, abierta la causa).** Daniel tiene UN Rotor de cañón
   libre y se quedó parado sobre él; la "segunda copia" (fila 50) salió a las 14:05:54, justo
   antes de que el panel cambiara a Viaje estruendoso. Hipótesis sin probar: el recuadro de
   selección salta a la casilla nueva antes de que el panel se redibuje, y "otra casilla + mismo
   panel" es exactamente lo que parece una copia idéntica. El localizador acierta 16/16 en las
   capturas quietas, así que no es sospechoso en frío. Se agregó la posición al log (`· @(x,y)`,
   commit `696a54c`) y la pasada de las **16:21** no lo reprodujo: tres lecturas del Rotor en
   `@(582,832)`, las tres `s30_libre_vista` sobre la fila 49 — **primera evidencia en vivo de que
   volver a una libre ya vista no la duplica**. La fila 50 quedó con `descartado = 1` (mig `_29`,
   baja lógica y reversible). Si el fantasma vuelve, la línea del log trae la casilla.

6. ✅ **Billy, Zhao y Billy Estelar — cerrados el 2026-09-12.** Tres armas no se podían atribuir y
   la causa era la LIBRERÍA, no el código. Detalle y números en
   `audit/latencia_y_badges_20260912.md`.

   - **Billy y Zhao**: cosecha guiada (ficha → arma → botón *Desequipar*, que es lo único que
     confirma el dueño sin librería). `Réplica de motor estelar` pasó de abstenerse (top `Ben`
     0.422, margen 0.027) a `la tiene Billy` (0.172, margen 0.250); `Transmorfer original`, de
     0.306 con margen 0.029 a **0.120** con margen 0.215. **El umbral de margen no se tocó** — y
     menos mal: es lo único que impidió escribir el arma de Billy a nombre de Ben.
   - **Billy Estelar**: su `Tránsito herciano` se atribuyó a Billy. No es un atuendo — en `agents`
     es otro PJ (id 47, S, Disruptivos). La causa: **la ref vieja de la clase `Billy` era la cara
     de Billy Estelar**, y como una clase se compara con su MEJOR ref, Billy ganaba 0.16 a 0.26 en
     el arma ajena. Se MOVIÓ la ref a su clase (no se borró) y quedó `Ejemplo_18` → Billy Estelar
     0.156, margen 0.272. La mig `_30` reasignó la fila 26.
   - **Lo que destapó el caso fue un veto**: al cosechar desde la ficha de Estelar, el juego decía
     "Billy Estelar" y el matcher afirmaba "Billy" ⇒ `veto_conflicto`, sin aprender nada. La guarda
     que evita envenenar una clase es además el mejor detector de clases envenenadas.
   - **Un error mío que vale documentar:** descarté esta hipótesis una vez con una distancia L2
     sobre la imagen en gris en vez de `descriptor_distance`. Ver A1 en las prácticas.

   Los tests miden contra un snapshot nuevo
   (`audit/avatar_detbadge_v2_snapshot_20260912_billy_estelar.npz`): 35 en verde y ningún `xfail`.

7. **La `Réplica de motor estelar` de Billy todavía no tiene fila.** No se inventa: la escribe la
   próxima pasada que la vea. Hasta la mig `_30` no podía, porque Billy figuraba con el Tránsito y
   el bucket B se abstenía — correctamente, porque una de las dos lecturas estaba mal.

   Cómo se escriben: una libre no tiene PJ que la identifique, así que su clave es (arma, nivel,
   refinamiento) + el **número de copia** que el monitor calcula desde la posición en la grilla. La
   copia k es la k-ésima fila libre de esa clave (`find_free`, con `IS` por el refinamiento NULL):
   si existe se reusa (`s30_libre_vista`), si no se inserta sin dueño (`s30_libre_insert`,
   `origen_evidencia='s30_libre'`). Nunca mueve ni borra; las equipadas idénticas no se tocan.
   **Límites, dichos en el reporte:** una libre que después se equipa, se sube de nivel o se recicla
   deja su fila vieja (no se borra por ausencia, B2), y volver a una copia libre tras un scroll
   puede sumar una fila de más.

### Cómo arrancar y cerrar una sesión (dos trampas medidas el 09-10)

- La app **la lanza Claude** desde su shell: `powershell -ExecutionPolicy Bypass -File
  tools/qa_launch.ps1 -FromSource`. Si la lanza Daniel, el contenedor MSIX hace que el shell lea una
  copia congelada del log.
- **Cerrar la pasada con F8, nunca con la X.** `closeEvent` hace `QApplication.quit()` sin pasar por
  `controller.stop()`: la X no cierra el censo (se pierde el reporte) y no deja `Monitor detenido`
  en el log. **Que esa línea falte no es un crash** — se verificó: salida 0, sin traceback, sin
  eventos de Windows.
- Antes de escribir la DB: app cerrada, **verificado** con `tasklist`, y sin `-wal` suelto.
- Un script largo con heredocs en el shell Bash de esta máquina puede fallar con *unexpected EOF
  while looking for matching quote* sin que se pueda ver dónde: escribirlo a un archivo y correrlo.

## Queda abierto

> Estado al 2026-09-08, después de la primera pasada. Los números y el detalle completo están en
> [`audit/censo_armas_20260908.md`](../../../../audit/censo_armas_20260908.md): **28 filas escritas**,
> 53/185 identidades, sólo rangos S y A.

- ~~**Los frames de transición cuentan como un arma más.**~~ **Cerrado el 2026-09-11** (ver *Para
  retomar*, punto 4). Lo que decía: en el mismo log del 09-10, una lectura
  `Última cena · ? · P? · dueño ?` (el pill todavía no estaba dibujado) entró al censo como una
  identidad provisoria propia, porque su refinamiento es `None`. Sobrecuenta de 1 por cada
  transición que alcance a leerse. Es previo al arreglo de copias y va aparte.
- ~~El contador del header dio 185, 56 y 75~~ **Cerrado el 2026-09-10**: el 185 es el total con los
  B; 56 y 75 eran vistas filtradas. Los B quedan fuera por decisión de Daniel.
- ~~Segunda pasada por los 4 engines duplicados~~ **HECHA el 2026-09-08**: las 9 filas entraron,
  `inventory_weapons` quedó en **37**. Cerrada con F8, reporte en `audit/censos/`.
- **Los tiles de rango B**, sin recorrer.
- ✅ **Hecha el 2026-09-10** (mig `_27`, 59 → 61) — sólo 2 de los 6 eran reales; ver *Estado al
  cerrar la sesión del 2026-09-10*. Lo que sigue quedó como historia. **La migración curada del catálogo** — **6** armas, no 7: `Cúter` (de Pulchra) y `Última cena`
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

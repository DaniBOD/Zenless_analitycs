# Criterio de equipamiento — casos etiquetados por Daniel (human first)

Registro vivo de la elicitación del 2026-09-22. Cada caso: situación, decisión de Daniel, su
razonamiento literal (resumido), y qué regla candidata sale. Al cerrar la elicitación esto pasa al
repo como doc + fixture de tests: el motor nuevo se mide por cuántas decisiones reproduce.

## Decisiones de marco

- **Fuentes**: Prydwen es la BASE (defaults para todos los usuarios); Daniel la pule a mano. O sea
  dos capas: default (fuente prydwen) + override del usuario (fuente usuario). AkumaTHG es su
  referente, pero entra a través de sus respuestas, no como fuente scrapeada (RNF-02).
- **Rangos objetivo** por stat clave (ej. Ellen ATK 3000-3200). Stat no clave (DEF en Ellen) no
  tiene rango.

## Caso 1 — Ellen, slot 2, CR bajo el rango

Ellen: ATK 3150 (en rango), CR 58 %, CD 175 %. Dos slot 2 Nivel 15, mismo set (el del 4pc).
- X: CR +2 (7,2 %) · ATK 3 % · ATK 19 · DEF 15
- Y: CD +2 (14,4 %) · ATK +1 (6 %) · ATK 19 · PEN 9

**Decisión: Y.**
Razón: gana una stat de utilidad (Perforación); la DEF de X no sirve para nada. La CR que se
pierde no es notable: sigue "en el 50 %", parecido. Cambiaría si estuviera cerca del 70 %
(lo marca como opinión subjetiva).

Nota: el motor ACTUAL también elige Y (pesos CR = CD = 1,0 con los mismos rolls; Y suma ATK% +1
roll y PEN 0,5). El caso no separa modelos — pero deja dos reglas:
- **R1 · línea muerta**: una substat sin uso para el PJ es costo real (ocupa un lugar); una de
  utilidad secundaria (PEN en Ellen) suma aunque pese menos.
- **R2 · el valor de un stat clave depende de dónde está el build respecto del rango** — lejos por
  debajo, moverse un poco no decide; cerca del borde del rango, sí. (subjetivo, a confirmar)

## Caso 2 — los mismos X e Y, Ellen con CR 65 %

X la lleva a CR 72,2 % (entra al rango) con DEF muerta; Y la deja en CR 65 %, DC 189,4 %, con PEN.

**Decisión: Y otra vez.**
Razón: con CR 65 / DC 175 los dos stats de crítico "ya están bien, sólo sería pulir". Y además
sube ATK%, que tiene mucho valor. Y la DEF no sirve frente a la PEN.

Lectura:
- **R1 confirmada** (2/2): la línea muerta pesa fuerte.
- **R3 · ATK% vale mucho** para Ellen.
- **R2 debilitada**: entrar al rango de CR NO alcanzó para compensar línea muerta + roll de ATK%.
  Aparece un concepto nuevo: **zona "ya está bien"** — dentro de ella, más stat es "pulir" y vale
  poco. En el caso 1 incluso 58 % (bajo el mínimo 60 de la DB) le pareció "similar": los bordes
  del rango son blandos.
- ⚠️ **Error de diseño mío**: los casos 1 y 2 estaban confundidos — X siempre tenía la línea muerta
  y un roll útil menos. No podían aislar CR vs DC. El caso 3 iguala todo menos eso.

## Caso 3 — aislado: sólo CR vs DC (Ellen CR 65 / DC 175)

X: CR +2 · ATK 3 % · ATK 19 · PEN 9 → CR 72,2 / DC 175.  Y: DC +2 · ATK 3 % · ATK 19 · PEN 9 → CR 65 / DC 189,4.

**Decisión: X.**
Razón: ya hay harto Daño Crítico; lo que importa es bajar la "lotería" de que salga el crítico.

Lectura:
- **R4 · balance del crítico**: con DC abundante respecto de CR, gana la CR. Valora la
  CONSISTENCIA (menos varianza), no sólo el promedio.
- Coincide con la cuenta: multiplicador esperado 1 + CR·DC → X 2,2635 vs Y 2,2311 (+1,5 %). La
  razón de Daniel (varianza) es un argumento EXTRA que el promedio no captura.
- Refina R2: la zona "ya está bien" no apaga el stat; adentro decide el BALANCE entre los pares.
- Idea de diseño: valuar el crítico con la fórmula del juego (1 + CR·DC, CR tope 100 %) en vez de
  pesos fijos — el balance sale solo.
- ⚠️ Otro error mío: en Nivel 15 un S tiene **+5 mejoras** (arrancando con 4 líneas) o **+4**
  (arrancando con 3). Mis discos de los casos 1-3 tenían +2/+3: irreales. No cambia las
  preferencias relativas, pero los fixtures tienen que ser realistas. Corregido desde el caso 4.

## Caso 4 — ¿romper el 4pc por mejores secundarios?

Ellen 4pc A (1-4) + 2pc B (5-6). Slot 2 actual (A): CR+1 · DC+1 · ATK%+1 · PV+2 (muerta).
Nuevo (set C, no lo usa): CR+2 · DC+2 · ATK%+1 · PEN. Equiparlo la baja a 3pc A.

**Decisión: NO.** "El 4pc no se rompe salvo que sean secundarios excelentes, y sería muy
puntual. Además lo más normal sería romper un 2pc, no un 4pc."

Lectura:
- **R5 · el 4pc es casi una regla dura** (con válvula de escape estrecha: "excelentes, muy puntual").
- **R6 · el 2pc SÍ se rompe**, es lo normal. → el 2pc pesa mucho menos que el 4pc.
- ~~El motor viejo acá acierta de casualidad~~ — **FALSO, medido después.** Esa cuenta la hice a
  mano con el peso de 4pc 1,5, que sólo se aplica si alguien le pasa al scoring el 4pc del PJ, y
  `recomendar()` no se lo pasa: el set cuenta sólo por su arquetipo (0,7). Además la línea de PV
  del actual está en los perjudiciales de ATK_DPS y resta. Resultado real: el motor actual
  **rompe el 4pc** (ver la línea de base al final). Una cuenta a mano no es una medición (A1).

## Hallazgo estructural (leyendo el recomendador que emite los toasts)

- `recomendar()` decide **Equipar por umbral ABSOLUTO** (score ≥ 0,75), **no comparando con lo que
  el PJ ya tiene** en ese slot. Las 4 respuestas de Daniel fueron COMPARATIVAS.
- `recomendar()` **no le pasa al scoring el 4pc/2pc del PJ** (`agent_set4p_id` queda None): el set
  se evalúa sólo por arquetipo. Y en la DB los PJs tienen `set_4p_id`/`set_2p_id` en NULL (rebuild
  del 2026-08-17: el build se OBSERVA en el censo, no se declara).
- El **optimizador** (RF-06) sí trabaja a nivel build, con el bono de sets en el build. Es la pieza
  más cercana a cómo decide Daniel.

## Caso 5 — ¿romper el 2pc?

Supuesto: Ellen 4pc Metal polar (1-4) + 2pc Tecno Pícido (5-6, 2pc = +8 % CR). CR 65 % (con los 8
adentro), DC 175 %. Slot 6, mismo principal (ATK 30 %):
- Actual (Tecno Pícido): CR+1 4,8 % · DC 4,8 % · ATK plano +2 57 · PV +2 336 (muerta)
- Nuevo (otro set): CR+1 4,8 % · DC+2 14,4 % · ATK% +2 9 % · PEN 9
Equiparlo rompe el 2pc: CR 65 → 57 %, DC 175 → 184,6 %, algo más de ataque.

**Decisión: SÍ lo equipa.** "El 2pc son sólo stats"; el disco da más DC y lo compensa; y cambiar
ATK plano por ATK% +2 está mucho mejor.

Lectura:
- **R7 · el 2pc es fungible: son stats y nada más.** Se puede modelar como su aporte de stats al
  build. El 4pc (R5) NO: es un efecto, casi regla dura.
- **R8 · ATK% >> ATK plano**, y sacar una línea muerta suma.
- ⚠️ **Tensión con R4 y con la cuenta.** El multiplicador de crítico baja de 1+0,65·1,75 = 2,1375 a
  1+0,57·1,846 = 2,0522 (**−4,0 %**), justo en la dirección que en el caso 3 no quería (menos CR
  con DC abundante). Para que el ATK% lo compense, el ATK total tiene que subir ≥ 4,16 %: con 3150
  de ATK hacen falta ~+131 netos, o sea 0,09·base − 57 ≥ 131 → **base de ataque (PJ + arma) ≥
  ~2090**. Ese número NO está medido. Hay que preguntarle a Daniel quién manda cuando su criterio y
  la fórmula no coinciden.

## Decisión de diseño D1 — quién manda cuando criterio y fórmula no coinciden

**Daniel eligió C: la fórmula del daño como base, y sus reglas como ajuste encima.**
- El motor calcula el valor del build con las reglas del juego (multiplicador de crítico 1+CR·DC
  con CR tope 100 %, 2pc como stats, rangos objetivo).
- Encima, ajustes que el promedio no ve, calibrados con los casos: premio a la consistencia del
  crítico ("lotería", R4), castigo extra a la línea muerta (R1), 4pc protegido (R5).
- Cuando un caso y la fórmula discrepan, es dato: o falta un ajuste, o la cuenta está mal hecha.

## Caso 6 — tres discos Nivel 0 de slot 4 (Mejorar / Guardar / Descartar)

Antes de contestar, Daniel pidió **qué set se farmeó y sus bonos**: para juzgar un disco "para la
cuenta entera" el set es lo primero que mira (define a qué PJs les sirve). → Dato de diseño: la
decisión sobre un disco nuevo arranca por el SET → candidatos, no por los secundarios.

Los tres son **Tecno Pícido** (de la DB: 2pc Prob. Crítica +8 %; 4pc: al hacer crítico con Ataque
Básico, Contraataque de esquiva o Especial EX, ATK +9 % por 6 s, cada skill con su propio timer).
- D1: principal Daño Crítico · CR 2,4 · ATK 3 % · PEN 9 · (sin 4ª línea)
- D2: principal Daño Crítico · CR 2,4 · PV 112 · DEF 15 · ATK 19
- D3: principal PV % · CR 2,4 · DC 4,8 · ATK 3 % · PEN 9

**Decisiones:**
- **D1 → MEJORAR.** Potencial para atacantes o aturdidores.
- **D2 → DESCARTAR.** Dos stats basura para atacantes/aturdidores. A lo más un disruptor, con
  puntuación baja: el ATK plano "sirve a medias", la vida sí sirve, la DEF no, la CR es útil.
- **D3 → GUARDAR sin mejorar.** Principal PV % no sirve "ni para disruptores, que buscan prob o
  atq", a pesar de los secundarios perfectos. Sólo como relleno temporal de un slot; si la cuenta
  ya está cubierta, se borra. Si algún PJ sí lo aprovecha, se toma.

Lectura:
- **R9 · el principal equivocado mata al disco** (slots 4-6): secundarios perfectos no lo salvan.
- **R10 · "Guardar" es relleno temporal** y depende de la COBERTURA de la cuenta: sin hueco que
  tapar, se borra. → Reserva/Descartar no es propiedad del disco solo: mira el inventario.
- **R11 · un disco nuevo se juzga por ROL** (atacante, aturdidor, disruptor), no por PJ.
- **R12 · Mejorar** = principal correcto + 3 líneas útiles para el rol, aunque la 4ª sea incógnita.
- **R13 · Descartar** = 2 líneas basura para los roles que habilitan el set y el principal.

### Lo que dice el motor ACTUAL (medido, DB en sólo lectura, sha256 intacto)

| | Daniel | motor actual | score |
|---|---|---|---|
| D1 | MEJORAR | **DESCARTAR** ❌ | 0,448 |
| D2 | DESCARTAR | DESCARTAR ✅ | 0,183 |
| D3 | GUARDAR | **DESCARTAR** ❌ | 0,448 |

**1 de 3.** Dos causas, las dos estructurales:
1. **Un Nivel 0 se normaliza contra el máximo de un +15** → ningún disco nuevo llega al 0,50 de
   "mejorar" salvo que sea perfecto (tope sin rolls ≈ 0,55). El motor **no sabe evaluar potencial**:
   descarta justo el disco en que Daniel invertiría.
2. **El principal vale lo mismo que una línea** (peso 1,0): D1 (principal bueno) y D3 (principal
   equivocado, 4ª línea buena) empatan EXACTO en 0,448. R9 dice que el principal equivocado mata.
- Y un síntoma del "todo default": el top es un **triple empate** N.º 11 / Billy / Harumasa en
  0,448 — mismos pesos de arquetipo, el motor no los distingue.

### Discrepancia con la DB (a confirmar)

El arquetipo `HP_DISRUPT` en la DB acepta en slot 4 **Prob. Crítica, Daño Crítico y PV %**. Daniel
dice que los disruptores buscan **prob o ataque**, no PV %. Además, en D2: ATK plano "a medias"
(DB: 0) y DEF "no sirve" (DB: −0,8, penaliza).

**Resolución de Daniel:**
- **Disruptores, slot 4 = sólo Prob. Crítica y Daño Crítico** (opción B). Sale PV % del default de
  `HP_DISRUPT`. Es un ajuste del usuario sobre el default del arquetipo.
- **D3 → DESCARTAR** como respuesta general (lo de "guardar" era sólo si hay un hueco que tapar;
  consistente con R10: por defecto se borra, se guarda únicamente con falta de cobertura).
- Con eso el motor actual coincide en **2 de 3** — pero ⚠️ el acuerdo en D3 es **por la razón
  equivocada**: el motor puso a D3 el MISMO 0,448 que a D1 (no vio el principal equivocado) y lo
  descartó porque descarta todo Nivel 0. Acierta el resultado, no el motivo. Para los tests: un
  caso que el motor acierta por casualidad tiene que fijar también el MOTIVO (p. ej., que el
  puntaje de D3 quede claramente por debajo del de D1), o no protege nada.

## Caso 7 — a mitad de camino: ¿seguir subiendo?

D1 del caso 6 (Tecno Pícido, slot 4, principal Daño Crítico), ya en **Nivel 6**. En +3 apareció
la 4ª línea y en +6 subió una. Dos resultados posibles:
- D1a: CR 2,4 · ATK 3 % · **PEN +1 · 18** · **DEF 15** (4ª línea muerta)
- D1b: **CR +1 · 4,8** · ATK 3 % · PEN 9 · **ATK 19** (4ª línea plana, "a medias")

**Decisión:** D1b → **sigue subiendo**. D1a → **frena y descarta**. PERO: "igual mejoraría ambos
al máximo, porque es importante ver el valor final".

Lectura:
- **R14 · el juicio definitivo es sobre el valor FINAL (+15).** La regla "freno y descarto" es la
  recomendación, pero en la práctica sube todo para ver cómo termina. → A mitad de camino la app no
  debería ordenar "frenar": lo útil es mostrar **qué se puede esperar del final**. Es calculable
  EXACTO: quedan 3 mejoras sobre 4 líneas equiprobables → 4³ = 64 resultados igual de probables.
- **R15 · una 4ª línea muerta a mitad de camino hunde la expectativa** lo suficiente como para que
  la recomendación sea descartar (1 de cada 4 mejoras futuras se va a la basura).
- La app ya observa las mejoras en vivo (S10, PRE→POST), así que tiene el dato para mostrarlo.

## Caso 8 — el tope del rango

Ellen, rango de ATK 3000-3200, pero YA tiene 3350. CR 62 %, DC 170 %. Dos slot 1 (PV 2200),
mismo set, Nivel 15, sin líneas muertas:
- X: ATK% +3 · 12 % · ATK +1 · 38 · CR +1 · 4,8 % · PEN 9
- Y: CR +2 · 7,2 % · DC +1 · 9,6 % · ATK% +1 · 6 % · PEN +1 · 18

**Decisión: Y.** Pasado el tope "rinde menos pero sigue sumando". Además "con cálculos, un
crítico acertado da mucho más DPS que meramente más ATK": en este caso, stats más HOMOGÉNEOS.

Lectura:
- **R16 · el tope del rango = rendimiento decreciente, NO un techo.** (Y el piso, por el caso 1,
  es blando: 58 vs mínimo 60 le pareció "similar".)
- **R17 · homogeneidad**: con un factor alto, conviene subir los otros. Es exactamente lo que da
  una fórmula MULTIPLICATIVA (daño ∝ ATK × (1 + CR·DC) × …): el valor marginal de cada stat es
  proporcional a los demás. Parte del "rendimiento decreciente" sale sola de la fórmula.
- Cuenta: Y sube el multiplicador de crítico de 2,1356 a 2,2428 (**+5,0 %**). Para que X empate,
  su ATK extra (6 % de la base + 38) tendría que valer > 5,0 % de 3350 = 167,5 → **base ≥ ~2158**.
- ⚠️ **Los casos 5 y 8 dependen del mismo número que no tengo: el ATK BASE de Ellen (PJ + arma).**
  El motor con fórmula lo va a necesitar para cada PJ. Es una dependencia de datos del diseño.

## Diseño — Parte 1 aprobada (flujo de decisión de la etapa 1)

Candidatos por principal (R9) → Nivel 15: ¿le gana a lo que el PJ ya tiene? (4pc protegido, 2pc
como stats) → EQUIPAR · Nivel < 15: valor final esperado → MEJORAR · bueno para su rol pero no le
gana a nadie → RESERVA · si no → DESCARTAR.

**RESERVA confirmada**, con su ejemplo: sale un nuevo atacante eléctrico en el futuro; un Tecno
Pícido de slot 5 con Bono Daño Eléctrico + DC, CR, ATK plano y ATK% "es un disco perfecto, pero no
para la actualidad sino para el futuro". → Se guarda aunque hoy no le gane a nadie.
(Nota: en su "disco perfecto" entra el ATK plano: perfecto = principal correcto y sin línea muerta.)

### Hallazgo de datos para la Parte 2

Los stats actuales de cada PJ están VACÍOS: `agents.prob_critico` / `dano_critico` con valor en
1 de 52, `ataque` en 0 de 52 (Ellen: todo NULL). Viene de la reconstrucción del 2026-08-17 (stats
a 0) y de que las pasadas son `-ReadOnly`. Sin eso no se puede:
- aplicar los RANGOS (hay que saber dónde está el PJ respecto del rango),
- balancear el crítico (caso 3: depende del CR y DC actuales del PJ).
El parser de S18 (stats del agente) existe; falta que esos datos lleguen a la DB.

## Línea de base del motor actual (medida, 2026-09-22)

Los 8 casos quedaron como tests en `app/tests/fixtures/criterio_equipar/casos.json` +
`app/tests/unit/test_criterio_casos.py` (11 decisiones: el caso 6 son tres discos y el 7 son dos).
El estado de cada PJ viaja adentro del caso, así que el test no lee la DB.

**El motor actual reproduce 7 de 11.**

| caso | Daniel | motor actual | por qué falla |
|---|---|---|---|
| 1, 2, 5, 8 | — | ✅ | — |
| 6_D2, 7_D1a, 7_D1b | — | ✅ | — |
| **3** | X | **empate exacto** | pesa CR y DC igual; no sabe que Ellen ya tiene DC de sobra |
| **4** | mantener | **cambiar** | no conoce el 4pc del PJ y castiga la línea de PV del actual |
| **6_D1** | mejorar | **descartar** | normaliza el Nivel 0 contra un +15; no evalúa potencial |
| **6_D3** | descartar | descartar, **por la razón equivocada** | mismo puntaje que D1 (0,448): no ve el principal PV % |

Los cuatro quedan como `xfail` ESTRICTO: si un cambio arregla uno sin sacar la marca, el test se
pone rojo, igual que si rompe uno que andaba. Sabotajes 4/4 en rojo (la decisión invertida, un
caso marcado que empieza a pasar, dejar de exigir el motivo, una marca con el id mal escrito).

### Paso 2 — el puntaje cuenta el stat, y el principal equivocado descalifica → **8 de 11**

- Una línea pasa de `peso × (1 + 0,25·mejoras)` a `peso × (1 + mejoras)`: proporcional al stat.
  El máximo teórico deja de suponer 5 mejoras en CADA línea (un disco imposible) y pasa a las 4
  mejores líneas + las 5 mejoras en la mejor. Es una cota, no un valor exacto por slot: en 1-3 el
  principal no suma, y en 4-6 su stat no puede repetirse abajo.
- `scoring.principal_valido()` es la única autoridad sobre "¿este principal le sirve a este
  rol?": la usan el recomendador (un PJ con el principal equivocado deja de ser candidato) y el
  optimizador, que antes tenía su propio `if` para lo mismo (B1).
- **Arregla 6_D3 por la razón correcta**: D3 ya no empata con D1 (0,25 contra 0,43), porque el PV %
  sólo lo aceptan los disruptores y los defensores, y para ellos los secundarios de D3 valen poco.
- Los negativos NO se tocaron (E3: ningún caso los discute todavía).
- Sabotajes 5/5 en rojo. Siguen pendientes 3 (balance del crítico), 4 (4pc) y 6_D1 (potencial).

### Paso 3 — la decisión compara, y el set es del build → **9 de 11**

- `evaluar_cambio()`: cuánto mejora el build de un PJ si en ese slot se pone el disco nuevo =
  (disco nuevo − disco actual) + (bonos de set del build después − antes). Un slot vacío vale 0,
  y de ahí sale solo el "relleno temporal" (R10).
- **El set se cuenta una vez, en el build**: el disco solo ya no cobra su set (antes el set entraba
  como atributo del disco, por arquetipo).
- **2pc = stats (R7)**: el bono se pasa a mejoras equivalentes con el **valor por mejora MEDIDO**
  sobre los 386 discos del inventario (unánime por stat: CR 2,4 en 253/253, DC 4,8 en 203/203, …;
  un test lo vuelve a medir en sólo lectura). Los 2pc que no son un secundario (Daño Hielo, Daño
  de Ataque Básico, Recarga, Impacto) no suman y **se anotan**: no se inventa un valor.
- **4pc (R5)**: tenerlo vale `VALOR_4PC_FRACCION = 0,5` del mejor disco posible para ese PJ, así
  que romperlo cuesta eso y completarlo suma eso. Calibrado con UN caso (el 4: hacía falta > 0,42);
  tentativo hasta que haya más.
- `recomendar(..., builds=)`: con builds y un disco LIBRE en Nivel 15 → EQUIPAR a quien más mejora
  (con el movimiento y su delta), RESERVA si es bueno para su rol pero no le gana a nadie, si no
  DESCARTAR. Un disco que lleva otro PJ sigue por el camino viejo hasta el paso 7 ("A no pierde").
  **Ningún llamador lo usa todavía**: se cablean en los pasos 7 y 8.
- Sabotajes 8/8 en rojo. Pendientes: 3 (balance del crítico) y 6_D1 (potencial).
- **Orden ajustado: 3 → 5 → 4 → 6 → 7 → 8.** Si el potencial (paso 4) entra antes que los ajustes
  de Daniel (paso 5), D3 vuelve a salir "mejorar" para los disruptores, porque el default de la
  DB todavía acepta PV % en su slot 4.

### Paso 5 — dos capas: el default y los ajustes de Daniel (migración 40)

- Tres tablas nuevas: `ajustes_usuario_rangos`, `ajustes_usuario_pesos` y
  `ajustes_usuario_arquetipo`. Los defaults (`agent_thresholds`, `agent_substat_preferences`,
  `disc_archetypes`) **no se tocan**. El repositorio mezcla: el ajuste gana, y si se borra la fila
  vuelve el default. Las reglas viven en el esquema (piso ≤ techo, peso en [-1, 1], sólo
  `mains_4/5/6`, valor como lista JSON).
- Cargado lo que Daniel ya dijo: disruptores en slot 4 = Prob. Crítica y Daño Crítico; Ellen ATK
  3000-3200. Verificado en la app real: Ellen lee `ataque (3000, 3200)` y sus rangos de CR/DC
  siguen en el default de Prydwen.
- `mezclar_pesos`: con ajustes, la base son los pesos propios **o los del arquetipo**. Si no, un
  PJ sin pesos propios al que se le ajusta UN stat quedaría con ese único stat y el resto en 0.
- En los defaults de Prydwen casi nunca está el máximo, pero sí el óptimo: el óptimo hace de techo.
- `rebuild_account_db` conserva las tres tablas (son declaraciones del usuario).
- Migración ensayada sobre una copia y aplicada con backup: `backup_premig_20260922_212711`, cuyo
  sha256 es el de la DB antes de migrar. 8 smoke checks exactos, `foreign_key_check` sin filas.
- ⚠️ **La primera suite dio 34 rojos.** El repo pasó a leer SIEMPRE `substats_positivos` de
  `disc_archetypes`, y 34 tests arman una DB mínima con sólo `id` y `code`. Esa columna sólo hace
  falta cuando hay ajustes de pesos: ahora se lee sólo entonces, y `agent_thresholds` se lee sólo si
  tiene las columnas del rango. Los tests del paso sobre la copia de la DB real no lo podían ver,
  porque la copia tiene el esquema completo: por eso existe la suite completa.
- Sabotajes 8/8 en rojo, antes y después del arreglo.

### Paso 4 — un disco sin terminar se juzga por lo que puede llegar a ser → **10 de 11**

- `potencial()`: el puntaje **esperado en Nivel 15**, exacto por linealidad (cada mejora pendiente
  sube una de las 4 líneas con la misma probabilidad y el puntaje es lineal en las mejoras). Dos
  tests lo comparan contra la **enumeración completa**: 4³ = 64 finales para un Nivel 6, y cada 4ª
  línea posible × 4⁴ repartos para un Nivel 0 de 3 líneas.
- Premisa MEDIDA sobre el inventario antes de escribirlo: los Nivel 15 tienen 4 o 5 mejoras (283
  y 74 discos, todos con 4 líneas), los Nivel 6 una, los Nivel 12 tres → mejoras en
  +3/+6/+9/+12/+15, y la primera agrega la 4ª línea si faltaba.
- La 4ª línea de un disco que arrancó con 3 se promedia entre los secundarios que no están ni son
  el principal, con probabilidad **uniforme**: `cuarta_linea_supuesta = True`, tentativo hasta tener
  la probabilidad real de una fuente autorizada (RNF-02).
- Una **línea muerta conocida** (peso ≤ 0 para ese rol: si no suma, ocupa un lugar) descarta (R13,
  R15). El disco se evalúa para todos los roles, y vale el mejor que **no** tenga líneas muertas
  (R11): la DEF que mata a un atacante puede servirle a otro rol.
- Un disco sin terminar sólo puede salir MEJORAR o DESCARTAR: primero se sube, después se equipa.
- `score_disco` y `potencial` usan la MISMA fórmula por línea (`_aporte_pos` / `_aporte_neg`); si
  cada uno tuviera la suya, el esperado dejaría de ser el promedio de lo que el motor puntúa.
- Sabotajes 6/6 en rojo. Pendiente: el 3 (balance del crítico, paso 6).
- ❓ **Para confirmar con Daniel:** un Nivel **0** con 4 líneas de las cuales **una** es muerta. Hoy
  se descarta, porque se generalizó la R15 (que él dijo a mitad de camino, Nivel 6). No lo
  preguntamos.

## Caso 9 — Nivel 0 con cuatro líneas, UNA muerta

**Decisión: MEJORAR.** "Se puede permitir uno muerto siempre y cuando las mejoras no apliquen a
él."

Lectura, y cómo encaja con el caso 7:
- **R15' · una línea muerta se tolera; se frena cuando se le GASTA una mejora**, sea la que la sube
  (+1) o la que la creó (la 4ª línea de un disco que arrancó con 3). En 7_D1a la DEF la creó la
  mejora del +3, así que ya se había gastado una mejora en ella → frenar. En el caso 9 viene de
  origen → mejorar.
- **R13 sigue: dos muertas → descartar.**
- Cómo se sabe si una mejora creó la 4ª línea: si hay una mejora menos repartida que las hechas,
  el disco arrancó con 3. **Premisa NO medida:** la línea agregada es la ÚLTIMA en pantalla (el
  orden en que la lee el parser).
- ⚠️ Un sabotaje que apagaba R13 **pasaba en verde**: en los ejemplos las muertas restan, el valor
  esperado queda bajo y el disco se descarta igual. La regla estaba escrita y no se ejercía. Ahora
  hay un test con dos muertas de peso exactamente 0 en un disco que por lo demás se mejoraría.
- Casos: **11 de 12** (el caso 9 entra al fixture y pasa). Sabotajes 4/4 en rojo.

### Paso 6 — el estado del PJ entra al peso: balance del crítico y rangos → **12 de 12**

- **Balance del crítico** (caso 3, R4): el multiplicador medio es 1 + CR·DC, así que una mejora
  de CR vale 2,4 %·DC y una de DC 4,8 %·CR. Se reparte el MISMO peso total de los dos según esa
  proporción: cambia el balance, no la escala. Pasado el 100 % la CR no suma. Sólo necesita CR y DC
  actuales, no la base de ATK.
- **Rangos** (R16): pasado el techo, factor `techo / actual`: rinde menos, nunca 0. Dentro o por
  debajo, 1 (bordes blandos, caso 1). ⚠️ **Ningún caso calibra la curva**: el caso 8 pasa con o sin
  ella. Sólo está fijada la DIRECCIÓN; la magnitud es tentativa.
- **Una sola función de pesos** para todo el motor (`scoring._pesos`): `score_disco`, `potencial` y
  los bonos de set del recomendador, que tenía su propia copia y valuaba un 2pc de CR sin el balance
  que sí veía el disco (B1).
- `Agent.stats` sale de las columnas de `agents` que llena S18. **Hoy la DB los tiene en 1 de 52
  PJs** (Claret: CR 95,2 / DC 93,2), así que en la app real el balance y los rangos casi no actúan
  todavía. Sin stats, pesos fijos, y el repositorio lo dice UNA vez con el número.
- Los casos llevan el estado del PJ con el vocabulario de la DB (`prob_critico`, `dano_critico`,
  `ataque`) y los rangos de Ellen: el default de Prydwen con el ajuste de Daniel encima.
- **Tus casos: 12 de 12.** Ya no queda ningún `xfail`. Sabotajes 9/9 en rojo.

### Paso 7a — mover un disco de un PJ a otro sólo si el que lo tiene NO pierde

- **Regla nueva de Daniel**, que reemplaza la del 2026-09-12 (movía si el destino ganaba más de lo
  que perdía el origen, neto > 0): el ORIGEN tiene que quedar igual o mejor. Para eso cuenta que
  puede recibir un disco LIBRE del inventario en ese slot, y también dejar el slot vacío, que puede
  ser mejor que un disco que le resta.
- Una sola regla para los dos que mueven discos (B1): `recommender.evaluar_salida`. La usan el
  recomendador (para las sugerencias) y el optimizador (para admitir un disco ajeno en una build).
  El optimizador conserva además su anti-traslado (neto > 0): mover sin ganar no es una mejora.
- ⚠️ **El primer test estaba mal armado.** Daba por "igual de bueno" un reemplazo con ATK plano +3
  en lugar de ATK% +3. Para un PJ que no valora el plano, ese reemplazo lo deja 2,0 abajo, y la
  regla hizo bien en no mover. Se corrigió el test y ese caso quedó como test propio (R7: el ATK%
  vale mucho más que el plano).
- **Costo medido** (optimizador, 52 PJs, copia de la DB): 62 → 319 ms de mediana al aplicarlo. Se
  bajó a **124 ms** (p90 142, máx 152) con dos cambios, medido uno por vez. Primero, mirar al origen
  sólo si el destino gana (→ 140). Segundo, leer una sola vez el build de cada origen por corrida
  (→ 124). El doble que antes, con 3× de margen bajo los 500 ms del RNF-06.
- Sabotajes 7/7 en rojo.

### Paso 7b — el motor sobre todo el inventario (`app/scripts/sugerir_movimientos.py`)

- Evalúa los discos activos y deja `audit/sugerencias/<ts>_sugerencias_discos.{md,json}` con cinco
  listas: mover (el que lo tiene no pierde), equipar un libre, mejorar, reserva y descartar. Las
  que se pisarían (mismo slot del mismo PJ, o un disco comprometido dos veces) se toman de la de
  más ganancia para abajo, y el resto queda **en conflicto**: no desaparece. Sólo lee la DB (se
  abre con `mode=ro` y se compara el sha256).
- ⚠️ **Un sabotaje escribió la DB de dominio.** El test "corre sobre la DB real" apuntaba a la DB
  de verdad. El sabotaje que le sacaba el `mode=ro` al script le creó una tabla vacía
  (`_sabotaje`). Se midió la diferencia con `iterdump`: esa tabla y nada más. Se guardó el estado
  contaminado como backup y se restauró la versión del commit (sha256 idéntico al de antes,
  `integrity_check` ok, sin FKs rotas). Ahora el test corre sobre una copia, y el script de
  sabotaje compara el sha256 después de cada sabotaje y aborta si cambió. Es la misma lección de
  `feedback_tests_contaminaron_db_dominio`: que algo sea de sólo lectura es justo lo que el test
  no puede dar por hecho.
- Un sabotaje quedó en verde: "un disco sin nivel se sugiere igual". La DB real tiene **0 de 380**
  discos activos sin nivel, así que esa rama no corría nunca. Se agregó un test que la ejerce.
- Sabotajes 5/5 en rojo. En 1,3 s sobre la DB real.
- **Primera corrida (380 discos): mover 122 · equipar 57 · mejorar 8 · reserva 0 · descartar 7.
  No se mostró**: salía Bono Daño Fuego → Lycaon (Hielo), Eléctrico → Piper (Físico), Hielo y Éter
  → Manato (Fuego). Los arquetipos aceptan los seis Bono Daño en el slot 5 y nadie lo cruzaba con
  el elemento del PJ. Se arregla en su propio commit.

### Arreglo — un Bono Daño de otro elemento es un principal equivocado (R9)

- `principal_valido(disc, arquetipo, pj)`: un "Bono Daño X" sólo sirve si X es el elemento del PJ
  (`agents.elemento`, cargado en los 52 PJs). Lumen no acepta ninguno, porque no existe "Bono Daño
  Lumen" (confirmado in-game el 2026-07-29). Un PJ sin elemento no se restringe (B2). Las tres
  llamadas pasan el PJ: `score_disco`, `evaluar_salida` (un reemplazo tiene que ser del elemento
  del origen) y el optimizador.
- Resultado (380 discos): mover 122 → **109**, mejorar 8 → 7, descartar 7 → 8; equipar sigue en
  57, pero los destinos ahora coinciden (Bono Daño Hielo → Lycaon, Éter → Yixuan, Hielo → Soukaku).
- ¿Por qué tantas mejoras? Se midió que **no** son builds incompletas: sólo 3 PJs tienen menos de
  6 discos (Antón 4, Ben 5, Nekomata 5), y 134 de las 166 sugerencias de equipar/mover van a un
  slot ocupado. Piper, que es destino de 5 movimientos, tiene una build de Anomalía con Daño Crítico,
  PV %, DEF % y DEF en casi todos los discos.
- Sabotajes 7/7 en rojo, con la DB de dominio comparada por sha256 después de cada uno.

### Primera revisión de Daniel sobre las sugerencias (2026-09-23)

Se le mostraron las sugerencias sin conflicto y cuatro dudas. Respuestas:

1. **#213 · Tasa de Perforación en el slot 5 → caso 10.** "Le sirve a atacantes como opción
   secundaria y de momento a los armeros, Claret se ve muy beneficiada de esto, los supports/apoyo
   se pueden beneficiar, por eso lo guardé (Rina por ejemplo) aunque es de nicho". → Migración 41
   (capa de ajustes): ATK_DPS y SUPPORT_ER aceptan Tasa de Perforación en el slot 5; ARMORER_DEF ya
   la aceptaba. Con eso #213 pasa de descartar (puntaje 0) a **equipar → Nekomata** (+1,90, que
   tiene la build incompleta). ⚠️ "Secundaria" y "de nicho" no se modelan todavía: el principal
   decide si el disco sirve, no cuánto vale frente a un Bono Daño.
2. **#369 · Floración, slot 5 Bono Daño Hielo, Nv 0 (DEF, ATK%, DC) → caso 11.** "No está bien el
   descarte actual de ese disco". Medido: el motor comparaba el valor esperado contra un umbral
   FIJO (0,468 < 0,50), no contra lo que el PJ ya lleva. Pero subido le gana al slot 5 de Soukaku
   (3,56 contra 2,90) y al de Lycaon (3,41 contra −1,00). Era un desvío de R12 ("mejorar si en lo
   esperable le gana a algo") que el paso 4 implementó mal. Arreglado: con `builds`, MEJORAR pasa
   por la misma comparación que un disco terminado (`evaluar_cambio`, con el valor esperado); las
   guardas R13 y "mejora gastada en una muerta" siguen por encima, y valen POR PJ. #369 → **mejorar
   → Lycaon**. Totales: mejorar 7 → 10, descartar 8 → 5. Sin `builds` (el fixture de casos) sigue
   el umbral.
3. **Piper destino de 5 movimientos → falta un dato: la PRIORIDAD DE BUILDEO.** "Actualmente no es
   su mejor build, acá se me olvidó mencionar la prioridad de buildeo, por ejemplo Piper no la uso
   casi nada mientras que Claret la quiero mejorar ahora, luego declaramos eso". Pendiente de
   declarar (por PJ, en la capa de ajustes) y de decidir cómo pesa: orden de las sugerencias, o
   que un PJ de prioridad baja no le saque discos a uno de prioridad alta.
4. **Reserva en 0 → esperado.** "El sistema siempre busca mejoras en mis PJs".

### Segunda revisión de Daniel: las sugerencias con prioridades (2026-09-25)

Se le mostraron las 28 firmes de `audit/sugerencias/20260925_000654_781001` con los tres discos de
cada una (el que llega, el que está, el que repone). Con las dos primeras alcanzó:

- **Caso 12 · #152 → Ye Shunguang (+6,30).** "No le sirve Armonía umbría en general porque el PJ no
  genera réplicas". Medido: los +6,30 son todos de substats (Prob. Crítica +3, Perforación +2); el
  disco reemplaza al #275 y **rompe el 2pc de Tecno tetraodóntido** (Tasa de Perforación +8 %), que
  vale 0 porque ese 2pc no es un substat. Pasa con **19 de 30 sets**: su 2pc "sin modelar" no cuesta
  nada al romperse.
- **Caso 13 · #163 → Nangong Yu (+6,12).** "No le sirve Balada porque las 2pc son para daño crítico;
  ella es una stunner/anómala con una build peculiar". Medido: rompe el 2pc de Jazz Caótico, y el
  arquetipo STUN le da a la Prob. Crítica el peso mayor (1,13). Falta el perfil de stats PROPIO.
- **Raíz:** `agents.set_4p_id/set_2p_id` están en NULL en los 52 PJs (eran la build observada y nadie
  la reconstruye desde el rebuild del 2026-08-17); el set sólo entra por `disc_set_archetype`, que
  es por ROL, no por PJ.
- **Hallazgo aparte:** en 3 slots dos firmes se pisan (Piper s3, Nangong Yu s6, Dialyn s2):
  `resolver_conflictos` no reserva el slot del ORIGEN que ocupa el disco que repone.

**Decisiones (2026-09-25):**

- **R18 · el set es del PJ, no del rol.** Base de conocimiento por PJ desde las wikis (Prydwen
  primaria, Game8 cruce; fuente y URL por fila; lo no confirmado queda NULL): sets de 4pc y 2pc en
  orden, y en la misma pasada los principales de los slots 4-6 y la prioridad de substats.
- **R19 · build objetivo:** el que declara Daniel en la ficha del PJ (capa de ajustes); si no hay,
  los sets equipados **si están entre los recomendados** para ese PJ; si no, el primero recomendado.
- **R20 · un disco de un set fuera del build objetivo no es candidato** para ese PJ, por buenos que
  sean sus substats (como R9 con el principal).
- **Gatillo y Grace (alta) llevan un 4pc que la guía no lista** (Armonía umbría; Blues Libre): "son
  builds mías que veo óptimas, dejalo como builds creadas por el usuario". Declarados en
  `ajustes_usuario_build`. Corolario: **una build declarada vale aunque la guía no la nombre**; la
  guía es el default, no un límite.

### Tercera revisión de Daniel: el motor por PJ (2026-09-25, tarde)

Sobre `audit/sugerencias/20260925_100942_416192` ("va mucho mejor ahora"):

- **Caso 11 vs R20 → mandan los sets.** "Pesa mucho más los sets": el #369 (Floración, slot 5 Hielo)
  se descarta porque Floración no está en el build objetivo de Lycaon ni de Soukaku. El caso 11
  queda SUPERADO por R20 (el fixture lo sigue probando sin build objetivo, por rol).
- **Aplicadas en el juego:** #85 Anby → Dialyn (repone #92) y #188 Astra Yao → Ju Fufu (repone
  #192). "Realizalos en la db para que tenga trazabilidad" → mig 44 (`movimientos_discos`).
- **Caso 14 · #151 N.º 0: Anby → Gatillo (+1,06) NO.** "Tiene en la pasiva más impacto a cuanta
  más probabilidad tenga, y aunque swapear el disco se ve bueno bajaría mucho su Prob. Crítica."
  Medido: 75,4 % → 68,2 %; su habilidad adicional da +1,5 % de aturdimiento de réplicas por cada 1 %
  sobre 40 %, hasta 90 % → −10,8 puntos de aturdimiento.
- **R21 · stats fijos.** "Podemos tener intervalos de stats pero algunos PJ requieren un stat fijo
  para aprovechar todo su potencial, como Astra Yao y Zhao, que requieren cierto ATK (Astra) y HP
  (Zhao) para aportar el buff de sus pasivas al equipo." Un cambio no se sugiere si BAJA un stat
  fijo del PJ y lo deja por debajo del objetivo (ni al que recibe ni al que entrega). Objetivos
  con su cuenta en `pj_stats_fijos` (mig 45), desde los kits en Prydwen con la pasiva al Lv. 7.
- **Descartes:** se revisan después de las sugerencias.

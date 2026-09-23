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

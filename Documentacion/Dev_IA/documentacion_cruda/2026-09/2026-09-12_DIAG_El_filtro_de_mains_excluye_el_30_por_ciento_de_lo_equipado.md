# DIAG · El filtro de mains por arquetipo excluye el 30 % de lo que los PJs llevan puesto

> **Fecha:** 2026-09-12 · **Tipo:** DIAG (sin cambios de código ni de DB) · **Alcance:** `disc_archetypes`, `app/core/optimizer.py`, `app/core/scoring.py`
> **Viene de:** [FIX baseline](2026-09-12_FIX_El_optimizador_media_contra_una_tabla_vacia.md) §5.2 — *"el slot 4 de Miyabi es `Daño Crítico` y ANOMALY no lo acepta"*
> **Prácticas en juego:** A1, A5 (conteo sobre el total), B1 (dos autoridades del vocabulario), B2 (estado provisional sin salida), RNF-02

---

## 1. La pregunta y la respuesta corta

¿Es un problema de Miyabi? **No.** Es un caso de un problema general, y ni siquiera el más grande.
Sobre los 152 discos equipados en slots 4–6, el filtro de mains del arquetipo del **propio PJ que
los lleva** deja afuera **46 (30 %)**, en **29 de 51** PJs. Adentro hay tres cosas distintas:

| categoría | discos | naturaleza |
|---|---|---|
| **A. Vocabulario viejo en `disc_archetypes`** | 9 | bug verificado, con un pendiente escrito hace 3 meses |
| **C. Arquetipo más angosto que la build real** | 37 | decisión de diseño/datos — incluye a Miyabi |
| (sin categoría B: ver §4) | | |

## 2. Cómo funciona el filtro (lectura de código)

- **El arquetipo sale del rol de juego**, no de la build: `AgentRepo._load` mapea
  `agents.rol` → código (`Anomalía`→ANOMALY, `Defensa`→DEFENSE, …, fallback ATK_DPS). Seis
  especialidades, seis arquetipos, sin override por PJ.
- **El optimizador filtra DURO** (`_greedy_candidates`): un disco de slot 4–6 cuyo main no está en
  `mains_N` del arquetipo **no es candidato**.
- **El scoring filtra BLANDO** (`score_disco`): mismo chequeo, pero `no_match` solo significa no
  sumar `peso_main` (+1.0). El disco sigue siendo puntuable.
- RF-06 §4.1 prevé una tolerancia (*"si el main está en la lista del arquetipo secundario del set,
  se acepta con factor 0.7"*). **No está implementada**: no hay arquetipo secundario en `Agent` y
  nada en `optimizer.py`/`scoring.py` lo busca.

El RF-06 §5 dice *"un disco que el evaluador marca como 'Equipar en Miyabi' sea efectivamente el que
el optimizador elegiría… Cualquier divergencia es bug"*. Duro contra blando es exactamente esa
divergencia: el evaluador puede recomendar un disco que el optimizador ni siquiera mira.

## 3. Medición — los 46, agrupados (conteo sobre el total)

DB de dominio en solo lectura. Main de cada disco equipado contra `mains_N` del arquetipo de su dueño.

| n | arquetipo | slot | main excluido |
|---|---|---|---|
| **8** | ANOMALY | 6 | **Tasa de Anomalía** |
| 4 | ATK_DPS | 6 | Recarga de Energía |
| 3 | SUPPORT_ER | 4 | Maestría de Anomalía |
| 3 | SUPPORT_ER | 6 | Tasa de Anomalía |
| 2 | ATK_DPS | 5 | Tasa de Perforación |
| 2 | ANOMALY | 5 | Tasa de Perforación |
| 2 | DEFENSE | 4 | Prob. Crítica |
| 2 | DEFENSE | 5 | ATK% |
| 2 | DEFENSE | 6 | ATK% |
| **1** | ANOMALY | 5 | **Bono Daño Viento** |
| 1 | ANOMALY | 4 | Daño Crítico ← Miyabi |
| 16 | varios | — | 1 disco cada combinación (DEFENSE con Físico/Eléctrico/ATK%/Maestría/ER, STUN con ER/ATK%/Maestría/Tasa, SUPPORT_ER con HP%/PEN/ATK%, ANOMALY con DEF%/ER) |

PJs con 3 exclusiones: Velina, Lucía, Ben, Pan Yinhu, Seth. Con 2: Nicole, Nangong Yu, Vivian,
Rina, Yanagi, César, Soukaku.

## 4. Categoría A — vocabulario viejo (9 discos, bug verificado)

### 4.1 `Maestría de Anomalía` en slot 6 (8 discos, todos los ANOMALY que llevan main de anomalía)

`disc_archetypes.ANOMALY.mains_6 = ["Maestría de Anomalía", "ATK%"]`. **Ese main no existe en
slot 6.** La autoridad del vocabulario lo dice por tres vías independientes:

| fuente | slot 4 | slot 6 |
|---|---|---|
| `stats_vocab.CANONICAL_MAINS_VARIABLE` | Maestría de Anomalía | **Tasa de Anomalía** |
| RF-04 §7.2.1 (corrección 2026-06-03, mig 09) | Maestría de Anomalía (flat) | **Tasa de Anomalía (%)** |
| valores en `inventory_discs` | 14 discos, **92** flat (1 en 23) | 13 discos, **30 %** (1 en 12) |

La entrada `Maestría de Anomalía` en `mains_6` es **letra muerta**: ningún disco puede
cumplirla, así que para un PJ ANOMALY el slot 6 solo admite ATK%.

**Por qué quedó así — y no es la primera vez (B2):** la migración 09 corrigió los discos y
`stats_vocab`, y su audit (`audit/correccion_tasa_anomalia_20260603.md` §4) dejó escrito:

> *"La tabla de arquetipos del RF-04 §7.2.2 … aún dice 'Maestría Anomalía'; debería ser 'Tasa de
> Anomalía' para slot VI. NO se tocó acá … Revisar al implementar `scoring.py`."*

Nadie lo revisó. Un pendiente sin dueño ni disparador es un estado provisional sin salida. La
migración 08 (`fix_archetypes_mains`, 2026-05-04) sí había corregido `mains_5`/`mains_6` contra
`stats_vocab`, pero es **anterior** a la separación Maestría/Tasa.

La tabla del RF-04 §7.2.2 además está desalineada con la DB en otra celda: dice `ATK_DPS` Mains VI =
*"Crit DMG, ATK%"*. Crit DMG no es main de slot VI según el §7.2.1 de arriba, y la migración 08 ya
lo había sacado de la DB (`["ATK%"]`). El doc quedó atrás de su propia corrección.

**Efecto medido** (en memoria, sin escribir la DB): cambiando solo esa palabra en `mains_6`,

- **10 de 11** PJs ANOMALY pasan a usar un `Tasa de Anomalía` en el slot 6 de su mejor build
  (Burnice sigue en ATK%);
- el `score_actual` de los **8** que ya lo llevan sube **exactamente +1.0**: el `peso_main` que
  `score_disco` les negaba.

O sea que **no es solo el optimizador**: el scoring compartido (RF-04, recomendador) también puntúa
mal hoy el disco de slot 6 correcto de todo PJ de anomalía.

### 4.2 `Bono Daño Viento` ausente de `mains_5` (1 disco, Velina)

Los cinco arquetipos que listan bonos elementales listan Físico, Fuego, Hielo, Eléctrico y Éter.
Viento entró al juego con Velina (patch 3.x) y está en `stats_vocab`, pero no en
`disc_archetypes`. Es la misma omisión que la 4.1: el catálogo no siguió al vocabulario.
(`Bono Daño Lumen` no falta: ese main no existe, está fijado como contrato en `test_stats_vocab.py`.)

## 5. Categoría C — arquetipo más angosto que la build (37 discos)

Todos son mains **válidos** en el juego que el arquetipo del rol no admite. Ejemplos: ER en slot 6
de atacantes (Harumasa, Billy, Cissia, Orfia y Magas), ATK%/crit en defensores (Seth, Pan Yinhu,
Ben, César), Maestría/Tasa de Anomalía en soportes y aturdidores (Nicole, Soukaku, Rina, Nangong
Yu, Yuzuha), Tasa de Perforación en slot 5.

Esto **no** se puede resolver mirando el código. La pregunta es si la build que el PJ lleva es la
buena (y el arquetipo le queda chico) o si el disco es un parche (y el filtro hace bien). RNF-02:
hace falta fuente por PJ, y no está en la DB.

### 5.1 Miyabi, en particular

La DB **se contradice a sí misma** sobre Miyabi:

| autoridad | qué dice |
|---|---|
| `agents.rol = 'Anomalía'` → ANOMALY | slot 4 solo Maestría/ATK%; `Daño Crítico` como substat es **perjudicial (−0.6)** |
| `agent_thresholds` de Miyabi (fuente: Prydwen/IcyVeins) | objetivos **Prob. Crítica 65–80 %** y **Daño Crítico 160–200 %** |
| RF-04 §7.2.2, nota de ANOMALY | *"`Daño Crítico` es perjudicial … `Prob. Crítica` se deja en intermedio porque algunos anomaly PJs (Miyabi, Yanagi) sí hacen daño directo con crits secundarios"* |
| su build real | slot 4 `Daño Crítico`; Prob. Crítica y Daño Crítico en substats |

El diseño **consideró** a Miyabi y decidió tratarla como anomalía con crit secundario. Los
thresholds cargados después (con fuente) la describen como escaladora de crit. El optimizador,
entonces, penaliza la stat que su propio benchmark pide maximizar. No tiene
`agent_substat_preferences` que lo compense (solo 9 PJs las tienen).

## 6. Opciones — ❓ decisión de Daniel

### Para A (bug, sin ambigüedad de diseño)

**A1. Migración de datos + contrato.**
- `UPDATE disc_archetypes`: ANOMALY `mains_6` Maestría → **Tasa de Anomalía**; agregar
  **Bono Daño Viento** a los `mains_5` que ya listan los cinco elementos.
- Corregir la tabla de RF-04 §7.2.2 (celdas Mains VI de ANOMALY y ATK_DPS).
- **Test de contrato:** todo `mains_N` de `disc_archetypes` ⊆ `stats_vocab.CANONICAL_MAINS_VARIABLE[N]`
  (una sola autoridad del vocabulario, B1). Hoy fallaría: habría atrapado la letra muerta de slot 6
  el mismo día de la migración 09.
- Escribe la DB ⇒ RNF-01 completo y la app cerrada.

La "completitud" (que todo elemento del vocabulario esté en los arquetipos elementales) **no** va en
el contrato: que un arquetipo admita o no un main es diseño (categoría C). El contrato solo exige que
lo que lista **exista**.

### Para C / Miyabi (necesita fuente y criterio)

| opción | qué hace | costo |
|---|---|---|
| **C1. Override de arquetipo por PJ** | columna `agents.arquetipo_override` (Miyabi → ATK_DPS si la fuente lo respalda) | chico, pero el arquetipo es de a uno: una Miyabi mitad crit mitad anomalía no entra |
| **C2. Mains preferidos por PJ** | tabla análoga a `agent_substat_preferences`, para mains | fiel por PJ; hay que cargarla con fuente por cada uno de los 29 |
| **C3. Filtro blando en el optimizador** | igual que el scoring: un main fuera de lista no suma `peso_main`, pero es candidato | cierra la divergencia RF-06 §5 sin datos nuevos; sigue sin premiar el main correcto de Miyabi |
| **C4. Nada** | se acepta que el arquetipo del rol manda | los 37 siguen invisibles para el optimizador |

**Recomendación:** **A1 ya.** Es el bug limpio, con 3 fuentes concordantes y un pendiente escrito.
Después, **C3**: una sola regla de filtro para evaluador y optimizador, que es lo que exige el
RF-06, y no requiere inventar datos. **C1/C2** solo con fuente por PJ (RNF-02). Para Miyabi el
punto de partida es la contradicción de §5.1, que tiene que resolver Daniel: sus thresholds de
Prydwen o la nota de diseño del RF-04. La DB no puede decidir cuál de las dos está bien.

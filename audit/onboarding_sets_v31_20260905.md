# Onboarding de los dos sets de la v3.1 — Hado emplumado y Rosa espinosa

**2026-09-05.** Disparado por un síntoma de campo: *"el nodo nuevo no lo detecta"*. No era el
matcher — el nodo no estaba cargado, y los sets tampoco del todo.

## Qué estaba mal, y por qué en silencio

Los dos sets entraron a `disc_sets` con **sólo el nombre en español**:

```
id=54  Hado emplumado   nombre_en NULL   bonus_2p NULL   bonus_4p NULL   arquetipos: 0
id=55  Rosa espinosa    nombre_en NULL   bonus_2p NULL   bonus_4p NULL   arquetipos: 0
```

Cada NULL apaga algo distinto, y ninguno avisa:

| campo | qué apaga |
|---|---|
| `nombre_en` | `farm_nodes.toml` resuelve por nombre inglés ⇒ el set **no puede** estar en ningún nodo, y un set sin nodo no se predice en S13 |
| `bonus_2p_*` | el toast muestra `2pc=-` |
| `disc_set_archetype` | el scoring puntúa el disco **sin contexto de set** |

Lo último no era teórico: había **4 discos de Hado emplumado equipados en Remielle Dan**,
puntuándose como si el set no existiera.

## El nodo: tres vías independientes, y coinciden

El nodo nuevo es **"Espina veloz y garra desgarradora"**
(`Screenshots_Triggers/Discos_Triggers/13_Seleccion_set_farmeo/Ejemplo_7.png`).

1. **El hueco del catálogo.** De los 30 sets de la DB, exactamente 2 no pertenecían a ningún
   nodo — y son estos dos.
2. **El matcher de logos de la app.** `SetBadgeMatcher` identificó los dos íconos del tile del
   nodo contra las **30 clases abiertas** (sin restringir a candidatos):

   ```
   logo izquierdo -> Feathered Fate   conf 0.602   margen 0.138 al 2º (Phaethon's Melody)
   logo derecho   -> Thorned Rose     conf 0.456   margen 0.154 al 2º (King of the Summit)
   ```

   Confianzas modestas —las refs son renders de package y estos son íconos circulares in-game,
   el riesgo que el propio módulo documenta en §8.1— pero lo que vale es el ranking.
3. **Las wikis.** Game8, Fandom e Icy Veins: los dos sets dropean del stage
   **"Swiftspine and Splitclaw"**, que es la traducción literal del título en español. Y cuesta
   **60 de batería** por intento, lo que coincide con el `200/60` de la captura.

Esto importa porque la regla del proyecto es **verificar por el logo, nunca por parecido de
texto** — la lección de cuando 6 de 30 nombres de set no resolvían y `sync_equip` descartaba el
20 % de los discos en silencio.

## Los bonos: dos fuentes, y coinciden en los cuatro valores

**La pantalla manda para la redacción** (capturas de la ficha "Información de conjunto"), **las
wikis verifican los números**. No hubo discrepancias.

| | 2 pistas | 4 pistas |
|---|---|---|
| **Hado emplumado** | Maestría de Anomalía +30 | MdA +50 al entrar/pasar a activo, 15 s; si es Lumen, +15 % daño de Anomalía de Atributo; sigue off-field |
| **Rosa espinosa** | Defensa +16 % | Daño +15 %; con DEF inicial ≥1000/1800, Prob. Crítico +8/16 % |

### Dos decisiones de redacción que quedaron anotadas

- **`lumiflujo` es el rótulo de pantalla; el canónico es `Lumen`** (`agents.elemento`, Remielle
  Dan). El rótulo de pantalla nunca es el canónico — misma lección que dejó "Lumiflujo" fuera del
  vocabulario. En el `bonus_4p_desc` va `Lumen`.
- **Una ambigüedad que no se resolvió inventando.** En español el *"durante 15 s"* queda pegado a
  la cláusula de lumiflujo, así que podría leerse como que sólo el +15 % dura 15 s. Game8 es
  explícito en que los 15 s cubren el buff entero, y el español no lo contradice: se escribió con
  esa lectura y quedó anotado en la migración. Si algún día importa la diferencia, eso es lo que
  hay que volver a mirar en pantalla.

## Arquetipos: por precedente, no por criterio propio

```
Anomaly Proficiency +30  ->  ANOMALY(p1)   ya lo tienen Jazz Caótico y Blues Libre
DEF +16%                 ->  DEFENSE(p1)   ya lo tiene Rock espiritual
```

Corroborado por el uso real: los 4 discos de Hado emplumado son de **Remielle Dan**, la única PJ
de Lumen del juego —justo para quien el 4pc está diseñado— y su slot 4 lleva **Maestría de
Anomalía** de main.

Rosa espinosa podría llevar `ATK_DPS` secundario por el "+15 % de daño", pero *Rock espiritual*
—mismo 2pc— está sólo como `DEFENSE`. Se siguió el precedente; queda como opción abierta.

## El test que faltaba

Un set sin nodo no se predecía **en silencio**, y así estuvo desde que salió la v3.1. Ahora hay
tres tests de cobertura contra la DB real: ningún set sin `nombre_en`, todos pertenecen a un
nodo, y el caso concreto. El primero mira **todas** las filas y no sólo las que ya tienen
`nombre_en`: filtrar por ese campo repetiría exactamente la ceguera que dejó pasar el caso.

Verificado sacando el nodo del `.toml`: 3 rojos.

## Verificación

```
_24  nombre_en          5 smoke checks exactos
_25  bonos+arquetipos   6 smoke checks exactos
     foreign_key_check  0 violaciones      integrity_check  ok
     262 tests del subconjunto (farm/sets/scoring/recommender/sync) en verde
```

Las dos ensayadas contra una copia de la DB antes de la corrida real.

## Queda abierto

- **`farm_nodes.toml` no se copia al bundle de PyInstaller**
  (`FileNotFoundError: ...\\_internal\\app\\resources\\farm_nodes.toml`, 2026-08-18): la
  predicción de sets **nunca funcionó empaquetada**. Con `-FromSource` no se nota.
- Rosa espinosa todavía no tiene ningún disco capturado (set recién salido).

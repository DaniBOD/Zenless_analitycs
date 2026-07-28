# Saneamiento del catálogo `weapons` — cierre

**Fecha:** 2026-07-28 · **Migraciones:** `2026-07-27_10`, `2026-07-27_11`, `2026-07-28_13`
**Herramienta:** `tools/audit_weapons_catalog.py` (read-only, repetible)

---

## De dónde salió

El pedido de Daniel fue chico: *"arreglemos esa discrepancia de la rareza"*. Auditando
apareció que la rareza no era el problema sino el **síntoma**. El catálogo se cargó
en bloque emparejando cada nombre español contra un nombre inglés **por parecido**, y
cuando el parecido erraba, la fila entera heredaba los datos de otra arma: rareza,
tipo de especialidad y ATK base.

La prueba de que era eso y no errores sueltos: `nombre_en` ni siquiera servía de clave.
Dos filas distintas (id 6 "Proyector de celuloide" e id 35 "Pacificador especializado")
apuntaban las dos a *Peacekeeper - Specialized*.

## Lo que destrabó el diagnóstico

Daniel cargó 40 capturas de la pantalla de detalle de sus W-Engines. Con eso apareció
el discriminador que faltaba:

> **El Ataque Base a Nivel 60/60 separa la rareza sin solaparse.**
>
> | rareza | ATK base observados |
> |---|---|
> | S | 684 · 713 · 743 |
> | A | 594 · 624 |
>
> 32 muestras a nivel máximo, cero solapes.

Eso convirtió cada corrección en algo con **dos evidencias independientes**: el ATK que
se lee en pantalla y la traducción literal del nombre. Y mostró que el catálogo asignaba
**S de más de forma sistemática** — la firma de una carga masiva mal emparejada.

## La regla que se siguió para el mapeo ES↔EN

Para no repetir el pecado original (emparejar por parecido), la tercera pasada se ató a
una regla explícita:

| Situación | Acción |
|---|---|
| Traducción **palabra por palabra** (*Cámara acorazada* = The Vault) | se aplica |
| Solo parecido semántico (*Tránsito herciano* ≈ Radiowave Journey) | **NO** se aplica: `nombre_en` va a NULL y la hipótesis queda acá, no en la DB |

El motivo de ser tan estricto: `nombre_en` es lo que después va a resolver el **ícono**
del arma (`Documentacion/Interfaz/Engines_icons/` está nombrada en inglés). Una etiqueta
inglesa equivocada no es cosmética — arrastra al ícono equivocado.

---

## Resultado

| | Inicio | Tras `_10` | Tras `_11` | **Tras `_13`** |
|---|---|---|---|---|
| Coinciden rareza y tipo | 32 | 39 | 53 | **53** |
| Rareza distinta a la referencia | 6 | 2 | 0 | **0** |
| Tipo distinto a la referencia | 2 | 1 | 0 | **0** |
| `nombre_en` que no existe en el juego | 13 | 13 | 7 | **0** |
| Sin mapeo EN declarado (NULL) | 0 | 0 | 0 | **5** |
| Filas totales (sin "Sin arma") | 55 | 58 | 60 | **58** |

**53 verificadas + 5 lagunas declaradas = 58.** No queda ninguna fila con datos que
aparenten estar confirmados sin estarlo, que era el objetivo real.

### Migración `_13` en detalle

**A · Duplicados fusionados** (confirmados por Daniel el 2026-07-28). En los dos pares,
una fila tenía el nombre español real y la otra uno inventado, delatado por el sufijo
artificial en `nombre_en`. Se conservó la fila con el nombre real —que además era la
única referenciada por `inventory_weapons`/`agents`— y se borró la otra.

| se conserva | se borra | queda como |
|---|---|---|
| 46 *Aguijón agudo* | 27 *Aguijón afilado* (`Sharp Stinger A`) | Sharpened Stinger · S · Anomalía · 713 |
| 48 *Engranaje infernal* | 47 *Hellfire Gears* (`Hellfire Gears S`) | Hellfire Gears · S · Aturdimiento · 684 |

**B · Rareza corregida** (confirmada por Daniel: *"son rareza A no S, capaz los confundió"*).
`tipo_especialidad` también fue a NULL: venía del mismo emparejamiento desmentido, y **no
se puede deducir del atributo avanzado** — las capturas prueban que el stat no determina
la especialidad (*Slice of Time* es Soporte y muestra Perforación; *Peacekeeper - Specialized*
es Defensa y muestra Ataque).

| id | nombre | era | queda |
|---|---|---|---|
| 5 | Última cena | The Restrained · S · 684 | NULL · **A** · 594 |
| 13 | Caldero ardiente | Roaring Fur-nace · S · 713 | NULL · **A** · 594 |

**C · Mapeos por traducción literal** (mismo defecto, encontrados al revisar A y B):

| id | nombre | era | queda | por qué |
|---|---|---|---|---|
| 39 | Cámara acorazada | Bashful Demon | **The Vault** | literal; le estaba usurpando el nombre a id 44 |
| 44 | Demonio cohibido | Bashful Demon B · B | **Bashful Demon** · A | literal |
| 16 | Petrazufre | Bellicose Blaze | **The Brimstone** | *petra + azufre* = brimstone |
| 14 | Caldero de la claridad | Half-Sugar Bunny · S · Defensa | **Cauldron of Clarity** · A · Ruptura | literal |

**D · `atk_base` contra la pantalla.** Verificando el ATK de Petrazufre apareció que la
columna arrastra el mismo mal. Comparando las 32 capturas a 60/60 contra el catálogo
salieron 5 filas con el ATK de otra arma:

| id | arma | era | queda |
|---|---|---|---|
| 40 | Roaring Ride | 594 | 624 |
| 7 | Starlight Engine | 684 | 594 |
| 36 | Starlight Engine Replica | 594 | 624 |
| 11 | Cannon Rotor | 713 | 594 |
| 16 | The Brimstone | 713 | 684 |

Re-verificado después de aplicar: **cero discrepancias** entre `atk_base` y las 32
capturas a nivel máximo.

**E · NULL declarados.** Tres nombres ingleses inventados sin candidato literal.

---

## Lo que queda abierto

### 1. Cinco filas sin mapeo EN (`nombre_en IS NULL`)

Se resuelven con una captura de la pantalla de detalle de cada una. Las hipótesis viven
acá **a propósito** y no en la DB:

| id | nombre (ES) | ATK visto | candidato sospechado | por qué no se aplicó |
|---|---|---|---|---|
| 5 | Última cena | 594 | — | ninguno plausible en la lista canónica |
| 13 | Caldero ardiente | 594 | The Simmering Pot · Steam Oven | dos candidatos, ambos A/Aturdimiento, ninguno literal |
| 37 | Primavera termal | 594 | Spring Embrace | *spring* coincide, *embrace* ≠ *termal* |
| 42 | Cilindro neumático | — | Big Cylinder | *neumático* ≠ *big* |
| 53 | Tránsito herciano | — | Radiowave Journey | *hercio* ≈ radiofrecuencia, no literal |

Para id 42 y 53 el `atk_base` tampoco está verificado (42 tiene 500, que no es valor de
nivel 60 de ningún rango).

### 2. Filas S nunca observadas, con el mapeo dudoso

No se tocaron: Daniel no las posee, así que no hay captura, y sin fuente en español la
corrección sería otra adivinanza. Pero el emparejamiento se ve tan flojo como el que ya
se corrigió, y conviene mirarlas cuando aparezca una fuente:

| id | nombre (ES) | `nombre_en` actual | traducción del EN |
|---|---|---|---|
| 20 | Garra del corazón | Dreamlit Hearth | hogar iluminado por sueños |
| 21 | Aguja del tiempo | Spectral Gaze | mirada espectral |
| 31 | Llama del corazón | Blazing Laurel | laurel llameante |
| 32 | Fuego ardiente | Cordis Germina | — |
| 19 | Visitante elegante | Elegant Vanity | vanidad elegante |

Además, tres filas tienen el **nombre inglés puesto como nombre español** —el mismo
síntoma que tenía id 47 antes de fusionarla—: id 18 *Neon Fantasies*, id 30 *Birdcage
Qingming*, id 47 (ya borrada).

### 3. Las 42 armas de la referencia que no están en el catálogo

Daniel pidió agregarlas. **No se puede hacer offline con datos reales**: `weapons.nombre`
es `NOT NULL UNIQUE` y es el nombre **español in-game**, que no tengo de dónde sacar —
Prydwen, Fandom, gachabase y honeyhunter devolvieron 403/402, y Game8 solo publica la
lista en inglés. Meter el nombre inglés en la columna española sería reproducir
exactamente el defecto que esta auditoría acaba de limpiar.

Las dos vías reales:
- **capturarlas** cuando aparezcan en pantalla (es justo lo que va a hacer la extracción
  de RF-15), o
- una fuente en español que todavía no se encontró.

De las 42, además, 37 son armas que Daniel no posee.

---

## RNF-01

| | `_13` |
|---|---|
| Backup | `db/danibod_zzz_v2.backup_premig_20260728_170956.db` |
| Transacción | única (`BEGIN … COMMIT`) |
| `PRAGMA foreign_key_check` | sin errores |
| `PRAGMA integrity_check` | ok |
| Smoke checks | 5 en verde (total, borradas, sin huérfanas, sin `nombre_en` duplicado, ATK vs capturas) |

La migración se aplicó **tres veces desde el backup**, no de forma incremental: cada vez
que apareció un hallazgo nuevo (el ATK de Petrazufre, y después las otras 4 filas con ATK
ajeno) se restauró la copia y se volvió a correr el archivo completo. Así el `.sql` que
queda en `db/migrations/` es exactamente lo que se aplicó, sin parches encima.

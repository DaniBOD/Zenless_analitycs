# 2026-08-02 · IMPL RF-15 tramo 2 (a) — Desambiguar las pantallas de arma de las de disco

> **Qué se cierra:** las dos pantallas del flujo de W-Engines que se hacían pasar por pantallas de
> disco. El diálogo de reemplazo pasa a tener estado propio (**S29**) y el inventario de
> amplificadores deja de entrar por **S9**.
>
> **Alcance:** ruteo + display-only. Cero escrituras a la DB.

---

## 1. Lo que había

Corrido el detector actual sobre los 21 fixtures de `Engines_Triggers/` que nunca se habían
clasificado (los 4 folders fuera de `Engine_vista_detallada_pj`):

| fixture | caía en | conf | verificación |
|---|---|---|---|
| `Reemplazo_engine` (4) | **S23** — sustitución de disco | 0.999 | `txt=sustituir` (pasaba) |
| `Inventario_general_engines` (6) | **S9** — inventario de discos | 0.855–0.864 | **ninguna** |
| `Mejora_engine` (6) | S12 | — | — |
| `Refinar_engine` (5) | S12 | — | — |

El primero ya tenía consecuencia visible y estaba documentado como deuda del QA del 2026-07-30:
`parse_sustitucion` se abstiene —lo correcto, un arma no tiene slot— y el monitor volcaba un PNG a
`audit/s23_parse_fallo/` por cada reemplazo de arma. Ese volcado existe para investigar diálogos de
disco que *deberían* parsear, así que la basura además **disfrazaba los fallos reales**.

El segundo no lo sabíamos. Todavía no rompe nada porque el handler de S9 nunca se cableó — y ese
es justamente el motivo de cerrarlo ahora: el día que se cablee, el pipeline de **discos** estaría
parseando **armas**, sin que nada avise. Es la misma trampa de S17/S26 y S23/S25, esperando.

`Mejora_engine` y `Refinar_engine` caen en S12 (terreno limpio, sin colisión que desarmar).

---

## 2. Los discriminantes, medidos

### El diálogo: el sufijo de slot

Un disco vive en un slot y el juego lo imprime; un arma no.

```
disco → "Yixuan equipa actualmente Balada de la rama y la espada (2). ¿Deseas sustituirlo?"
arma  → "Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?"
```

Tesseract sobre la banda `_S23_TEXT_ROI`: **7/7 discos con `(N)`, 4/4 armas sin él.**

El patrón de ruteo (`_RE_S23_SLOT`) replica al de `parser_sustitucion` **a propósito**, incluidos
el `(` opcional y los alias de dígito de la variante laxa: si el parser va a poder sacar un slot de
ahí, el frame es de un disco y le pertenece a S23. Que el criterio de ruteo y el de parseo sean el
mismo es lo que evita que se abra un hueco entre los dos.

### El inventario: el título

```
discos → "Pistas de disco [339/3000]"
armas  → "Amplificadores [57/2000]"
```

**El ancla se fija con las lecturas crudas, no con la palabra ideal.** El primer intento ancló en
`plificador` y falló 2 de 6: el OCR nunca lee "Amplificadores" limpio y lo rompe de dos formas
distintas y estables — `Amoplificadores` (×4) y `Amolificadores` (×2). Ni el arranque ni la `p`
sobreviven. La cola **`lificador`** sí, en 6/6. Hay un test parametrizado con las tres lecturas
reales para que el próximo ajuste se haga contra lo que el OCR devuelve.

---

## 3. Cómo se contiene el riesgo de compartir template

Tres estados sobre `s23_sustitucion.png` (S23, S25, S29) y dos sobre la grilla del inventario. La
regla del repo ya estaba escrita y se aplica igual: **ante la duda gana el que hace algo.**

- `_verify_s29` **falla cerrado** sin OCR, como `_verify_s25`. De los diálogos, el único con
  consecuencias es S23 —mueve un disco entre PJs y escribe la DB—, así que en una máquina sin
  Tesseract S29 no existe y S23 queda exactamente como estaba.
- `_verify_s23` sigue **fallando abierto** sin OCR. Los dos comportamientos están fijados como
  test, uno frente al otro.
- Los dos verifies son **mutuamente excluyentes por construcción** (con slot / sin slot), así que
  el orden en `_STATE_TEMPLATES` es cinturón además de tirantes. S29 va último igual, por la misma
  convención: el primer turno de verificación le toca al que escribe la DB.
- `_verify_s9` **solo bloquea cuando ve positivamente** el título de armas. Con OCR ilegible deja
  pasar: S9 no tenía verificación ninguna hasta hoy, y esto es un blindaje contra una pantalla
  concreta, no una recalibración del estado.

### Exigirle el slot a `_verify_s23` no abre un modo de fallo nuevo

Es la objeción obvia y hay que responderla con el desenlace, no con la etiqueta:

| frame | antes | ahora |
|---|---|---|
| disco con `(N)` legible | S23 → parsea → swap | igual |
| disco con `(N)` arruinado por el OCR | S23 → **el parser se abstiene** → sin swap + PNG | S29 → sin swap, sin PNG |

En los dos casos el swap no ocurre. Cambia quién lo dice, no lo que pasa — y del lado nuevo
encima no ensucia `audit/`.

---

## 4. El estado nuevo

`S29 · "Diálogo de sustitución de W-Engine entre PJs"`. Umbral 0.85 (el de S23), cadencia 1000 ms,
`NON_CAPTURE_STATES`, transiciones desde/hacia S26/S12/S8/S9/S17.

**Rama propia en `_dispatch_state`, y no por prolijidad.** Sin ella el diálogo caería en el `else`,
que a conf ≥ `_DETAIL_RESET_MIN_CONF` **resetea el latch de identidad** — y el diálogo matchea
0.999. Habría borrado el PJ que estás mirando justo cuando volver a S26 lo necesita. Es la misma
razón por la que S23 tiene rama explícita; hay test de regresión para las dos.

`_process_s29_sustitucion_arma` es **display-only**: una línea por flanco, sin pending, sin toast
(ver el diálogo no prueba que se confirme) y sin volcado de diagnóstico — que el parser de discos
no lea esto es el diseño, no un fallo que investigar.

Lo que sí aporta: el texto trae **PJ + arma escritos por el juego**. Es dueño certero sin librería
de badges de por medio, igual que el botón *Desequipar* de S26. El día que el flujo de armas
escriba la DB, esta es la fuente del origen.

---

## 5. Un hallazgo lateral: `eguipa`

`parse_sustitucion_arma` falló en 2 de los 4 fixtures hasta que se midió qué leía Paddle:

```
Ejemplo_2 → 'Zhu Yuan eguipa actualmente Rotor de canon. Deseas sustituirlo?'
Ejemplo_3 → 'Billy Estelar eguipa actualmente Tránsito herciano. Deseas sustituirlo?'
```

Confusión q↔g, del mismo tipo acotado que el alias de dígito del slot. El ancla nueva es
`e[qg]uipa`.

> ⚠️ **`_RE_SUSTITUCION` (la del disco) tiene el mismo `equipa` rígido.** Hoy no falla porque los 7
> fixtures de disco salen limpios con Paddle, pero el modo de fallo es idéntico y ese camino
> **escribe la DB**: un `eguipa` en vivo sería un swap de disco perdido en silencio. No se tocó acá
> a propósito — aflojar el parser del swap de discos pide su propio QA (RNF-01/02). **Queda
> abierto.**

---

## 6. Verificación

`app/tests/unit/test_detector_desambiguacion_armas.py` — **57 passed**. Cubre: registro del estado,
los 4 diálogos de arma → S29, los 7 de disco → S23 (no-regresión del que escribe la DB), ambos
verifies rechazando al contrario, el fail-closed/fail-open enfrentados, los 6 inventarios de arma
fuera de S9, los de disco todavía en S9, y el corpus de negativos sin disparar S29.

Más los unitarios de regex y parser (`test_parser_sustitucion.py`) y las 4 regresiones del monitor
(`test_monitor_sustitucion.py`), incluida la del latch.

`test_armas_no_contaminan_discos.py` queda como estaba, con los docstrings actualizados: ahora es
**segunda línea**. Fija que los parsers de disco se abstengan aunque el ruteo falle, que es la
propiedad que de verdad protege la DB.

### Pendiente de QA en vivo

- Abrir el reemplazo de un arma y ver `[reemplazo arma] {arma} · {PJ} → {PJ}` en el log, con
  `audit/s23_parse_fallo/` **sin PNGs nuevos**.
- Entrar al inventario de amplificadores y confirmar que ya no dice S9.
- Un swap de disco real, de punta a punta, para la no-regresión de S23.

---

## 7. Lo que este hito NO hace

- **El inventario de amplificadores no tiene estado propio todavía.** Cae en S12, que es correcto
  y seguro. Darle estado y parser de tiles es el tramo siguiente, y es el que tiene el premio: una
  pasada de scroll expone las 57 armas (arte → nombre, franja → rareza, estrellas → refinamiento,
  badge → dueño), que es lo que cierra el desfasaje de `inventory_weapons` (50 filas de abril vs
  57 en la cuenta) y las 6 filas con `nombre_en IS NULL`.
- `Mejora_engine` y `Refinar_engine` siguen en S12.

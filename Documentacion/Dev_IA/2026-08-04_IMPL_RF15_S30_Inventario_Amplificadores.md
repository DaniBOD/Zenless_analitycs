# 2026-08-04 · IMPL RF-15 tramo 2 (b) — S30, el inventario de amplificadores

> **Qué se cierra:** el inventario de W-Engines pasa de "blindado" (caía a S12) a **estado propio
> con lectura**. El panel derecho da los seis campos del arma seleccionada.
>
> **Alcance:** display-only. Cero escrituras a la DB, cero toasts.

---

## 1. El parser no se escribió: se parametrizó

El primer instinto era escribir un parser nuevo. No hacía falta. Las dos pantallas que muestran un
arma —el detalle (S26) y el inventario (S30)— usan **las mismas secciones**: "Atributo principal",
"Atributos avanzados", "Efecto de amplificador". Es la misma gramática con otro marco.

Lo que efectivamente cambia son dos cosas, y las dos ya eran (o pasaron a ser) parámetros:

| | S26 (detalle) | S30 (inventario) |
|---|---|---|
| banda del panel | centro, `_S26_LAYOUT` | derecha, `_S9_LAYOUT` ← **ya existía**, del inventario de discos |
| OCR del crop | `_ocr_detail_lines` | `_ocr_s9_detail_lines` ← **ya existía** |
| badge de rareza | `pill.x1 − 64`, separado | `pill.x1 − 26`, pegado |
| fila de estrellas | caja **debajo** del pill | **a la derecha**, misma fila |

Con solo los dos primeros —que ya estaban escritos para discos— el panel salía casi entero:
**nombre, nivel/máximo, ATK base y stat avanzado, 6/6**. Fallaban rareza y refinamiento.

### Por qué fallaban: no era escala, era otra disposición

La tentación era asumir que el panel del inventario es "el mismo pero más chico" y escalar los
offsets. **Medido, es falso**: los pills miden 190×28 en S26 y 194×31 en S30 — prácticamente
idéntico. Lo que cambia es la disposición alrededor del pill, y eso ningún factor lo arregla.

```
S26   [A] Nivel 60/60   (avatar)          S30   [S] Nivel 60/60   ★★☆☆☆
      ★★★★★                                     Atributo principal
```

Por eso la geometría entra como `PillGeometry` explícita y no como un escalar. Medido sobre los 6
fixtures:

- **badge**: `dx = pill.x1 + [-28, -24]` ⇒ −26, centrado en el rango.
- **estrellas**: 5 blobs en 6/6, arrancando en `pill.x2 + [78, 80]`, espaciados ~38.7 px, el
  último termina cerca de `pill.x2 + 263`. Banda `+60..+290`: entra la fila entera con margen y no
  toca el borde del pill (que si no metería un 6º blob del propio texto del nivel).
- **hues**: `S = 21.0 · A = 155.0 · B = 98.0`. Los mismos exactos que en el detalle (`S = 22.0`),
  con la misma varianza cero — es color plano de UI. La tabla `_BADGE_HUE` se comparte tal cual.

`read_rareza` y `read_refinamiento` toman la geometría **con default `_S26_PILL`**, así que el
camino del detalle no cambia ni una línea. Hay un test que fija ese default: si se moviera, S26 se
rompería en silencio.

---

## 2. Resultado sobre los 6 fixtures

```
Engranaje infernal      | S | Nv 60/60 | P2 | ATK 684 | Impacto 18 %
Florescencia aurífera   | A | Nv 60/60 | P5 | ATK 594 | ATK% 25 %
Última cena             | A | Nv 60/60 | P5 | ATK 594 | Recarga de Energía 50 %
Llanto mielgo           | A | Nv 60/60 | P5 | ATK 594 | ATK% 25 %
Repercusión - Modelo II | B | Nv  0/10 | P1 | ATK  32 | Recarga de Energía 16 %
Caldero de la claridad  | A | Nv 60/60 | P5 | ATK 594 | HP% 25 %
```

**Seis campos, 6/6, y cero notas.** Incluida la corroboración cruzada: al máximo el ATK base
determina la rareza por sí solo (S ∈ {684,713,743}, A ∈ {594,624}, hallazgo de la auditoría del
catálogo) y en los 5 maxeados **coincide con el badge**. Ninguna `rareza_discrepa_atk`.

### La canonización no es un lujo acá

El OCR maltrata los nombres bastante más que en el detalle. Los crudos:

```
Uitimacena              → Última cena
Repercusión: Modeloll   → Repercusión - Modelo II
Llanto mielgo FFA       → Llanto mielgo
Calderodela claridad    → Caldero de la claridad
Florescencia aurifera   → Florescencia aurífera
```

**6/6 canonizados** contra `weapons` con `match_catalogo`. El caso `Modeloll → Modelo II` es el que
`_RE_TOKEN_ROMANO` ya cubría; sin esa normalización el candidato ganador era *Modelo II* leyendo
*Modelo III*, o sea dos armas distintas fundidas en una.

Y `Última cena` es una de las **6 filas con `nombre_en IS NULL`** — justo las que solo se cierran
capturándolas de la pantalla.

---

## 3. Estado y ruteo

`S30 · "Inventario general de amplificadores (W-Engines)"`. Umbral 0.80 (el de S9), cadencia
1500 ms, `NON_CAPTURE_STATES`, S9↔S30 como transición normal (las pestañas de la bolsa son vecinas).

**Reusa el template de S9 y va ANTES en `_STATE_TEMPLATES`**, por el mecanismo de S26/S17: ante
scores empatados el primer turno de verificación le toca al estricto. La asimetría es deliberada:

- `_verify_s30` **falla cerrado** — exige ver "Amplificadores".
- `_verify_s9` **deja pasar** si el título es ilegible.

Así el par tiene un fallback definido: con el título borroso el frame vuelve a S9, que es el
comportamiento de siempre, en vez de quedar en tierra de nadie. Al revés, S9 se comería todo frame
dudoso y S30 no llegaría a probarse nunca.

El ancla del título sigue siendo la cola `lificador`, por lo medido en el tramo anterior: el OCR
nunca lee "Amplificadores" limpio.

---

## 4. El handler, y en qué se diferencia de S26

`_process_s30_weapon_inventory`: gate por firma del panel (RNF-06 — el OCR cuesta ~500 ms y la
cadencia es 1500 ms), parseo, log + panel en vivo.

**Sin toast, a diferencia de S26.** Recorrer una grilla es lectura, no novedad: un toast por tile
sería exactamente lo que se vetó en el QA del 2026-07-31 (*"un toast avisa de CAMBIOS, no de
lecturas"*). En S26 abrir un arma sí emite, porque ahí el cambio observable es la tenencia.

Un arma que no canoniza se muestra **con el nombre crudo y marcada** `⚠ fuera del catálogo`. No se
da de alta sola: `weapons` tiene 42 armas de menos y completarla es una pasada aparte con su propio
criterio (RNF-01/02).

---

## 5. Un bug latente que apareció en el camino

`WeaponParsed.rareza` y `.refinamiento` **no estaban declarados en el dataclass**: se asignaban al
vuelo dentro del `if frame is not None and pill_bbox is not None`. Sin pill no existían, y
cualquier consumidor —`monitor.py:3981` arma la firma con `d.refinamiento`— reventaba con
`AttributeError` en vez de ver el `None` que promete el docstring del módulo.

Hoy no pasaba **de casualidad**: el gate del handler exige `nivel`, que sale del mismo pill. Al
reusar el parser en otro panel esa casualidad deja de valer. Declarados con default `None`, y con
test.

---

## 6. Verificación

| suite | resultado |
|---|---|
| `test_parser_weapon_s30.py` | 14 passed |
| `test_monitor_weapon_s30.py` | 10 passed |
| `test_detector_desambiguacion_armas.py` | ver commit |

Los tests del monitor fijan los dos contratos que separan S30 de S26: **no emite toast nunca** y
**no escribe la DB**. Y los dos flancos del trabe: que un panel ilegible lo declare, y que al
recuperarse lo diga (si solo se anotara el trabe, un handler que se recupera dejaría al usuario
creyendo que sigue roto).

### Pendiente de QA en vivo

- Entrar al inventario de amplificadores → `[S30] Inventario W-Engine — ...` con los seis campos.
- Moverse por la grilla → una línea por arma, **ningún toast**.
- Quedarse quieto → **sin líneas nuevas** (el gate de firma).
- Volver a la pestaña de discos → S9, con su comportamiento de siempre.

---

## 7. Lo que este hito NO hace

- **No lee el DUEÑO.** En este panel el avatar está arriba, junto al nombre, no al lado del pill
  como en S26, así que `read_weapon_owner_badge` no aplica sin recalibrar. Es el mismo trabajo de
  medición que se hizo acá para el badge de rareza.
- **No lee los TILES de la grilla**, que es el premio grande: cada tile trae arte (→ nombre vía
  `engine_refs`, ya probado ~90 % en el gacha), franja de rareza, fila de estrellas, nivel y badge
  de dueño. Una pasada de scroll expondría las **57** armas de una, contra las 50 filas de abril
  que hay en `inventory_weapons`. Hoy el panel da un arma por selección.
- **No escribe nada.** El sync va atado al censo, como se acordó para discos.

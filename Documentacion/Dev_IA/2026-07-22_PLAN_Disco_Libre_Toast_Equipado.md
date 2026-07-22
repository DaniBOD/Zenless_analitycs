# PLAN — Disco libre equipado → toast EQUIPADO (S6/S7)

**Fecha:** 2026-07-22
**Estado:** 📋 PLANIFICADO — sin implementar.
**Hermano de:** [Reemplazo de disco S23](./2026-07-19_IMPL_Reemplazo_Disco_S23.md) (cerrado 2026-07-20)
**Relacionado:** [SPEC Invariante equipado/asignado](./2026-07-22_SPEC_Invariante_Equipado_Asignado.md)

---

## 1. Qué se quiere

Detectar que el usuario **equipó un disco libre** a un PJ, y avisarlo con un toast **EQUIPADO**.

Daniel marcó una distinción que el diseño debe respetar:

> "el resalto del toast equipado que es diferente a 'equipar' la cual es una sugerencia"

| | **EQUIPAR** (ya existe) | **EQUIPADO** (nuevo) |
|---|---|---|
| qué es | recomendación del sistema | observación de lo que pasó |
| tiempo | futuro — *deberías* | pasado — *lo hiciste* |
| score / countdown | sí | no |
| familia | recomendaciones | confirmaciones pasivas (con REEMPLAZADO) |

---

## 2. La pantalla y las dos señales

**Pantalla: S6/S7** — vista individual del disco. Layout: grilla de discos a la izquierda, panel de
detalle al centro, hexágono del PJ a la derecha. Ya está detectada y parseada (parser 2 columnas
validado en vivo 2026-07-18).

Los folders `04_Inventario_Disco_Vista_Individual` y `17_..._libres` son **la misma pantalla** con el
disco en estados distintos.

### Señal A — badge junto al pill de nivel (idea de Daniel)

> "en uno libre no hay badge a la derecha del nombre del slot (no en la grilla aclaro) luego si se
> equipa aparece el badge del pj en el disco"

Verificado sobre capturas reales. El badge **no** está a la derecha del título sino **a la derecha
del pill "Nivel X/15"**, una línea más abajo:

| captura | disco | fila del nivel |
|---|---|---|
| `17/Ejemplo_2_(equipar)` | Floración del alba (1) | `Nivel 15/15` → *vacío* |
| `17/Ejemplo_1_(reemplazar)` | Melodía de Faetón (1) | `Nivel 15/15` → *vacío* |
| `04/Ejemplo_1` | Jazz caótico (1) | `Nivel 15/15` → **avatar de la dueña** |

**Ya implementado y reusable:** `crop_s17_assigned_avatar` ([`parser_disc_s17.py:614`](../../app/core/parser_disc_s17.py))
se ancla al pill vía OCR, recorta el círculo a su derecha y **devuelve `None` si no hay avatar**
(`_has_avatar_content`, densidad de bordes Canny — robusto, no depende de saturación).

⚠️ **Pero hoy nadie lo llama en S6/S7**: el monitor no hace detección de dueño en esa pantalla
(0 hits de badge/owner para S6/S7).

### Señal B — el botón de acción (hallazgo de esta sesión)

El botón inferior derecho cambia según el contexto. **Corrección de Daniel:** no habla del disco,
habla del **slot destino**:

| botón | significado |
|---|---|
| **Equipar** | disco libre → el PJ tiene ese slot **vacío** |
| **Reemplazar** | disco libre → el PJ ya tiene un disco ahí → **habrá un desplazado** |
| **Desequipar** | el disco ya lo lleva puesto este PJ |

⚠️ **Hoy el texto del botón se descarta a propósito** — `parser_disc_s17.py:763` lo filtra como
basura de OCR del panel.

---

## 3. El diseño: las dos señales se guardan mutuamente

Esto es lo que hace al feature sólido, y es la razón para no conformarse con una sola señal.

**Debilidad de A sola:** LIBRE es la lectura más frágil del sistema de badges. El 2026-07-19 hubo que
cambiar la regla a *"presencia gana a LIBRE"* justamente porque la cara de Jane se leía como texto y
producía falsos LIBRE. Un falso LIBRE acá dispararía un toast fantasma.

**Debilidad de B sola:** el botón dice *qué va a pasar*, pero **no dice quién es el dueño**.

**Juntas:** "Equipar"/"Reemplazar" solo aparecen en discos libres → confirman la ausencia de badge
por una vía independiente (texto OCR de posición fija, mucho más confiable que el clasificador
cara-vs-texto). Y el badge, cuando aparece, nombra al dueño.

### La transición que dispara el toast

```
ANTES:    badge AUSENTE  ∧  botón ∈ {Equipar, Reemplazar}
DESPUÉS:  badge PRESENTE (= latch)  ∧  botón = Desequipar
```

**Las dos señales voltean juntas.** Exigir ambas hace el falso positivo muy improbable: haría falta
que el badge y el OCR del botón fallaran a la vez y de forma coherente.

### Estructura: mismo esqueleto que el reemplazo

El check del S23 ya resolvió esta forma y **conviene reusarla, no duplicarla**:

| | reemplazo (cerrado) | disco libre (nuevo) |
|---|---|---|
| arma el pendiente | diálogo S23 | ver el disco libre en S6/S7 |
| origen | PJ que lo tenía | **LIBRE** |
| destino | latch (PJ en pantalla) | latch |
| confirma | badge = destino | badge = destino **+ botón Desequipar** |
| toast | REEMPLAZADO | **EQUIPADO** |

Es la misma frase: *un disco cuyo dueño pasó de \<lo que vi antes\> a \<el PJ que estoy mirando\>*.
Solo cambia que "lo que vi antes" es LIBRE en vez de un nombre.

**Propuesta:** generalizar `_pending_swap` → pendiente con `origin` que admite `LIBRE`, y que
`_check_swap_owner` decida qué toast emitir según el origen. Un solo camino, dos desenlaces.

### Diferencia deliberada: la vida del pendiente

En el S23 decidimos que el pendiente **vive hasta consumirse** — lo justifica el compromiso explícito
del diálogo.

Acá **no hay compromiso**: ver un disco libre no significa que lo vayas a equipar. Por eso:

- **El pendiente libre muere cuando cambia el latch de PJ.** Un disco libre se equipa al PJ que
  estás mirando, en la misma visita.
- **Identidad completa** (set, slot, nivel, main, {substat+rolls}), no solo set+slot.

Sin esto hay un falso positivo concreto: mirás un Jazz Caótico slot 1 libre, **no lo equipás**, y más
tarde entrás a un PJ que ya tiene un Jazz Caótico slot 1 puesto → "antes LIBRE, ahora ese PJ" →
toast fantasma. Con S23 casi no pasa (el origen es un PJ específico); con LIBRE el origen no
identifica nada.

---

## 4. Regalo para el invariante

El botón resuelve gratis algo que la SPEC del invariante necesitaba: **"Reemplazar" avisa por
adelantado que va a haber un disco desplazado**, y "Equipar" avisa que no.

Es el discriminador exacto de la R2 (*el desplazado pierde `equipado` Y `agente_asignado`*),
**observado en pantalla** en vez de deducido de la DB. Cuando se implemente el invariante, esta
señal ya va a estar disponible.

---

## 5. La pregunta empírica que hay que resolver primero

**¿Qué pasa en pantalla justo después de apretar Equipar / Reemplazar?**

De la respuesta depende dónde se observa el "DESPUÉS":

| escenario | consecuencia |
|---|---|
| se queda en S6/S7 y el panel se refresca | ideal — la transición se ve en la misma pantalla, sin reset |
| hay animación / vuelve a la grilla / va a S8 | el pendiente tiene que sobrevivir al cambio de estado, y el "después" se observa al volver a abrir el disco |
| aparece un popup de confirmación | ese popup es un estado nuevo a capturar (como S23 para el reemplazo) |

**Hoy no lo sabemos.** No hay capturas del momento posterior. Es la primera tarea, y es de Daniel:
una sesión corta de capturas del "después".

⚠️ Ojo con el acumulador de votos: se resetea por cambio de disco/firma
(`_reset_s17_disc_tracking`). El estado "antes = LIBRE" **debe vivir en el pendiente**, no en el
acumulador, o se pierde en la transición.

---

## 6. El toast EQUIPADO

**Variante nueva en `tokens.py::VARIANTS`.** Hoy existen `equipar` (POSITIVE), `mejorar` (INFO),
`reserva` (YELLOW), `descartar` (WARNING), `lategame`, `reemplazado` (PURPLE).

**Problema:** en un toast de 380×116, *"EQUIPAR"* y *"EQUIPADO"* se diferencian por dos letras. Es
mal lugar para apoyar toda la distinción.

**Recomendación:** que la diferencia **no dependa de la palabra**.
- **Color PURPLE**, igual que REEMPLAZADO. Lo que agrupa a esos dos no es el verbo sino que **ya
  ocurrieron**. Púrpura pasa a significar "esto pasó"; los colores de recomendación quedan solo para
  consejos.
- **Sin score ni countdown**, como REEMPLAZADO (`show_replacement`).
- Entre EQUIPADO y REEMPLAZADO no hay riesgo de confusión: el body de REEMPLAZADO es
  origen→disco→destino; el de EQUIPADO sería disco→destino (un solo PJ, sin origen), tal como lo
  pidió Daniel.

**Nota:** el campo `icon` de `VARIANTS` **no se renderiza** (no hay ninguna referencia a `icon` en
`toast.py`). Solo `label` y `color` tienen efecto. No perder tiempo eligiendo ícono.

**Decisión abierta:** ¿la etiqueta es `EQUIPADO`, o algo sin ambigüedad de dos letras
(p.ej. `EQUIPASTE`)? Es de Daniel.

---

## 7. Fases

| # | Fase | Entregable | Bloquea a |
|---|---|---|---|
| **0** | **Capturas del "después"** (Daniel) | screenshots del instante posterior a Equipar/Reemplazar → nueva carpeta de triggers | todo |
| **1** | **Badge de dueño en S6/S7** | llamar `crop_s17_assigned_avatar` en el handler de S6/S7 + `BadgeSurface` + votación | 2 |
| **2** | **OCR del botón de acción** | leer Equipar/Reemplazar/Desequipar (dejar de filtrarlo) + exponerlo en el parseo | 3 |
| **3** | **Pendiente + check generalizados** | `origin` admite LIBRE; muerte por cambio de latch; identidad completa | 4 |
| **4** | **Toast EQUIPADO** | variante + body de un solo PJ + payload en el controller | — |
| **5** | **QA en vivo READ-ONLY** | los 3 desenlaces (equipar a slot vacío / a slot ocupado / cancelar) | — |

**Fase 0 primero y es de Daniel.** Sin saber qué pasa después del click, la fase 3 se diseña a
ciegas.

Fases 1 y 2 son independientes entre sí y se pueden hacer en cualquier orden.

---

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Falso LIBRE** del badge | señal B (botón) como confirmación independiente |
| **Falso positivo por disco gemelo** | identidad completa + muerte del pendiente al cambiar de latch |
| **La transición no se ve** (cambio de pantalla) | fase 0 lo responde; el pendiente sobrevive al reset del acumulador |
| **OCR del botón poco fiable** | posición fija + 3 valores conocidos → match por prefijo, no exacto |
| **RNF-06** | ambas señales ya son baratas: el crop está anclado a líneas de OCR que ya se computan |

---

## 9. Fuera de alcance

- **Desequipar** (dejar un slot vacío). Es la transición inversa y toca la R2 del invariante. Se
  puede sumar después reusando todo esto.
- **La escritura a la DB.** Igual que el reemplazo, este feature es **observacional** y debe salir en
  read-only. La persistencia va desacoplada y después.

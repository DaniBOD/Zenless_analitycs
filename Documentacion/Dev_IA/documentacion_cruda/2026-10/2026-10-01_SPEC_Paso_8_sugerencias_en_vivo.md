# SPEC · Paso 8: las sugerencias del motor en vivo (2026-10-01)

**Estado:** diseño aprobado por Daniel el 2026-10-01, por partes ("si me cierra", dos veces).

## Qué pidió Daniel

El paso 8 del plan de la Fase A (`~/.claude/plans/dale-rangos-en-la-streamed-hopcroft.md`):

> Hoy `recomendar()` corre sólo del lado que persiste. Pasa a calcularse en los dos modos, y
> persiste sólo si no es readonly. Toast sólo si hay un movimiento que mejora a algún PJ ("toasts
> avisan cambios, no lecturas").

> "Sigamos con el paso 8." (2026-10-01)

## Lo que hay hoy (leído en el código, 2026-10-01)

- **Drops (S3/S6/S7):** `MonitorController._build_payload` llama a `recomendar()` **sin** el
  contexto del motor de Discos. Le faltan los builds declarados, los libres, el inventario de R22 y
  la prioridad. **Todo drop saca un toast** con ese resultado, más un SCORE, una barra de URGENCIA
  y un umbral `thr` que salen del scoring sin calibrar. La card en vivo lo ignora a propósito.
- **Inventario (S9/S17):** se persiste y se muestra la card. No se calcula ninguna sugerencia.
- **La pantalla Discos** usa `sugerencias.generar`: el motor completo (R9-R24, mejora mínima 0,1,
  R22, prioridades) sobre todo el inventario, más `resolver_conflictos`.

## Decisiones

| pregunta | decisión |
|---|---|
| qué pasa por el motor en vivo | **drops (S3/S6/S7) e inventario (S9/S17)** |
| qué saca toast | **discos nuevos (S3, S5, S22) y el "Ver" (S6/S7)**, sólo si la sugerencia es **EQUIPAR o MEJORAR** (corrección de la tabla: ver abajo) |
| un drop que no mejora a nadie (reserva, guardar, descartar) | **sin toast**: card y log |
| lo del inventario | **sin toast** aunque mejore (mirar no es un cambio; una pasada de censo darían ~40) |
| dónde se ve la sugerencia | **una línea en la card y el detalle en la región derecha** |

### Corrección (2026-10-01, al implementar)

El diseño llamó "drops (S3/S6/S7)" a lo que pasa por `_build_payload`, y S6/S7 **no es un drop**:
es la pantalla "Ver" de un disco, a la que se llega desde la tienda, las baterías o el
inventario. Al camino del toast llegan **S3** (drop de desafío), **S5** (afinación), **S22**
(baterías, "Obtenido") y **S6/S7** (el "Ver").

Daniel eligió **"Nuevos + Ver"**: el "Ver" es abrir UN disco a propósito, no inunda como el censo,
y es lo que pidió en la QA del 18/07.

Además:
- los eventos (S3/S5/S22) se evalúan como disco nuevo;
- las observaciones (S6/S7/S9/S17) se resuelven a su fila real por identidad, para que el disco no
  quede gemelo de sí mismo y R22 dé lo mismo que en Discos.

## Medido antes de diseñar (2026-10-01, DB real en sólo lectura, con la suite corriendo en paralelo)

`recomendar` de un disco con el contexto completo:
- **57 ms** (máx. 72) armando el contexto de cero;
- **23 ms** (máx. 40) con el contexto armado.

Entra en los 500 ms del toast (RNF-06): se calcula sincrónico, sin hilo aparte.

## Parte 1 · El cálculo, el flujo y el toast

- **Una sola autoridad** (`app/core/sugerencias.py`):
  - el contexto del motor (PJs, builds por PJ, libres, `ScoringContext`, prioridades) sale de
    `generar` a **`contexto_motor(con)`**, y lo usan la pantalla Discos y el vivo;
  - **`sugerir_un_disco(con, disco) -> SugerenciaDisco`** arma la sugerencia de ese disco con las
    mismas reglas que `generar` y en la misma forma de datos, así que el texto (`texto_sugerencia`)
    y el detalle (`detalle_sugerencia`) se reusan;
  - un drop en sólo lectura no está en la DB y se evalúa igual.
- **Diferencia honesta con Discos:** en vivo se evalúa un disco solo, sin cruzarlo con las otras
  sugerencias (los "en conflicto" de la tabla). Dice la mejora frente a lo que el PJ lleva hoy.
  Cruzarlo todo es correr el inventario entero (0,75 s) por disco.
- **Cuándo** (`app/ui/controller.py`): drops e inventario, **después de persistir** y **en los dos
  modos** (calcular no escribe). Sincrónico.
- **Toast:** sólo un drop EQUIPAR o MEJORAR.
  - Salen el SCORE, la barra de URGENCIA y el umbral sin calibrar.
  - Entra la **mejora real** ("MEJORA +0,57") con el PJ destino.
- **Log:** una línea por disco, `[sugerencia] #412 → EQUIPAR Anby +0,57 (vs #301)`.

## Parte 2 · La card, la región derecha, los errores y las pruebas

- **Card en vivo** (`app/ui/live/item_card.py`): debajo del disco, la etiqueta de la sugerencia con
  el color y el texto de la columna de Discos (`texto_sugerencia`, `tokens.SUGERENCIA`). Sin
  sugerencia (equipado y bien donde está): "Nada que hacer".
- **Región derecha** (`region_derecha`, hoy vacía): un recuadro "Sugerencia del motor" con
  `detalle_sugerencia` (la misma función que el modal del disco).
  - **equipar / mejorar:** qué disco lleva hoy ese PJ en el slot;
  - **mover:** de quién sale, quién lo repone y a quién va;
  - **reserva / guardar / descartar:** el porqué.

  Se reemplaza con cada disco nuevo, y el contenedor sigue siendo sustituible.
- **Errores:** si el cálculo falla, va al log con el traceback, la card dice "sin sugerencia: falló
  el cálculo (ver log)" y no sale toast. Ni la persistencia ni el censo dependen de la sugerencia:
  va en su propio try (A2: que la falla se vea).
- **Pruebas:**
  - **Una sola autoridad:** sobre una copia, `sugerir_un_disco` da lo mismo que `generar` antes de
    `resolver_conflictos`, disco por disco, para todo el inventario.
  - **Toast:** sale para un drop EQUIPAR o MEJORAR. No sale para reserva, guardar o descartar, ni
    para nada de S9/S17, ni si el cálculo falla. Igual en sólo lectura y en modo normal.
  - **Card y región derecha:** un test por estado.
  - Un sabotaje por regla; sha256 de la DB igual antes y después.
- **En vivo:**
  - una pasada de censo en S9 en sólo lectura con métricas: **0 toasts**, y la latencia click→log
    sin regresión contra la línea de base de **1203 ms** [1172–1234]
    (`project_latencia_log_censo_s9`);
  - un par de drops reales farmeando.

## Fuera de alcance

- Cruzar la sugerencia en vivo con las demás (conflictos).
- Sugerencias para W-Engines (RF-14).
- Rehacer el diseño visual del toast más allá de cambiar el puntaje por la mejora
  (`project_deuda_ui_toasts`).

# SPEC · Dedup por contenido en la cosecha de badges (+ limpieza de los clones existentes)

> **Fecha:** 2026-08-11
> **Estado:** diseño aprobado, pendiente de plan de implementación
> **Alcance:** las tres superficies de badge. Cero escrituras a la DB. Cambia las librerías de
> avatares y los snapshots versionados de `audit/`.

---

## 1. El problema, medido

Contar referencias no era medir cobertura. Medición del 2026-08-11 sobre las tres librerías del
runtime, con umbral de clon 0.03:

| superficie | refs | **distintas** | PJs con **una sola imagen** |
|---|---|---|---|
| `row` | 365 | **62 (17%)** | **40 de 50** |
| `detail` | 193 | **85 (44%)** | 22 de 50 |
| `grid` | 486 | 392 (81%) | 6 de 56 |

Alice, Jane, Miyabi, Nangong Yu, Zhao, Zhu Yuan, Ye Shunguang y 15 más muestran **cuatro
referencias que son la misma imagen repetida**. Pyrois tiene siete idénticas.

## 2. Por qué nadie lo vio: el leave-one-out se infla

El leave-one-out saca una ref y la busca contra el resto — **pero si su gemela idéntica sigue
adentro, matchea a 0.000 y cuenta como acierto perfecto**. No mide discriminación: mide "¿quedó una
copia mía?".

Medido con `tools/measure_badge_lib.py` sobre `detail`, guard 0.80:

| librería | top-1 | abstención |
|---|---|---|
| tal cual (193 refs) | **91.2%** | 8.3% |
| dedupeada (85 refs) | **42.4%** | 54.1% |

Y el dedupeado **coincide con el campo**: el QA del inventario S30 dio 5/11 = 45% de naming. El
número de laboratorio era el que mentía, durante semanas.

Es el **segundo** punto ciego del leave-one-out. El primero —una librería con solo semilla `-ico`—
se documentó el 2026-08-02 y se detecta con `--against-labeled`. Este no lo detecta ninguno de los
dos: hace falta contar refs **distintas**.

## 3. La causa

`learn_s17_detail` se llama **una vez por cada disco** del PJ (flujo-ancla de S17), pero el avatar
del panel de detalle **no cambia según el disco seleccionado**. Seis discos ⇒ seis copias del mismo
recorte. Lo mismo el `row`: la barra superior tampoco cambia al moverse entre discos.

El `grid` se salva porque ahí el tile **sí** cambia con cada disco — de ahí su 81%.

Y hay un agravante: `add_reference` desaloja **FIFO** al llegar a `_MAX_REFS_PER_NAME = 10`. Una
clase que se llena de clones **expulsa refs diversas** para meter más copias de lo mismo.

## 4. Diseño

### 4.1 El dedup va en `BadgeSurface.learn`

Es el cuello único: los tres caminos (`row`, `grid`, `detail`) entran por ahí y no hay otro. Antes
de `add_reference`, si el descriptor del crop está a ≤ `_CLON_MAX_DIST` (0.03) de alguna ref que ese
PJ ya tiene, **no se aprende** y `learn` devuelve `False`.

El umbral ya está medido y en uso: refs genuinas del mismo PJ están a **0.098-0.229**; un clon, a
**0.000**. Queda holgado por debajo del piso genuino.

Se aplica a las tres superficies aunque el `grid` casi no lo necesite: es el mismo cuello, y una
pantalla nueva que registre su superficie (S9, S23) queda cubierta sin que nadie tenga que
acordarse. `AgentIdentifier.detail_is_near_duplicate` —que hoy usa la cosecha de armas— pasa a
apoyarse en la misma primitiva para no tener dos implementaciones del mismo criterio.

### 4.2 Lo que NO toca

- **La semilla `-ico` no pasa por `learn`**: escribe directo en `_refs`. El dedup no la afecta.
- **La DB**, en ningún momento.
- **Los guards de naming ni los umbrales del matcher.**

### 4.3 Efecto secundario que se gana

`BadgeSurface.learn` llama a `save()` en **cada** cosecha, o sea reescribe el `.npz` entero — el del
`row` pesa 23 MB. Hoy cada clon dispara esa reescritura para no agregar nada. Con el dedup, esas
escrituras desaparecen (RNF-06).

### 4.4 Un caller que hay que ajustar

`_maybe_harvest_detail_despite_veto` (rescate del detalle) loguea *"pasó los 3 checks pero la
librería NO aceptó la ref"* cuando `learn` devuelve `False`. Con el dedup ese mensaje va a aparecer
para clones, donde es engañoso: no es que la librería falló, es que ya tenía esa imagen. Necesita
distinguir los dos casos.

## 5. Limpieza de los clones existentes

Cortar la fuente no alcanza: las ranuras ya están ocupadas y el techo de 10 sigue bloqueando cosecha
real.

- **Herramienta nueva** `tools/dedup_badge_lib.py`, que lee un `.npz`, colapsa los clones por
  contenido y escribe uno nuevo. **Read-only sobre su entrada** y con un `--dry-run` que solo
  reporta — la lección de que un audit no muta su objeto de estudio.
- Se corre sobre **las tres librerías del runtime**.
- Para los snapshots versionados: **no se reescribe ninguno**. Se generan snapshots NUEVOS con
  fecha, se apunta `_BASELINES` a ellos, y los viejos quedan como historia. Es la convención que ya
  siguieron los commits de julio y agosto, y evita que un `git log` mienta sobre lo que había.
- El reporte de la corrida va a `audit/`.

## 6. Tests

| caso | esperado |
|---|---|
| aprender dos veces el mismo crop | la segunda no entra |
| aprender un crop distinto del mismo PJ | entra |
| dos PJs con crops parecidos entre sí | no se afectan (el dedup es **dentro** de la clase) |
| clon rechazado | **no** dispara `save()` |
| la semilla `-ico` | sigue sembrando igual |
| las tres superficies | todas dedupean (test parametrizado) |
| `dedup_badge_lib --dry-run` | no modifica el archivo (sha256 antes/después) |
| `dedup_badge_lib` | el resultado no tiene pares ≤ 0.03 y no pierde ninguna clase |

## 7. Verificación y criterio de éxito

1. Refs **distintas** por superficie antes/después de la limpieza; ninguna clase desaparece.
2. Ningún par a distancia ≤ 0.03 en las librerías limpias.
3. Suite completa verde (línea base **2048 passed · 11 skipped**).
4. QA en vivo: cosechar dos veces el mismo PJ desde discos distintos ⇒ **una sola** ref nueva.

**Aviso importante para no asustarse:** después de la limpieza el leave-one-out **va a bajar mucho**
—de ~91% a ~42% en `detail`, y bastante más en `row`—. Eso **no es una regresión**: es el número
verdadero saliendo a la superficie. El indicador de salud pasa a ser *refs distintas* y el
`--against-labeled`, no el leave-one-out sobre una librería inflada.

## 8. Riesgos

- **La cobertura real va a verse mucho peor de lo que creíamos.** 40 de 50 PJs del `row` con una
  sola imagen es el estado actual, no algo que rompa este cambio. Conviene saberlo antes de decidir
  cuánto invertir en re-cosecha.
- **Costo por cosecha**: una comparación de descriptores contra ≤10 refs de la clase. Es
  despreciable frente al `save()` de 23 MB que el mismo cambio evita.
- **Un PJ cuyo recorte sea siempre idéntico se queda en 1 ref.** Es honesto: cuatro copias nunca
  valieron más que una. Lo que cambia es que ahora el contador lo dice.

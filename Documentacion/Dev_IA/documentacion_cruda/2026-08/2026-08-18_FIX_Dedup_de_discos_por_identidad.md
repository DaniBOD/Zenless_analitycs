# La firma que no distinguía discos: distinguía casilleros

> **2026-08-18** · `app/db/repositories.py`, `app/core/sync_equip.py`
> Encontrado mientras se preparaba el re-censo de discos. **No** es el bloqueante del censo —
> ver §4, que corrige el diagnóstico inicial.

---

## 1. El hallazgo

`find_by_hash` deduplica discos por `(set_id, slot, main_stat, main_valor)`. Parece razonable hasta
que se mira qué son los slots 1, 2 y 3: **su main stat es fijo** — PV, ATK y DEF planos. A un mismo
nivel, todos los discos de un set en esos slots comparten los cuatro campos.

Medido sobre el inventario real de 367 discos (snapshot `pre_censo_20260817`):

| clave de dedup | filas que sobreviven |
|---|--:|
| `(set, slot, main, main_valor)` — la que estaba | **177** |
| + nivel | 177 *(no aporta: `main_valor` ya es función del nivel)* |
| + nivel + `{substat, rolls}` — identidad completa | **345** |

**190 discos, el 51,8 %.** El grupo peor: 10 discos de Monarca del Pináculo slot 3, DEF 184,
colapsando en un solo registro. El efecto no era perder un insert: era que un disco farmeado nuevo
**pisara** los stats de uno viejo que no tenía nada que ver.

Los 22 pares que ni la identidad completa separa son ambigüedad irreducible —dos discos realmente
idénticos—, y ahí no se adivina: se avisa.

## 2. El arreglo ya estaba escrito, en otra capa

Dos piezas del repo ya tenían la definición correcta:

- `row_matches_parsed_identity` — `(set, slot, nivel, main, {substat normalizado + rolls})`.
  Incluye **rolls** (enteros limpios) y omite **valores** (ruidosos por OCR).
- `monitor._disc_identity` — la misma idea, con este comentario de junio 2026:
  *"en slot 1 el main es siempre HP → dos discos distintos del MISMO set en slot 1 colapsaban a la
  misma identidad y el segundo NUNCA se emitía"*.

O sea: **el mismo bug se había diagnosticado y arreglado hace dos meses, en la capa de emisión.** Se
arregló donde se veía —el log no mostraba el segundo disco— y no donde se escribe.

`find_all_by_identity` (nuevo, en `InventoryDiscRepo`) reusa `row_matches_parsed_identity` y
devuelve **una lista**, no un `Disc`. La diferencia es el punto: `≥2` significa ambigüedad real, y
el caller tiene que poder avisarla en vez de quedarse callado con el primero que salga.

## 3. Lo que fijan los tests

Seis, y tres de ellos existen para que el arreglo no se pase de rosca en la otra dirección:

| test | qué protege |
|---|---|
| dos discos del mismo set/slot no colapsan | el bug de los 190 |
| el mismo disco visto dos veces sigue siendo uno | precisión sin duplicados |
| mismos substats, distintos rolls → distintos | los rolls discriminan |
| **valores ruidosos del OCR no parten un disco en dos** | por qué los valores quedan FUERA |
| un disco mejorado no se duplica por subir de nivel | el nivel sí entra |
| los gemelos irreducibles se avisan, no se adivinan | RNF-02 |

El cuarto es el contrapeso: si los valores entraran a la identidad, cada relectura (38.0 / 38.4 del
mismo substat) sería un disco nuevo y el censo contaría **de más**. Precisión y tolerancia al ruido
tiran en direcciones opuestas; los rolls son el punto donde se cruzan.

## 4. ⚠️ Corrección: esto NO era el bloqueante del censo

El diagnóstico inicial fue que el censo perdería la mitad del inventario. **Es incorrecto**, y vale
dejarlo escrito porque el error es instructivo: se midió la colisión sin verificar **qué camino usa
la pantalla del censo**.

Hay dos caminos de persistencia, y S9 usa el otro:

| camino | clave | quién lo usa |
|---|---|---|
| `on_disc_detected` | ~~`find_by_hash`~~ → identidad completa | drops S3, S6/S7 |
| `persist_s17_disc` | `find_equipped_by_agent_slot(PJ, slot)` | **S17 y S9** |

La clave `(PJ, slot)` es **natural** —un PJ tiene un disco por slot— y no colisiona entre PJs. Los
292 discos equipados nunca estuvieron en riesgo.

**El bloqueante real del censo es otro:**

```python
if agente_id is None:
    return None      # no se persiste NADA
```

`persist_s17_disc` exige dueño confiable, y el comentario del controller lo dice sin vueltas: *"los
LIBRES (sin dueño) no se persisten aún"*. En el snapshot son **72 discos libres** de 367 — el 20 %
del inventario que una pasada del S9 vería y descartaría.

Y hay una segunda capa debajo: **hoy no existe señal de "libre"**. `_assign_s9_owner` documenta que
*"un disco libre da badge None"*, pero `badge=None` también significa "no localicé el tile". Son
indistinguibles — el mismo problema que RF-15 resolvió para las armas por **nitidez**, no por
coordenadas.

Así que el arreglo de esta nota **sirve igual y hace falta igual** —es la clave que el camino de
discos libres va a necesitar, porque ahí no hay `(PJ, slot)` que usar— pero el censo necesita
además: (a) distinguir libre de no-sé, y (b) un camino de persistencia sin dueño.

## 5. La lección

Medir la colisión fue correcto; atribuirla al camino equivocado, no. **Un número real puede
sostener una conclusión falsa si no se verificó qué código lo consume.** El mismo error, en otra
escala, que arreglar `_disc_identity` en la emisión y dejar la escritura como estaba.

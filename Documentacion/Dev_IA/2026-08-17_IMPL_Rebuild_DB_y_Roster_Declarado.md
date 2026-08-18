# La DB reconstruida desde cero + el roster declarado · 2026-08-17

> Continúa [2026-08-17_QA_Censo_Roster_y_el_problema_de_los_grises.md](./2026-08-17_QA_Censo_Roster_y_el_problema_de_los_grises.md),
> que dejó los dos defectos que motivan esto.
>
> Dos entregables: la DB de cuenta reconstruida (`app/scripts/rebuild_account_db.py`) y la
> declaración manual del roster (módulo + diálogo + migración 20).

---

## 1. Por qué el roster pasa a ser declarado

El censo por observación funciona para lo que se posee (49/51 en 18 min). Para lo que **no**, falla
de dos maneras medidas:

- de 6 personajes no obtenidos, **solo 1 dejó registro**;
- **4 de 6 matchean a un PJ propio** por encima del umbral (`Norma→Nekomata 0.615`,
  `Lichter→Alice 0.667`), así que pararse sobre un gris le dice al sistema que estás en otro.

No contradice RNF-02. La doctrina es *no inventar*, no *no preguntar*: declarar ~55 casillas que el
usuario sabe de memoria no es transcribir 367 discos con substats. Y da el **denominador**, que la
observación no puede dar por más que recorra — el sistema no sabe cuántos personajes existen.

---

## 2. El rebuild, y el límite que lo define

Daniel pidió "una DB nueva, clonar el modelo relacional pero sin los datos, y la actual queda de
respaldo". Tomado al pie de la letra eso tiraba **516 filas que ningún censo devuelve**:
`agent_thresholds`, `agent_score_thresholds`, `agent_substat_preferences` y `pj_weapon_synergy`
tienen `fuente='Prydwen'` o `'manual'`. Son cosas como *"AP ≥300: Afterburn +30%, cap duro"*.
Mirar la pantalla no las recupera.

De ahí la regla que define el script, y que es la única línea que hay que recordar:

> **se vacía lo que el sistema sabe volver a observar; se conserva lo que no.**

### La clasificación es obligatoria y exhaustiva

Las 32 tablas están en exactamente un grupo: `CATALOGO` · `INVESTIGACION` · `DECLARADO` · `VACIAR`
· `DERIVADAS_VACIAS`, más `agents` aparte. Si una tabla no está clasificada, **`rebuild` falla a
propósito**:

```python
raise ValueError(f"tablas sin clasificar en {origen.name}: {faltan}. ...")
```

No es paranoia de diseño: se disparó **el mismo día**. Al aplicar la migración 20,
`roster_declarations` apareció sin clasificar y el rebuild frenó. La alternativa —vaciar por
defecto lo desconocido— es exactamente cómo se pierden datos que nadie sabía que eran
irrecuperables.

`roster_declarations` fue a un grupo nuevo, `DECLARADO`: lo que el usuario afirma sobre su cuenta no
es observación, y ningún censo lo reproduce. Si la DB se vuelve a reconstruir, sus declaraciones y
su historial sobreviven.

### Las tres columnas que son stats y NO se vaciaron

`mindscape`, `perforacion` y `bono_dano_elemento`. El comentario de `sync_agent_stats._STAT_MAP` es
explícito: S18 no las parsea. Vaciarlas habría repetido el error de vaciar los umbrales.

**Van marcadas en el reporte como arrastradas.** Un dato conservado que el usuario cree recién
censado es peor que uno faltante: se ve igual de confiable y no lo es.

### Resultado real

```
integrity ok · foreign_key_check OK
agents 51 (identidad + id intactos) · investigación 532 · catálogo 220
inventory_discs 367→0 · agent_discs 270→0 · evaluations 334→0 · weapons 50→0 · optimizer 423→0

Ellen: ('Ellen','S','Hielo','Ataque','Victoria Housekeeping', nivel=None, mindscape=0, pv=None, weapon_id=None)
```

Respaldo: `audit/danibod_zzz_v2.pre_censo_20260817_193905.db` · reporte
`audit/rebuild_db_20260817_193905.md`.

El nombre del archivo **no cambió**. `danibod_zzz_v2.db` está hardcodeado en 8 módulos; una "v3"
obligaba a tocarlos todos sin ganar nada. Lo que cambia es el contenido.

---

## 3. La declaración

`roster_declarations` guarda **la tanda completa** —los ~58 con su 1 o su 0— y no solo los
tildados. Tres razones, y la tercera es la que no es obvia:

1. Historial: re-declarar es una tanda nueva, no una corrección. Eso vuelve la tabla una auditoría
   de sincronía y no un flag de "ya se hizo".
2. El denominador explícito.
3. **El registro de los NO poseídos** (`poseido = 0`), que es justo lo que la pantalla no expone de
   forma fiable y lo que después permite **vetar** un match difuso a un gris.

Va a la DB de dominio y no a `census.db`: lo declarado **define** el roster. `census.db` guarda
evidencia observacional *sobre* el dominio, que es otra cosa.

`declarar()` copia la ceremonia de `census_store.marcar_huerfanos_en_dominio`, que ya es el patrón
validado: gate `is_readonly()`, backup previo, transacción, los dos PRAGMA, idempotencia. Tres
efectos, ninguno borra:

| caso | qué hace |
|---|---|
| declarado **sin** fila en `agents` | `INSERT` mínimo, identidad NULL, `notas='declarado_por_usuario_<fecha>; pendiente onboarding'` |
| en `agents` y **no** declarado | anota `no_declarado_<fecha>`. **No borra** (RNF-02) |
| declarado y ya presente | no se toca |

La fila mínima no es un capricho: **sin fila en `agents` la cosecha de badges se descarta en
silencio** — pasó con Aria.

---

## 4. Tres cosas que aparecieron al implementar

### El `ts` de segundos fusionaba dos tandas en una

Lo encontró un test antes de que llegara a la DB. `ts` es la clave que agrupa la tanda, y dos
declaraciones dentro del mismo segundo colapsaban en una sola foto — justo lo que la tabla existe
para no hacer. Pasó a microsegundos, igual que los reportes del censo.

### `setEnabled(False)` no es una garantía

El test del diálogo falló porque `setChecked(False)` funciona igual sobre un check deshabilitado:
`setEnabled` frena el **click del usuario**, no el código.

El arreglo no fue debilitar el test sino mover el bloqueo a donde importa: `seleccionados()`
agrega **siempre** los confirmados. Lo inviolable tiene que ser **lo que se escribe**, no el estado
del widget. La casilla deshabilitada es la afordancia; la garantía vive abajo.

### El día 1 no hay ningún confirmado — y está bien

Con stats y discos en NULL, nadie califica como "confirmado por evidencia", así que en la primera
declaración **todo es destildable**. Es correcto: se está declarando desde cero. El bloqueo
recupera sentido a medida que el censo llena datos.

Verificado contra la DB reconstruida: `58 personajes · 51 en agents · 7 solo arte · 0 confirmados`.

---

## 5. ⚠️ El diálogo muestra 58 casillas para 55 personajes

```
51 en agents            = 49 personajes + 2 variantes de ATUENDO (Billy Estelar, N.º 0: Anby)
 +7 solo con arte       = Banyue, Hugo, Lichter, Lighter, Norma, Promeia, Yidhari
```

`Lichter` y `Lighter` son **el mismo personaje con dos grafías de archivo**
(`Lichter-ico.webp` contra `Lighter-extend.webp`). **No se dedupeó a propósito**: elegir una por
parecido sería adivinar, y el nombre correcto es el que muestre la pantalla del juego. Se cierra
con una lectura del OCR sobre ese PJ y quedan 57.

Las 2 variantes de atuendo son el límite conocido del modelo (`agents` cuenta filas, no personajes)
y el mismo que produce los imanes de la librería de badges.

---

## 6. Consecuencia en la suite: el optimizador se quedó sin discos

`test_optimizer_miyabi.py` cayó con 5 fallos. **No es una regresión**: el optimizador arma builds
*eligiendo* entre los discos que hay, y con el inventario vacío devuelve builds de 0 discos y
score 0. Es una precondición que dejó de cumplirse.

El fixture ahora hace `skip` con el motivo explícito, y **se cura solo**: en cuanto el censo cargue
inventario, el test vuelve sin tocar nada. Poner el skip sin decir por qué habría dejado 16 tests
apagados que nadie iba a volver a mirar.

---

## 7. Lecciones

1. **"Desde cero" tiene un límite, y es lo que no se puede volver a observar.** La pregunta útil no
   es "¿qué borro?" sino "¿esto lo puedo recuperar mirando la pantalla?". Las 516 filas de Prydwen
   y las 3 columnas que S18 no parsea salen de la misma pregunta.
2. **Una clasificación exhaustiva con fallo duro vale más que un default.** Se disparó el mismo día
   que se escribió, con `roster_declarations`.
3. **Deshabilitar un control no es hacer cumplir una regla.** La regla se hace cumplir donde se
   escribe el dato.
4. **Un skip tiene que decir por qué y cuándo deja de aplicar**, o se convierte en cobertura
   perdida en silencio.

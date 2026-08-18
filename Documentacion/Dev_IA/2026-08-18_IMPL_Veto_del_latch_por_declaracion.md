# El veto del latch: lo que no tenés ya puede desmentir un match

> **2026-08-18** · `app/core/parser_agent_stats.py`, `app/core/roster_declaration.py`,
> `app/core/census.py`
> Cierra el bloqueante del re-censo de discos. Depende de la declaración del roster
> ([`2026-08-17_IMPL_Rebuild_DB_y_Roster_Declarado.md`](./2026-08-17_IMPL_Rebuild_DB_y_Roster_Declarado.md)).

---

## 1. El problema no era el umbral

El matcher de identidad elige **el más parecido del roster**, y el roster es `agents` — es decir,
solo lo que sí poseés. Frente a un personaje ajeno el matcher no tiene la opción correcta
disponible, así que gana un parecido coincidental. Medido contra la DB real, antes del arreglo:

| leído | mejor del roster | ¿supera el umbral 0.55? |
|---|---|---|
| `Banyue` | Anby **0.600** | sí ⚠️ |
| `Lichter` | Alice **0.667** | sí ⚠️ |
| `Norma` | Nekomata **0.615** | sí ⚠️ |
| `Promeia` | Pyrois **0.615** | sí ⚠️ |
| `Hugo` | Zhao 0.500 | no |
| `Lighter` | — 0.500 | no |
| `Yidhari` | — 0.545 | no |

**4 de 7.** Y las tres que se salvaban lo hacían por casualidad: 0.545 está a 0.005 del umbral.

La tentación es subir el umbral. Es la salida equivocada: **0.55 existe para tolerar lecturas
sucias de PJs que sí tenés** (`Nekomat` → Nekomata, `Astre Yoo` → Astra Yao). Subirlo cambiaría un
error por otro. Lo que faltaba no era rigor: era **el nombre ausente**.

## 2. La declaración lo aporta, y por eso el arreglo es chico

`roster_declarations` es la primera lista autoritativa de lo que **no** está en la cuenta — algo
que la observación no puede producir por más que recorra el menú. Con esos nombres a mano, el
matcher pasa a tener la opción correcta.

Los no poseídos entran a la comparación como **señuelos**: no son candidatos a identificar (no son
tuyos), pero sí a ganar. Cuando ganan, el matcher se abstiene.

```
Norma  →  señuelo "Norma" 1.000  >  Nekomata 0.615  ⇒  abstiene
```

Después del arreglo, los 7 se abstienen — y encima **saben quién es** (1.000 contra el nombre
real). Eso es estrictamente mejor que "no sé": el censo puede registrar el gris en vez de tirarlo.

### Tres decisiones de diseño, cada una con su porqué

**El señuelo tiene que GANAR, no empatar.** Vetar por parecerse *tanto como* el propio convertiría
la declaración en una forma de apagar la identificación de un PJ con build. `veto_sim > mejor_sim`,
estricto.

**Un declarado que además tiene fila en `agents` no se veta.** Ahí la declaración y los datos se
contradicen; una fila con build no se apaga por una casilla destildada. Ese conflicto se resuelve
donde corresponde: `declarar()` lo marca en `notas` como sobrante.

**Solo pesa la última tanda.** Una declaración vieja que siguiera contando vetaría para siempre a
un PJ que el usuario acaba de sacar — justo cuando empieza a importar identificarlo.

Y una condición de borde que no es negociable: **sin declaración, todo queda como antes**. El
lector devuelve el conjunto vacío ante cualquier problema. Esto mejora la identificación; no puede
volverse un requisito para que funcione.

## 3. El efecto de costado que casi se cuela

El veto cambió **qué puede ser `candidato`**. Antes salía siempre del roster, así que en
`census._resolver_clave` la rama del casi-acierto podía dar `en_db=True` por construcción:

```python
if s.candidato and s.score >= _NUEVO_MAX_SIM:
    return s.candidato, True, True      # ← "es tuyo" cableado a mano
```

Con el veto, el candidato **puede no ser tuyo**. El caso limpio no se rompe —`_resolver_clave`
compara el texto crudo contra los grises *antes* que el match difuso— pero una lectura sucia de un
gris (`Lichten` por `Lichter`) esquiva esa comparación y cae en la rama del candidato. Sin el
arreglo, un personaje ajeno habría entrado al censo como **uno tuyo pendiente de ver**, inflando
el denominador de cobertura en silencio.

Arreglado consultando `_grises` también en esa rama. Test: `test_un_casi_acierto_sobre_un_GRIS_no_se_cuenta_como_PJ_tuyo`.

**La lección:** cambiar qué *significa* un valor de retorno es un cambio de contrato aunque el tipo
no cambie. Buscar quién lo consume no es opcional.

## 4. Un test que pasó a la primera no probaba nada

Los 10 tests del veto pasaron en la primera corrida. Eso no es evidencia de que detecten el bug, así
que se desactivó el veto a propósito:

```
assert nombre is None, "no puede identificar a un PJ que declaraste no tener"
E   assert 'Nekomata' is None
```

El bug reportado, reproducido en el fixture. Recién ahí el verde significa algo.

## 5. El test de Hugo cambió, y el cambio es la mejora

`test_el_matcher_expone_al_mas_parecido_aunque_no_pase_el_umbral` fijaba `0.4 <= sim < 0.55` para
`Hugo` — describía un mundo donde Hugo era desconocido y se salvaba por poco. Hoy Hugo se reconoce
por nombre (1.000) y la abstención es deliberada.

El test ahora acepta los dos mundos, ramificando por si el roster está declarado: una DB recién
clonada no tiene declaración, y ahí el comportamiento viejo sigue siendo el correcto.

## 6. Qué desbloquea

El re-censo de discos. Es **human-bound** —11-20 s por disco, ~367 discos— y lo que atribuye cada
disco a un dueño es el latch. Con el latch envenenado, pararse sobre un gris del menú no dejaba al
sistema en "no sé": lo dejaba convencido de estar en otro personaje, y los discos siguientes se le
colgaban a ése. Silencioso, y visible recién al auditar.

Arreglar esto cuesta un rato de máquina. No arreglarlo costaba rehacer horas de trabajo manual.

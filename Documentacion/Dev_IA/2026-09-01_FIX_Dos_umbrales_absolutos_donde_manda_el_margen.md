# Dos umbrales absolutos donde manda el margen — y dos atribuciones que estaban mal

> **2026-09-01.** Pendientes 3 y 4 del cierre del censo: apagar la promoción del top-2 con una
> pasada abierta, y poner una regla de margen en el resolvedor de nombres de set.
>
> Los dos se hicieron. Y al ir a buscar la evidencia para el 3, **dos cosas que yo mismo había
> documentado el 30/31 resultaron falsas**. Las dos correcciones están acá.

---

## 1. El desempate: no era "por build", y es peor de lo que decía el audit

`audit/bug_desempate_por_build_durante_censo_20260830.md` lo tituló *desempate por build*. La
señal `build` **no se disparó ni una vez en toda la pasada**, y no podía: sale de
`agents.set_4p_id / set_2p_id`, y esas dos columnas están en NULL para **los 51 agentes**. El
mapa de builds del tiebreaker se carga vacío.

Los 54 desempates del log salieron todos de la otra señal, `equip` — *"este PJ ya tiene un disco
con esta huella (set, slot, main)"*. Que es **peor**, porque `build` al menos leería datos
curados: `equip` lee `inventory_discs`, exactamente la tabla que el censo está construyendo.

### La evidencia que el audit no tenía: la regla se contradice a sí misma

11 promociones del top-2 en la pasada del 30. Dos de ellas, sobre el **mismo par**:

```
22:14:26  equip_top2: Manato   top=[Antón:0.93,  Manato:0.92, Lucy:0.71]   <- da vuelta hacia Manato
23:05:03  equip_top2: Antón    top=[Manato:0.93, Antón:0.90,  Lucy:0.73]   <- da vuelta hacia Antón
```

Cincuenta minutos separan un veredicto de su opuesto, con la vista diciendo lo mismo en los dos
casos (el top-1 va 0.01-0.03 arriba). Lo único que cambió en el medio es cuántos discos había
registrados. **No es que la regla se equivoque a veces: es que su respuesta depende de por dónde
iba el censo.** Un dato que ninguna de las dos veces existía todavía.

Las 11 promociones, y en qué quedaron:

| hora | promueve | por encima de | disco | dueño hoy |
|---|---|---|---|---|
| 22:05 ×2 | Ju Fufu | Yuzuha | id=85 Monarca s3 | **Anby** (cambió después) |
| 22:14-22:15 ×4 | Manato | Antón | id=121 Fábula s3 | Manato |
| 22:50 | Manato | Antón | id=121 | Manato |
| 22:54 | N.º 0: Anby | Orfia y Magas | — | — |
| 23:05 | **Antón** | **Manato** | id=254 Tecno Pícido s4 | **Antón** ⚠️ |
| 23:08 ×2 | **Antón** | **Harumasa** | id=268 Tecno Pícido s6 | Harumasa (se corrigió sola) |

El caso que Daniel reportó en vivo (id=268) **se arregló solo** al volver a ver el disco. El que
quedó en pie es **id=254**, promovido a Antón por encima de Manato con margen 0.03 — el límite
exacto de `_TOP2_MARGIN_MAX`.

### El arreglo

`OwnerTiebreaker.resolve(..., permitir_top2=False)` mientras haya una pasada de censo abierta. Se
mantiene la **confirmación del top-1**, que corrió 39 veces: ahí el contexto no invierte nada, sólo
respalda lo que la vista ya puso primero. Lo que se apaga es dar vuelta al top-1 **apoyándose en
una ausencia** que durante el censo significa *"todavía no llegué a sus discos"*.

El monitor lo calcula con `_censo_discos_en_curso()`, que es una consulta y **no abre** la pasada:
abrir un censo como efecto de costado de una decisión de identidad es el error que el censo del
roster ya enseñó a no cometer.

Costo: las promociones correctas de esa lista se vuelven abstenciones, y el disco queda guardado
**sin dueño**. Recuperable. Un dueño equivocado no lo es — y encima desplaza al disco legítimo.

## 2. Los dos discos duplicados de Antón NO salieron del desempate

El cierre del censo atribuyó `id=355` y `id=339` al desempate. **No.** El log los tiene:

```
23:38:58  [s9_owner] match directo: Harumasa (conf 0.91)   -> id=338 slot 3, bien
23:39:11  [s9_owner] match directo: Antón (conf 0.91)      -> id=339 slot 5, MAL
```

`match directo` es el matcher de badges de la grilla resolviendo solo, sin tiebreaker de por medio.
Tres minutos antes, el mismo par se daba vuelta entre frames:

```
23:39:06  top=[Harumasa:0.86, Antón:0.85]
23:39:07  top=[Antón:0.87,    Harumasa:0.85]
23:39:08  top=[Harumasa:0.87, Antón:0.86]
```

Ninguna de esas tres pasó el margen y las tres se abstuvieron. La cuarta salió con 0.91 y margen
suficiente, y esa fue la que escribió. **Es una lotería de frames**, y el arreglo del punto 1 no la
toca. Queda como problema abierto: Antón/Harumasa (y Antón/Manato) son clases que el descriptor de
la grilla no separa.

## 3. El desplazamiento era mudo

Cuando un disco entrante reclama un slot ocupado, el anterior queda `equipado=0`. Es correcto y
está por diseño. Lo que faltaba es que **no lo decía nadie**: el `s17_swap` de id=339 salió en el
log idéntico a un alta normal, y el disco legítimo de Antón se apagó sin una línea.

Por eso el estado raro —dos filas del mismo PJ en el mismo slot— apareció **dos días después**, al
consultar la DB a mano.

Ahora sale un `WARNING` que nombra a los dos discos y al dueño entrante. Es raro (2 en 383) así que
no hace ruido, y cuando el dueño se leyó mal, es la línea que lo delata en el momento.

## 4. El resolvedor de sets: medir primero, y ahí también había una atribución mal

Escribí el 30 que `Blues libre Precdom` resolvía con ratio 0.7407 y que por lo tanto *"hay otra vía
(el matcher de logos)"*. **No hay tal cosa.** Resuelve por el atajo de **substring** del mismo
resolvedor: `blueslibre` está contenido en `blueslibreprecdom`.

Y no es un caso de borde. Sobre el corpus real (89 lecturas del log del censo):

| vía | lecturas |
|---|---|
| **substring** | **57** |
| exacta | 14 |
| difflib | 9 |
| no resuelve | 6 |

El difflib —lo único que el cutoff gobierna— decide **9 de 89**. Todo el debate sobre el 0.86
estaba pasando en el 10 % del problema.

### La calibración

`tools/measure_set_resolver.py` (nuevo) mide contra dos corpus: el de campo y uno adversario de
**3789 corrupciones** sintéticas de los 30 nombres del catálogo (borrados, transposiciones,
confusiones de OCR).

```
regla            corpus:det_ok  MAL  basura | corr:bien   MAL  abst
ACTUAL .86/.06            1803    0     3/3 |      3559     0   230
0.70/0.12                 1822    0     3/3 |      3782     0     7
0.75/0.12                 1822    0     3/3 |      3782     0     7
0.80/0.12                 1822    0     3/3 |      3775     0    14
0.86/0.12                 1803    0     3/3 |      3558     0   231
```

Tres cosas que la tabla dice y que yo no habría adivinado:

1. **`MAL = 0` en todas las combinaciones**, incluso las más flojas. En este catálogo el riesgo no
   es nombrar mal, es abstenerse: los 30 nombres están bien separados (el par más parecido,
   `metal eléctrico` vs `metal caótico`, está a 0.7692 entre sí).
2. **El rescate viene entero de bajar el cutoff.** El margen no aporta aciertos: sólo cobra
   abstenciones (0.06 → 2; 0.12 → 7; 0.15 → 22).
3. **0.70, 0.75 y 0.80 dan idéntico resultado.** Es una meseta, no un filo — igual que pasó con el
   guard del detalle. Elegir el borde de una meseta es elegir mal por accidente.

**Queda en `0.75 / 0.12`**: el medio de la meseta (la lectura genuina más floja está en 0.8148 y
la basura más alta en 0.4615), y 0.12 en vez de 0.15 porque la familia `metal caótico` compite con
`metal eléctrico` a **0.1474** — a 0.15 se perdían transposiciones legítimas.

### Y de paso, dos bugs estructurales

- **La guarda de ambigüedad miraba sólo el top-3.** Con `get_close_matches(n=3, cutoff=...)`, un
  rival a distancia de margen que quedara 4º —o debajo del cutoff— era invisible: la guarda
  dependía de quién hubiera entrado al recorte. Ahora se rankea el catálogo entero.
- **`sync_equip` tenía su propia copia de los dos números**, y era la que mandaba en el camino que
  más usa el resolvedor. Calibrar el repo no habría cambiado nada ahí. Borrada.

### Un test que afirmaba lo contrario

`test_resolve_set_id_fuzzy_drop_de_letra` exigía que `Balada de la rama y la espada` **no**
resolviera, llamándola *"genuinamente lejana/ambigua"*. Medida: 0.8000 contra el alias corto del
mismo set y 0.5581 contra el otro `Balada` — **0.24 de margen**. Nunca fue ambigua; abstenerse
salía sólo de estar 0.06 debajo de un cutoff. El test se actualizó al veredicto correcto, y se le
agregó un caso que abstiene **por margen** (0.7778 de ratio, 0.0085 de separación) para que la
guarda siga probada. Verificado rompiéndola a propósito: 3 tests caen.

---

## Lo que me llevo

**Un grep truncado es una medición, y se puede usar mal como cualquier otra.** A mitad de esta
investigación afirmé que el desempate nunca había disparado, porque miré las últimas 20 líneas de
un `grep` y todas eran abstenciones. Eran 54 aciertos. Estuve a punto de escribir que el pendiente
3 no tenía sentido —y de dejarlo sin hacer— apoyado en las últimas 20 líneas de 7107. `grep -c`
antes de concluir.

**Que la fuente de un dato esté mal nombrada esconde cuán mal está.** El audit decía *build*; era
*equip*. La diferencia importa: `build` lee una tabla curada a mano, `equip` lee la que se está
llenando. El título hacía que el problema pareciera más leve de lo que era.

**Antes de bajar un umbral, contar por dónde pasa la gente.** El 86 % de las lecturas de set no
tocan el cutoff: entran por substring o por match exacto. Todo el análisis del 30 —incluida una vía
de resolución que inventé— estaba discutiendo el 10 % del camino.

---

**Pendientes que esto deja:**

- ⚠️ **`id=254`** (Tecno Pícido slot 4, hoy en Antón) es la única promoción del top-2 que sigue en
  pie: se lo sacó a Manato con margen 0.03. Confirmar en pantalla, junto con los slots 1 y 5 de
  Harumasa (`id=355`, `id=339`).
- La lotería de frames entre Antón / Harumasa / Manato en la grilla sigue abierta: es lo que
  escribió los dos discos duplicados, y ninguno de estos dos arreglos la toca.
- `agents.set_4p_id / set_2p_id` están en NULL para los 51 agentes ⇒ la señal `build` del
  desempate es código muerto. O se cargan, o se saca.

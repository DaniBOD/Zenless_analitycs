# Inventario de discos reconciliado — 51/51 PJs

**2026-09-05.** Cierre de los pendientes que dejó el censo del 2026-08-30
([`censo_discos_cierre_20260830.md`](./censo_discos_cierre_20260830.md)).

```
384 discos  ·  0 marcados  ·  0 asignados sin equipar  ·  0 duplicados (PJ, slot)
50 PJs con 6/6  +  Nekomata 5/6 (slot 5 vacío, confirmado en pantalla)  =  51/51
integrity_check ok  ·  foreign_key_check sin violaciones
```

**Nada de esto se arregló editando la DB.** Las correcciones salieron de la pantalla; lo único
que se borró fueron filas que no podían corresponder a ningún disco del juego.

## 1. Los dos discos de Harumasa volvieron solos

La hipótesis del cierre del censo —*"devolverle `id=355` y `id=339` le arma un 4pc Metal
Eléctrico + 2pc Tecno Pícido coherente"*— la confirmó el juego seis días después, sin que
hiciera falta escribir una sola sentencia:

```
02:10:33  id=355 s17_move     Metal eléctrico s1  Antón → Harumasa (corrección tardía)
02:10:45  id=339 s17_move     Metal eléctrico s5  Antón → Harumasa (corrección tardía)
02:11:19  id=281 s17_reequip  Disco Sacudestrellas s1 → Antón
02:11:25  id=259 s17_reequip  Tecno Pícido s5 → Antón
```

| | build resultante |
|---|---|
| **Harumasa** | 4pc Metal Eléctrico (s1, s2, s3, s5) + 2pc Tecno Pícido — estándar 4+2 |
| **Antón** | 2pc Sacudestrellas + 3pc Tecno Pícido + Nana — exótica, pero es la suya |

### ⚠️ `id=254` no era un error

Se había señalado como *"la única promoción del top-2 que sigue en pie"* y por lo tanto
sospechosa. La pantalla dice que **es de Antón** (`s17_update`, sin mover nada): la promoción de
Antón sobre Manato estaba **bien**.

Eso no invalida el gate del 2026-09-01. El problema nunca fue que la regla acierte o falle, sino
que **su respuesta depende de por dónde iba el censo** — para ese mismo par dio veredictos
opuestos con 50 minutos de diferencia. De los dos casos rastreables, acertó uno y falló el otro.

## 2. Los 5 marcados: dos reales, tres fantasmas

Una fila marcada `dueno_no_identificado` **AFIRMA que alguien la tiene equipada**. Es una
afirmación, así que se puede contradecir — y eso es lo que discriminó:

| disco | ¿hueco en su slot? | ¿gemela con dueño? | ¿cerca de un reinicio? | veredicto |
|---|---|---|---|---|
| `id=127` Fábula Yunkui s5 | **sí** (Yixuan) | no | no | **real** → adoptado |
| `id=171` Balada s4 | **sí** (N.º 0: Anby) | no | no | **real** → adoptado |
| `id=120` Fábula Yunkui s3 | no | sí (121 → Manato) | 6 s antes | fantasma → borrado |
| `id=266` Tecno Pícido s6 | no | sí (267 → Anby) | 4 s antes | fantasma → borrado |
| `id=301` Blues Libre s2 | no | sí (302 → Soukaku) | 7 s antes | fantasma → borrado |

Los tres criterios coincidieron en los cinco casos. **Los dos que tenían hueco propio eran
legítimos; los tres que no tenían dueño posible eran duplicados.**

### De dónde salieron los fantasmas

El censo tuvo **22 reinicios**: cuando el reconocimiento fallaba, Daniel detenía y reiniciaba la
captura. La secuencia era:

1. Disco en pantalla, ninguna superficie nombra al dueño → se guarda **marcado**.
2. Reinicio de la captura.
3. En la pasada nueva sí lo nombra.
4. Y como una fila marcada **no se podía adoptar**, insertaba una segunda.

Arreglado en `a9a6dcd` (las marcadas se adoptan) y limpiado en la migración `_23`.

## 3. Cuatro discos que el censo nunca capturó

Al mirar los huecos aparecieron discos que sí existían en el juego y que la pasada no había
visto: **Ju Fufu s3, Orfia y Magas s2, Alice s1, Corin s1** (este último a nivel 3, quizá por eso
pasó desapercibido). Parte de la brecha entre el contador del juego (401) y lo capturado (383)
era esto, no gemelos.

## 4. Migraciones aplicadas

| | qué hizo | verificación |
|---|---|---|
| `_21` | borró el duplicado del slot 5 de Yixuan (384 → 383) | 5 smoke checks exactos |
| `_22` | sacó la marca vencida de `id=127`, que ya tenía dueño | 5 exactos |
| `_23` | borró los tres fantasmas (385 → 382) | 5 exactos |

Las tres ensayadas contra una copia antes de la corrida real, con backup previo, transacción, y
`foreign_key_check` + `integrity_check` después (RNF-01).

## 5. Lo que queda abierto

- **`id=93`** (Monarca s3, libre) es byte a byte idéntico al de Ju Fufu (`id=385`) y **no se
  toca**: una fila LIBRE afirma *"no lo tiene nadie"*, y que otro PJ tenga uno igual no la
  contradice. Dos discos idénticos pueden coexistir.
- El **contador del juego** decía 401 y hay 384 filas. La diferencia son discos no visitados y
  gemelos; el censo reporta la brecha, no la cierra a la fuerza.
- La **lotería de frames** entre Antón / Harumasa / Manato en la grilla sigue abierta: es lo que
  escribió los dos discos mal asignados, y ninguno de los arreglos de esta semana la toca.

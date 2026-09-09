# Una marca es una afirmación — y por eso se puede refutar

> **2026-09-05.** El inventario quedó reconciliado: **51/51 PJs**. Lo interesante no es el
> número, es que los cinco discos "de dueño incierto" se resolvieron **sin mirar ninguno de
> ellos**: lo decidió preguntar si su afirmación podía ser cierta.
>
> Cierre operativo en [`audit/inventario_reconciliado_20260905.md`](../../../../audit/inventario_reconciliado_20260905.md).

---

## El problema

Cinco filas guardadas con `dueno_no_identificado`. Dos posibles historias para cada una:

- es un disco real que alguien tiene equipado y no se pudo nombrar, o
- es una fila duplicada de otra que sí tiene dueño.

Y en la tabla se ven **idénticas**: `agente_asignado` NULL, `equipado` 0, la marca.

## Lo que las separó

La marca no es un dato: **es una afirmación**. Dice *"alguien lo tiene equipado"*. Y una
afirmación se puede contradecir con el resto del estado.

Un disco de slot 6 sólo puede estar en el slot 6 de alguien. Si los 51 PJs ya tienen su slot 6
ocupado por otro disco, **no queda nadie que pueda tenerlo** — y la afirmación es falsa. Más aún:
es falsa *precisamente en la lectura que ya había fallado*, la del dueño.

```
                    ¿hueco en su slot?   ¿gemela con dueño?   ¿cerca de un reinicio?
id=127  Yixuan            sí                    no                    no          → REAL
id=171  N.º 0: Anby       sí                    no                    no          → REAL
id=120                    no                    sí                  6 s antes     → fantasma
id=266                    no                    sí                  4 s antes     → fantasma
id=301                    no                    sí                  7 s antes     → fantasma
```

Tres señales independientes, y **coincidieron en los cinco casos**. Los dos que tenían hueco
propio resultaron legítimos y se adoptaron solos al mirar al PJ; los tres que no tenían dueño
posible eran duplicados.

## El mecanismo, que apareció en los segundos

Las tres fantasmas se escribieron **entre 4 y 7 segundos antes de un reinicio del monitor**. El
censo tuvo 22 reinicios: cuando el reconocimiento fallaba, Daniel detenía y reiniciaba la captura
—su propio workaround, y funcionaba—. Sólo que:

1. disco en pantalla, nadie lo nombra → fila **marcada**;
2. reinicio;
3. en la pasada nueva **sí** lo nombra;
4. y como una fila marcada no se podía adoptar, **insertaba una segunda**.

La marca se había agregado para **no perder el disco entero** cuando el dueño no se leía. Pero
nada podía reclamarla después, así que garantizaba un duplicado por disco marcado. Una red de
seguridad sin salida.

## Tres correcciones que me debo

**Casi descarto el pendiente por un `grep | tail -20`.** Miré las últimas 20 líneas, todas
abstenciones, y concluí *"el desempate nunca disparó"*. `grep -c` decía **54**. Quedó como
práctica A5.

**Creí que `266`/`267` eran adyacentes.** Están a 15 segundos y el censo camina un tile cada 5-8,
así que parecían dos tiles vecinos — y los gemelos quedan adyacentes en el inventario ordenado,
que es justo la firma de un gemelo *real*. Lo resolvió el reinicio en el medio, a las 23:06:40:
no son dos tiles, es **el mismo tile a los dos lados de un reinicio**.

**Señalé `id=254` como mal asignado y no lo estaba.** La promoción del top-2 que había marcado
como sospechosa acertó. Eso no invalida el gate que puse el 01/09 —la regla dio veredictos
opuestos para el mismo par con 50 minutos de diferencia, así que no es una autoridad mientras el
censo corre— pero de los dos casos rastreables, acertó uno y falló el otro.

## Lo que me llevo

**Una afirmación en los datos vale más que un dato, porque se puede refutar.** `libre` y
`dueño incierto` se ven igual en la tabla, y esa diferencia —que costó implementarla— fue lo que
permitió cerrar el caso: a la fila marcada se le puede preguntar *"¿y quién lo tiene?"*, y quedarse
sin respuesta es información. A una fila libre no se le puede preguntar nada equivalente: dice que
nadie lo tiene, y que otro PJ tenga uno idéntico **no la contradice**. Por eso `id=93` sigue en pie
y los otros tres no.

**Una red de seguridad sin salida es una fuga.** Guardar el disco marcado evitaba perder set,
slot, nivel y substats — bien. Pero no haber previsto **cómo se sale de ese estado** convirtió el
rescate en una fábrica de duplicados. Cuando se agrega un estado "provisional", la pregunta que
falta casi siempre es quién lo saca de ahí.

**El arreglo correcto hizo el trabajo solo.** Los cuatro discos mal asignados de Harumasa y Antón,
y los dos marcados legítimos, se corrigieron **mirando la pantalla** — `s17_move`, `s17_reequip`,
`s17_adopta`. Ninguna sentencia SQL. La tentación de escribir un `UPDATE` con la hipótesis (que
era correcta, y estaba escrita hacía seis días) habría llegado al mismo resultado sin dejar la
evidencia de que el juego lo confirmó.

---

**Migraciones:** `_21` (duplicado de Yixuan) · `_22` (marca vencida) · `_23` (los tres fantasmas).
Las tres ensayadas contra una copia antes de la corrida real.

**Queda abierto:** la lotería de frames entre Antón / Harumasa / Manato en la grilla — es lo que
escribió los dos discos mal asignados, y ninguno de estos arreglos la toca.

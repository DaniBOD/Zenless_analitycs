# Duplicado del slot 5 de Yixuan — cómo apareció y cómo se cerró

**2026-09-01 / aplicado 2026-09-03.** Migración `db/migrations/2026-09-01_21_dedup_disco_yixuan_s5.sql`.

## Qué pasó

Se abrió a Yixuan en S17 para confirmar una hipótesis del cierre del censo: que el disco `id=127`
—guardado sin dueño y marcado `dueno_no_identificado_2026-08-30`— era el de su slot 5.

**La hipótesis era correcta.** La app leyó `Fábula Yunkui slot 5 · Bono Daño Éter · nv15 · dueño
Yixuan` y lo dejó en **6/6 · estándar 4+2** (4pc Fábula Yunkui + 2pc Balada de la rama y la espada).

Pero en vez de ponerle el dueño a la fila que ya existía, **insertó una nueva** (`id=384`). El
inventario pasó de 383 a 384 discos.

## Por qué

`find_swap_candidates_by_identity` excluía a propósito **toda** fila sin dueño. Para un disco
LIBRE el motivo es bueno: entre dos gemelos (22 pares en el inventario real) adoptar el equivocado
haría desaparecer al libre de verdad.

Pero la marca `dueno_no_identificado` **afirma que alguien lo tiene**: no hay ningún libre que
perder, y es justo la reconciliación para la que la marca existe. Sin eso, lo que se agregó para no
perder el disco entero garantizaba **un duplicado por disco marcado** — habría vuelto a pasar con
los otros cuatro (ids 120, 171, 266, 301) en cuanto se pasara por sus PJs.

Arreglado en `a9a6dcd`: las filas marcadas se adoptan; las libres siguen sin tocarse.

## Qué se hizo con los datos

Las dos filas coinciden en los **doce campos de identidad**: set 49, slot 5, main `Bono Daño Éter`
30.0, nivel 15, y los cuatro substats con los mismos valores **y** los mismos rolls.

```
id=127   fecha_obtencion 2026-08-31 02:51   sin dueño   equipado=0   marcada
id=384   fecha_obtencion 2026-09-01 15:37   Yixuan      equipado=1   sin marca   <- borrada
```

**Se conservó la 127.** Su `fecha_obtencion` es la real (cuando el censo vio el disco); la de la
384 es cuándo se creó el duplicado, que no es lo mismo.

**No se le escribió el dueño a mano.** Queda sin dueño y con su marca: con la adopción arreglada,
la próxima vez que se abra a Yixuan la app se lo pone leyéndolo de la pantalla. Un dato que puede
venir de la observación no se inventa en una migración (RNF-02).

## Verificación

```
backup      db/danibod_zzz_v2.backup_premig_20260903_083239.db
expected_0    id=384 borrada                              0  ✓
expected_1    id=127 sigue                                1  ✓
expected_383  total de discos                           383  ✓
expected_5    filas marcadas 'dueño incierto'             5  ✓
expected_5    slots equipados de Yixuan                   5  ✓
foreign_key_check   0 violaciones
integrity_check     ok
```

Ensayada antes contra una copia de la DB, con los mismos cinco resultados.

## Lo que queda

- Abrir a Yixuan una vez para que adopte la `127` (pasa de 5/6 a 6/6 con el dueño escrito).
- Los otros 4 marcados se arreglan solos al pasar por sus PJs, ya sin duplicar.

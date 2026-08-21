# Un dueño que no se puede nombrar ya no se lleva puesto el disco entero

> **2026-08-21.** Sale de la corrida real del censo del 2026-08-20, medida sobre el log:
> **3 discos perdidos de 119** (2,5 %). Dos de esos tres se perdieron por lo mismo — el badge
> decía que el disco tenía dueño y ninguna superficie pudo decir quién.
>
> Continúa [`2026-08-18_FIX_S9_libre_vs_no_se.md`](./2026-08-18_FIX_S9_libre_vs_no_se.md), que
> arregló el primer caso de la misma familia: *el dato no faltaba, la función lo tiraba*.

---

## 1. Qué se perdía, y por qué no era poco

`sync_equip.persist_s17_disc` tenía dos desenlaces cuando no había PJ resuelto:

| lectura del badge | qué hacía |
|---|---|
| `equip_libre=True` — se vio la esquina del tile y **no hay avatar** | persiste con `agente_asignado = NULL` |
| cualquier otra cosa | **descarta el disco entero** |

El segundo cajón mezclaba dos situaciones que no se parecen en nada:

- **no se pudo leer nada** — ausencia de dato. Descartar es correcto.
- **hay avatar, pero ninguna superficie lo nombró** — el disco se leyó **completo**: set, slot,
  nivel, main y los cuatro substats con sus rolls. Falta **un** campo, y se tiraban los diez.

Es la regla **B2** textual: *abstenerse no debe costar el dato entero*.

## 2. Por qué el descarte estaba ahí, y por qué había que preservar el motivo

No era descuido. Sin PJ no existe la clave natural `(PJ, slot)`, y en este roster **el 72 % de los
discos comparte firma con el disco de otro PJ**. Un match por firma, sin dueño, le robaría un disco
a un personaje para dárselo a otro — en silencio.

Así que el arreglo **no** podía ser "guardalo igual y ya".

## 3. Cómo quedó

El disco se persiste con la **forma** de un libre —`agente_asignado = NULL`, `equipado = 0`— pero
**marcado** en `notas`:

```
dueno_no_identificado_2026-08-21
```

Misma convención que `no_visto_en_censo_<fecha>` (`census_store`) y `declarado_por_usuario_<fecha>`
(`roster_declaration`): el formato ya existía, no se inventó uno nuevo.

### La marca no es un comentario: es funcional

Acá está el punto que hace que el cambio valga.

En la tabla, una fila marcada y un disco genuinamente libre **se ven idénticos**: los dos tienen
`agente_asignado` NULL y `equipado` 0. La marca es lo único que los separa — y por eso
`_persist_disco_libre` pasó de dos buckets a **tres**:

```
ocupados   agente_asignado IS NOT NULL
marcadas   NULL  +  la marca      ← alguien lo tiene, no sabemos quién
libres     NULL  sin la marca     ← nadie lo tiene
```

Cada lectura busca a los de su clase: incierta ↔ `marcadas`, libre ↔ `libres`.

Sin ese split, el próximo disco genuinamente libre con la misma identidad haría
`update_from_parsed` sobre la fila marcada y **fusionaría dos discos distintos en una sola fila**,
sin ruido. Es exactamente el modo de falla que el split libres/ocupados ya existía para evitar,
apareciendo por una puerta nueva.

## 4. El test que importa

Doce tests en `test_sync_disco_libre.py`, pero once son andamiaje. El que sostiene el diseño es:

```
test_una_fila_MARCADA_no_es_pisada_por_un_libre_genuino
```

**Saboteado a propósito** —devolviendo las marcadas al bucket de libres con
`mismos = marcadas if dueno_incierto else (libres + marcadas)`— falla **ese test y sólo ese**. Los
otros once no distinguen las dos implementaciones: sin él, la marca sería decorativa y nadie se
enteraría (regla **A3**).

El segundo con dientes es el de no-regresión: `test_sin_señal_de_badge_SIGUE_sin_escribirse`. La
puerta nueva no podía abrirle paso al caso que sí hay que descartar.

## 5. Lo que este cambio NO hace

**No baja la abstención.** Con la librería repuesta el descriptor se abstiene el **4,3 %** de las
veces — unos 17 discos sobre 405. Este cambio hace que esos 17 dejen de perderse; averiguar por qué
Manato no se pudo nombrar es otra investigación, con `DANIBOD_LOG_DEBUG=1`.

**No arregla el tercer disco perdido de los tres.** Ese cayó por un nombre de set irresoluble
(`Nana cenicienta` por `Nana a la luz cenicienta`). Sin `set_id` no hay fila que insertar —es clave
foránea—, así que el arreglo es otro: ampliar el resolvedor difuso. Se anota, no se hace acá.

---

## Lo que me llevo

**Un cajón de "todo lo demás" esconde una distinción.** El `else` que descartaba juntaba *no leí
nada* con *leí todo menos una cosa*. Los dos llegaban ahí por la misma condición —`agente_id is
None`— y por eso la diferencia era invisible desde el código: había que mirar **qué evidencia
tenía el badge**, no qué devolvió el resolvedor.

**Y una marca sin consecuencia es un comentario.** Si `_es_dueno_incierto` no cambiara a quién
puede pisar la fila, escribirla en `notas` sería documentación adentro de la base de datos. El
valor no está en la marca: está en el tercer bucket.

---

**Archivos:** `app/core/sync_equip.py` · `app/core/monitor.py` (`_assign_s9_owner`) ·
`app/core/parser_disc.py` · `app/core/parser_disc_s17.py` · `app/db/repositories.py` ·
`app/tests/unit/test_sync_disco_libre.py`.

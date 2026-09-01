# Censo de discos — cierre de la pasada del 2026-08-30

**383 discos capturados.** La pasada arrancó de cero (`inventory_discs` vaciado a las 21:42) y se
cerró a las 23:53.

```
integrity_check     ok
foreign_key_check   0 violaciones
snapshot            audit/danibod_zzz_v2.censo_discos_20260830.db   (verificado bit a bit)
respaldo runtime    db/danibod_zzz_v2.backup_censo_discos_cerrado_20260830_235313.db
```

## 1. Qué se capturó

| | |
|---|---|
| con dueño | **299** |
| libres | **79** |
| dueño incierto (marcado) | **5** |

Los 5 marcados son discos que **antes de agosto se habrían perdido enteros**: se leyeron bien set,
slot, nivel, main y los cuatro substats, y sólo faltó el nombre del dueño.

| id | slot | set | main |
|---|---|---|---|
| 120 | 3 | Fábula Yunkui | DEF |
| 127 | 5 | Fábula Yunkui | Bono Daño Éter |
| 171 | 4 | Balada de la rama y la espada | Prob. Crítica |
| 266 | 6 | Tecno Pícido | Impacto |
| 301 | 2 | Blues Libre | ATK |

## 2. Cobertura del roster

**43 de 51 PJs quedaron con los 6 slots.** Ninguno quedó sin ningún disco.

| PJ | slots | faltan |
|---|---|---|
| Alice · Corin · Ju Fufu · N.º 0: Anby · Nekomata · Orfia y Magas · Yixuan | 5/6 | uno cada uno |
| **Harumasa** | **4/6** | **slots 1 y 5** |

## 3. ⚠️ Dos discos mal asignados, y la DB sola los delata

Un PJ **no puede** tener dos discos en el mismo slot. Hay exactamente dos casos, **los dos en
Antón**:

```
Antón slot 1:  id=281 Disco Sacudestrellas      +  id=355 Metal Eléctrico
Antón slot 5:  id=259 Tecno Pícido              +  id=339 Metal Eléctrico
```

Y Harumasa —el PJ más incompleto— es justo al que le faltan **los slots 1 y 5**.

Su build actual:

```
Harumasa   slot 2  Metal Eléctrico
           slot 3  Metal Eléctrico
           slot 4  Tecno Pícido
           slot 6  Tecno Pícido
```

Dos piezas de Metal Eléctrico, y las dos duplicadas de Antón son **de Metal Eléctrico**. Devolverle
`id=355` (slot 1) y `id=339` (slot 5) le arma un **4pc Metal Eléctrico + 2pc Tecno Pícido**, que es
una build coherente, y deja a Antón sin duplicados.

**Sugerido, no aplicado** — hay que confirmarlo en pantalla antes de escribir (RNF-02). Lo que sí
está probado es que el estado actual es imposible: los duplicados no pueden existir en el juego.

### De dónde salieron

> ⚠️ **CORREGIDO el 2026-09-01.** No salieron del desempate. El log los tiene asignados por
> `match directo` —el matcher de la grilla resolviendo solo, sin tiebreaker— a las 23:39:11 con
> conf 0.91. Tres frames antes, el mismo par se daba vuelta (0.86/0.85, 0.87/0.85, 0.87/0.86) y
> las tres veces se abstuvo; la cuarta salió con margen suficiente y escribió. Es una lotería de
> frames entre dos clases que el descriptor no separa, y sigue abierta. Detalle en
> [`Dev_IA/2026-09-01_FIX_Dos_umbrales_absolutos_donde_manda_el_margen.md`](../Documentacion/Dev_IA/2026-09-01_FIX_Dos_umbrales_absolutos_donde_manda_el_margen.md).
>
> El desempate SÍ escribió mal en otro disco (`id=268`, que después se corrigió solo) y dejó uno
> en pie: **`id=254`**, promovido a Antón por encima de Manato. Sumarlo a lo que hay que mirar.

Del desempate por build, documentado en
[`bug_desempate_por_build_durante_censo_20260830.md`](./bug_desempate_por_build_durante_censo_20260830.md).
Antón y Harumasa son indistinguibles para el descriptor en la grilla (se dan vuelta entre frames,
margen 0.00-0.03), y el desempate promovió al top-2 apoyándose en "quién corre este set" — un dato
que leyó de la tabla que el censo estaba construyendo.

## 4. El resolvedor difuso de nombres de set

De **433 detecciones, 415 persistieron**. Las 18 restantes vienen de sólo **dos** lecturas que el
resolvedor nunca acepta:

| lectura | veces | mejor candidato | ratio | margen al 2º |
|---|---|---|---|---|
| `Melodia Faett` | 15 | Melodía de Faetón | 0.8148 | **0.3603** |
| `Metalcolmilluda (i)` | 3 | Metal Colmilludo | 0.8485 | **0.2771** |

Las dos quedan por debajo del cutoff de **0.86**, y las dos son **inequívocas**: el segundo
candidato está a 0.28-0.36 de distancia. Es el mismo error estructural que el guard de identidad —
un umbral **absoluto** donde la señal que discrimina es el **margen**.

Simulado sobre las 60 lecturas del censo, una regla de margen (`ratio ≥ 0.80` **y** margen ≥ 0.15)
aceptaría 18 detecciones más, y **ninguna lectura del corpus tiene dos candidatos cerca**: cuando
hay un match bueno, el segundo está lejísimos.

**No se perdió ningún disco por esto**: Melodía de Faetón tiene 18 discos en la DB y Metal
Colmilludo 15. El agregador reintenta hasta que sale una lectura buena. El costo fue **tiempo** —
hasta 4 intentos y ~45 s para un disco.

⚠️ **CORREGIDO el 2026-09-01.** Acá decía que `Blues libre Precdom` resuelve por "el matcher de
logos". No: resuelve por el atajo de **substring** del propio resolvedor de texto (`blueslibre`
está contenido en `blueslibreprecdom`). Y no es un caso raro — **57 de las 89 lecturas** del corpus
entran por ahí, contra 9 por difflib. El cutoff gobierna el 10 % del camino, no el 100 %.

Medido y calibrado a `0.75 / 0.12` con `tools/measure_set_resolver.py`.

## 5. Conclusión

La pasada salió **limpia**. Las tres cosas que se arreglaron durante el censo se ven en el
resultado:

- **el disco sin dueño ya no se pierde** — 5 rescatados que antes se descartaban enteros;
- **el gemelo re-arma** — no hubo trabas de las que costaban 29 s;
- **el guard por superficie** — Soukaku y Manato se nombran solos desde que se aplicó.

Lo que queda:

1. **Confirmar en pantalla** los slots 1 y 5 de Harumasa y corregir las dos filas. Es la única
   inconsistencia dura de los 383 discos.
2. **Revisar los 7 PJs a 5/6**: puede ser que el slot falte de verdad, o que ese disco esté entre
   los 5 marcados o los 79 libres.
3. ~~**Desactivar la promoción del top-2 mientras haya un censo abierto**~~ — hecho el
   2026-09-01. No era la causa de (1), pero sí de otro error real (`id=254`).
4. ~~**Regla de margen en el resolvedor de sets**~~ — hecho el 2026-09-01 (`0.75 / 0.12`).

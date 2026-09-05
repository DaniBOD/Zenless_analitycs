# Adopción de la fila marcada — verificación en vivo, y la cola que dejó

**2026-09-05.** Primera vez que el arreglo de `a9a6dcd` corre contra el juego, sobre el mismo caso
que lo motivó.

## Funcionó

```
01:21:01  ADOPTADO: id=127 estaba sin dueño y marcado — ahora es de 'Yixuan' (slot 5)
01:21:01  S17 persistido id=127 s17_adopta ... · 6/6 · estándar 4+2
```

| | |
|---|---|
| id | **127**, no una fila nueva |
| trigger | **`s17_adopta`** |
| total de discos | **383** — ninguna alta |
| `fecha_obtencion` | 2026-08-31 02:51, la original |
| Yixuan | **6/6 · estándar 4+2** |

El 2026-09-01, con el mismo recorrido, esto había insertado `id=384`.

## La cola: la marca sobrevivió a su propia condición

La fila quedó con `notas = 'dueno_no_identificado_2026-08-30'` **después** de recibir dueño. La
marca AFIRMA *"alguien lo tiene y no pude leer quién"*, y eso dejó de ser cierto en el momento en
que se leyó el dueño.

No es peligroso —la adopción exige `agente_asignado IS NULL`, así que la fila no se puede volver a
adoptar— pero **envenena el contador de inciertos**, que es justo el número que dice cuántos discos
quedan por reconciliar: decía 5 cuando eran 4, y no iba a bajar nunca. Un contador que no puede
llegar a cero no sirve para saber cuándo terminaste.

### Arreglo

- `_sin_marca_dueno_incierto()` saca **el token, no el campo**: otros flujos concatenan sus marcas
  con `' | '` (`no_visto_en_censo_<fecha>`, `declarado_por_usuario_<fecha>`) y vaciar `notas` se
  llevaría puesto lo que dijo otro.
- `InventoryDiscRepo.limpiar_marca_dueno_incierto()`, llamada desde la rama de adopción.
- 10 tests: 7 parametrizados sobre la función pura + 2 de integración. Verificado rompiendo la
  llamada a propósito: los dos de integración caen.
- Migración `2026-09-05_22` para la única fila que quedó en ese estado (verificado por consulta:
  `id=127` era la única con marca **y** con dueño).

### Verificación de la migración

```
backup        db/danibod_zzz_v2.backup_premig_20260905_013437.db
expected_0    marcados CON dueño                        0  ✓
expected_4    marcados en total                         4  ✓
expected_1    la 127 con dueño, equipado y su fecha      1  ✓
expected_383  total de discos                         383  ✓
expected_6    slots equipados de Yixuan                 6  ✓
foreign_key_check   0 violaciones
integrity_check     ok
```

Ensayada antes contra una copia, con los mismos cinco resultados.

## Lo que queda

Los 4 marcados que siguen — `120` (s3 Fábula Yunkui), `171` (s4 Balada), `266` (s6 Tecno Pícido),
`301` (s2 Blues Libre) — se reconcilian solos pasando por el PJ que los tiene, ya sin duplicar y
ya sin dejar la marca vencida. Ahora el contador sí puede llegar a cero.

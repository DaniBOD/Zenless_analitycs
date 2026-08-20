# Dos worktrees escribieron la misma primitiva sin verse — y las dos tenían razón

> **2026-08-20.** Cierra la serie que abren
> [`2026-08-19_FIX_Unicidad_de_nombres_en_audit.md`](./2026-08-19_FIX_Unicidad_de_nombres_en_audit.md)
> y [`2026-08-20_FIX_Unicidad_del_backup_RNF-01.md`](./2026-08-20_FIX_Unicidad_del_backup_RNF-01.md).
>
> Los dos arreglos salieron de worktrees paralelos que **no se veían**. Cuando se los puso lado a
> lado, tenían la misma primitiva escrita dos veces, con docstrings casi calcados. Es la regla
> **B1** ocurriendo en vivo, tres días después de escribirla.

---

## 1. Lo que había, por duplicado

| | `audit_paths.reservar_rutas` | `db.connection.respaldar_db` |
|---|---|---|
| primitiva | `O_CREAT \| O_EXCL` | `O_CREAT \| O_EXCL` |
| tope | `_MAX_INTENTOS = 1000` | `_MAX_INTENTOS = 1000` |
| reintento | sufijo `_2`, `_3`… | sufijo `_2`, `_3`… |
| al agotarse | `raise FileExistsError` | `raise FileExistsError` |

Dos módulos, dos constantes con el mismo nombre y el mismo valor, dos lazos idénticos. Si mañana
alguien cambia el tope, lo cambia en uno.

## 2. Por qué NO era una duplicación pura

Acá está lo que hace interesante el caso: **divergían en un punto, y los dos estaban en lo
correcto**.

| | si algo falla entre la reserva y la escritura real |
|---|---|
| `audit/` | **deja** el archivo de 0 bytes |
| respaldos | **borra** la reserva |

El razonamiento de cada uno, textual:

> *(audit)* ruido visible, y estrictamente mejor que el modo de falla que reemplaza — una tanda de
> auditoría pisada en silencio.

> *(backups)* un `.db` vacío con nombre de backup es peor que ningún archivo, porque **parece un
> respaldo del que se podría restaurar**.

Los dos tienen razón porque el archivo significa cosas distintas. De `audit/` nadie restaura: un
archivo vacío ahí es una molestia que se ve. De un backup sí se restaura: un archivo vacío ahí es
una trampa.

**Conclusión:** no eran dos primitivas. Era **una primitiva con dos políticas** — y colapsarlas a
la fuerza habría borrado una distinción real, que es el otro modo de fallar la regla B1.

## 3. Cómo quedó

`app/core/unique_paths.py` es ahora la única autoridad sobre *cómo se consigue un nombre libre*:

```
candidatos_numerados(carpeta, base, extensiones)  →  base.ext, base_2.ext, base_3.ext…
reservar(candidatos)                              →  el primer juego que se pueda crear ENTERO
```

La **política se queda en cada llamador**, que es quien sabe qué significa su archivo.
`reservar_rutas` y `respaldar_db` sobreviven como las caras públicas de siempre; por dentro las dos
llaman a lo mismo.

### El todo-o-nada, que sólo uno de los dos necesitaba

El censo escribe `.json` y `.md` bajo el mismo sello. Si dos corridas pudieran repartirse el par,
cada reporte quedaría a medias **pareciendo completo**. Por eso `reservar` toma el juego entero o
suelta lo ya creado y pasa al número siguiente. `respaldar_db` pide un solo archivo y no lo nota —
pero la garantía es de la primitiva, no de un llamador.

### El tope dejó de ser un default de parámetro

Estaba como `max_intentos: int = MAX_INTENTOS`. Un valor por defecto **se evalúa al importar**, así
que quedaba una copia congelada y la constante dejaba de ser la autoridad (además de volverla
imparcheable desde un test). Ahora se resuelve dentro de la función. Es la misma regla B1, aplicada
a una constante.

## 4. La validación: los tests de cada uno como especificación del otro

El refactor no se verificó con tests nuevos míos, sino con **los tests que cada worktree escribió
contra su propia implementación**. Si la versión unificada pasa los dos juegos, preservó las dos
conductas — que es exactamente lo que había que probar.

```
66 passed   (test_unique_paths + test_db_backup + test_census_cierre
             + test_desmontaje_audit + test_roster_declaration)
```

Los únicos dos tests que hubo que tocar apuntaban a `_MAX_INTENTOS` en su módulo viejo. No es una
regresión de conducta: es el precio de mover la constante, y se ve de una.

### El test que le puse a la primitiva

`test_es_ATOMICA_no_un_mira_y_despues_escribe` simula un intruso que gana la carrera **justo
después** de que el candidato se vio libre. Saboteado a propósito —cambiando `O_EXCL` por un
`if ruta.exists()`— falla ese test y **sólo ese**: los otros nueve no distinguen las dos
implementaciones. Un test sin dientes acá habría dejado pasar exactamente el bug que originó todo.

## 5. La pasada completa: 13 sitios, no 2

Ninguno de los dos worktrees cubría todo el patrón. Se hizo la pasada entera:

| sitio | qué era |
|---|---|
| `teardown_batch.py` · `census.py` | bitácoras — *worktree A* |
| `census_store.py` · `roster_declaration.py` | respaldos RNF-01 — *worktree B* |
| `ui/controller.py` | **backup de sesión**, código de producción, sin dueño |
| `monitor.py` (dump S23) | **dos bugs en cuatro líneas** — ver abajo |
| `monitor.py` (frames de debug) | la confianza en el nombre da entropía, no unicidad |
| `scripts/qa/apply_migration.py` | el backup pre-migración: la red de RNF-01 |
| `scripts/{restandarize,score_existing,seed_substat}.py` | ídem |
| `scripts/rebuild_account_db.py` | caso aparte, ver abajo |

**El dump S23 tenía un segundo bug de regalo:** usaba `Path("audit")` **relativo al CWD**. En el
`.exe` el CWD es el del acceso directo, así que el dump de diagnóstico caía en cualquier parte, o
no caía. El docstring de `audit_paths` ya lo mencionaba como el único precedente sin arreglar —
llevaba meses ahí. Un dump que no se escribe se ve igual que un dump que no hizo falta (regla A2).

**`rebuild_account_db` es el caso interesante:** el sello nombra **dos cosas correlacionadas en
carpetas distintas** — la DB nueva y el reporte que la describe. Se reserva la que tiene datos y el
nombre del reporte se **deriva** del que la DB terminó tomando, así el reporte sigue nombrando a su
DB aunque haya habido colisión. Reservar los dos por separado habría podido darles números
distintos, que es peor que el problema original.

---

## Lo que me llevo

**B1 no se cumple por escribirla.** El doc de prácticas se commiteó el 2026-08-19 y al día
siguiente dos agentes duplicaron una primitiva. No fue por no leerlo: fue porque **ninguno de los
dos podía ver el trabajo del otro**. La regla necesita un mecanismo, no sólo un enunciado — acá el
mecanismo fue que alguien mirara los dos worktrees antes del merge.

**Y colapsar no siempre es unificar.** La tentación era quedarse con una de las dos políticas de
falla. Habría sido "una sola autoridad" y habría estado mal: la diferencia codificaba que un
archivo de `audit/` y un `.db` de backup no significan lo mismo cuando están vacíos.

---

**Archivos:** `app/core/unique_paths.py` (nuevo) · `app/core/audit_paths.py` ·
`app/db/connection.py` · `app/core/{teardown_batch,census,census_store,roster_declaration,monitor}.py` ·
`app/ui/controller.py` · `app/scripts/{qa/apply_migration,rebuild_account_db,restandarize_inventory_discs,score_existing_inventory,seed_substat_preferences}.py` ·
`app/tests/conftest.py` · `app/tests/unit/test_unique_paths.py` (nuevo).

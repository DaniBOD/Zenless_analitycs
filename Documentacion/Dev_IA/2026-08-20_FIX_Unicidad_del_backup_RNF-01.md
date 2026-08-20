# El backup que probaba el estado previo — y el segundo F8 que se lo llevaba puesto

> **2026-08-20.** Cierra el punto que
> [`2026-08-19_FIX_Unicidad_de_nombres_en_audit.md`](./2026-08-19_FIX_Unicidad_de_nombres_en_audit.md)
> §6 dejó *"señalado, sin tocar"*: `census_store.py:313` y `roster_declaration.py:277` arman el
> nombre del backup de la DB de dominio con un sello **al segundo**. Aquel doc estimó la exposición
> como *"mucho menor: las dos las dispara una acción humana que ocurre una vez"*, y lo dijo con
> todas las letras: **no medido**.
>
> Medido. La estimación era optimista por una razón que no estaba a la vista: la acción humana
> ocurre una vez, pero **el sistema la escucha dos veces**.

---

## 1. Lo que había

```python
# app/core/census_store.py:313  y  app/core/roster_declaration.py:277
sello = datetime.now().strftime("%Y%m%d_%H%M%S")          # granularidad de SEGUNDO
backup = destino.with_name(f"{destino.stem}.backup_precenso_{sello}.db")
shutil.copy2(destino, backup)                              # pisa el destino sin preguntar
```

## 2. Primero: qué NO era alcanzable

El pedido era medir antes de arreglar (A1), así que el primer trabajo fue buscar el camino, no
escribirlo.

| camino | veredicto |
|---|---|
| `declarar()` ← `RosterDeclarationDialog._guardar` ← botón del panel Roster | **no alcanzable**. Un `dlg.exec()` modal por acción; en el único camino que no escribe (`escribio=False`) el backup ni se llega a crear, porque las guardas de readonly y de DB inexistente están *antes* del `copy2`. Reabrir el diálogo y volver a guardar dentro del mismo segundo no lo hace un humano. |
| dos `marcar_huerfanos_en_dominio` **secuenciales** | no existe: el único llamador es `Monitor.cerrar_censo`, y llama una vez. |
| `cerrar_censo_discos()` (que `cerrar_censo` invoca primero) | no toca la DB de dominio — no hace backup. |
| pasada sin huérfanos | `marcar_huerfanos_en_dominio([])` corta antes del backup. **El backup sólo existe cuando hay huérfanos**, y eso importa para lo que sigue. |

## 3. La ventana que sí existe, y por qué el debounce no la cubre

`HotkeyManager._fire` marca el debounce y **suelta el lock antes de invocar la callback**:

```python
with self._lock:
    if now - last < self._debounce_s: return          # _debounce_s = 0.25
    self._last_fire[name] = now
    callbacks = list(self._handlers[name])
for cb in callbacks:                                   # ← fuera del lock
    cb()
```

Eso protege contra que **un mismo press físico** se procese dos veces (los dos backends —Win32
RegisterHotKey y pynput— corren en simultáneo, cada uno en su hilo). No protege contra que la
callback se re-entre: dos presses separados por más de 0,25 s corren **concurrentes**.

¿Alcanza 0,25 s para entrar en el medio? La ventana la pone `RosterCensus.cerrar()`, que baja
`_abierta` **después** de persistir cada huérfano, y `CensusStore.guardar_fila` abre conexión,
corre el DDL entero, inserta, commitea y cierra — una vez por fila:

| huérfanos | ventana (guard → `_abierta = False`) p50 | min | max |
|---:|---:|---:|---:|
| 4 | 37,0 ms | 30,7 | 53,1 |
| 10 | 79,2 ms | 71,2 | 117,6 |
| 25 | 194,8 ms | 179,0 | 209,9 |
| **51** (el roster real) | **357,1 ms** | 330,0 | 439,2 |

357 ms > 250 ms de debounce. La re-entrada es real y está **medida sobre el código de
producción**: un tercer F8 entra a `cerrar_censo` mientras el segundo sigue adentro, y se lo ve
leer la lista a mitad de mutación (`faltan 10 sin ver` cuando eran 51).

## 4. Lo que lo frenaba era un guard de otra cosa

Barrido sistemático del tercer F8 sobre toda la ventana (offsets 250→700 ms, paso 10 ms, 3
repeticiones = 138 corridas): **0 colisiones**. Un nulo sin mecanismo es suerte, así que se
instrumentó dónde muere el tercer press:

```
confirmacion re-armada: 17 / 17
```

Nunca lo frena `censo.abierta`, ni el gate de idempotencia de `cerrar()`. Lo frena
`_confirmar_cierre_parcial`, que existe **para otra cosa**: para que no se declaren 49 huérfanos
sin querer. Y funciona como interlock por una coincidencia exacta —
`pendientes = filas(PENDIENTE, en_db=True)` es *exactamente* el conjunto que se convierte en
huérfanos — así que "hay backup que hacer" ⟹ "hay pendientes" ⟹ "hace falta confirmar de nuevo".

Cuánto pesa ese guard accidental, contrafáctico con él neutralizado y nada más:

| corridas | dos backups pedidos | colapsaron en un archivo | el superviviente ya no es el estado previo |
|---:|---:|---:|---:|
| 40 | 39 | 39 | **39** |

## 5. El camino que sí llega: parar y volver a arrancar el monitor

`Monitor.stop()` para el hilo, saca el handler de log y vuelca métricas. **No para el
`HotkeyManager`** (que tiene su `stop()`, sin llamador). `Controller.stop()` hace
`self._monitor = None`, y el siguiente `start()` construye un Monitor nuevo que registra **otro**
HotkeyManager. El viejo sigue vivo: sus dos backends siguen enganchados y su callback mantiene
referenciado al Monitor muerto.

Lo dispara el usuario desde el panel en vivo — `main.py:571-572` conecta
`start_monitor_requested`/`stop_monitor_requested` — y también el entorno de QA
(`DANIBOD_AUTO_STOP_ON_WINDOW_LOST`).

A partir de ahí no hace falta ninguna carrera fina:

- cada manager tiene **su propio** `_last_fire` ⇒ un solo F8 físico dispara los dos, sin debounce
  entre ellos;
- cada Monitor tiene **su propio** `_cierre_pedido_ts` ⇒ los dos avisan, y al segundo F8 los dos
  confirman;
- cada `start()` reabre el censo, así que hay **dos `RosterCensus` distintos restaurados de la
  misma corrida** (`run_id` 1 y 1), los dos `abierta` ⇒ el gate de idempotencia de `cerrar()` no
  ve nada raro: cada objeto se cierra una sola vez.

Repro, con `Monitor.stop()` real:

```
tras Monitor.stop():   el HotkeyManager sigue referenciado: True
                       misma corrida restaurada: run_id A=1 B=1   ambas abiertas: A=True B=True
--- F8 #1 ---  (los dos avisan)
--- F8 #2 ---  (los dos cierran)
archivos de backup en disco: 1
   danibod_zzz_v2.backup_precenso_20260820_001027.db
      sha256 70314be92ee9e212  == estado previo? False
sha256 del estado PREVIO real: 3c9c3583d79a06ab
```

## 6. El daño no es "un backup menos"

Los dos respaldos **no son intercambiables**. El primero es el estado previo. El segundo se copia
*después* de que el primer cierre ya escribió las notas de huérfano. `copy2` pisa sin error, sin
warning y sin archivo de más: lo que queda archivado con nombre `backup_precenso` es un estado
**posterior a la escritura**, y no hay nada en el disco que lo delate.

Es peor que el caso de `audit/` que cerró el doc anterior. Allá se perdía una bitácora. Acá se
pierde, en silencio, la única evidencia con la que RNF-01 permite volver atrás — y se pierde
precisamente el día en que el censo escribió el dominio, que es el único día en que importa.

## 7. El arreglo

Autoridad única en `app/db/connection.py`, que ya es el módulo que responde "dónde está la DB" y
"¿se puede escribir?" (`is_readonly`). Ahora responde también "con qué nombre se la respalda":

```python
respaldar_db(destino, etiqueta) -> Path        # <stem>.backup_<etiqueta>_<sello>[_N].db
```

No fue a `audit_paths.py`: un backup vive **al lado de la DB**, no en `audit/`, y su nombre sigue
otra convención. Comparte la idea de `reservar_rutas`, no el código.

Tres decisiones, y en qué se aparta del precedente:

- **El sello se queda al segundo.** Es para que un humano ubique la copia en su día, y lo comparte
  con `backup_premig_` de `apply_migration` y con CLAUDE.md §3.1. Lo que no puede quedar colgado
  de él es la unicidad. Sobre colisión: `_2`, `_3`, …
- **`O_CREAT | O_EXCL`, no `if existe`.** Preguntar y después escribir son dos pasos, y entre medio
  cabe otro escritor — que acá no es hipotético: **son literalmente dos hilos del mismo proceso**.
  Reservar con un archivo de 0 bytes antes de `copy2` es correcto justamente porque `copy2` pisa
  el destino: pisar la reserva propia es lo que queremos.
- **Si `copy2` falla, se borra la reserva** — al revés que en `audit/`. Allá un archivo vacío es
  ruido visible y nadie restaura de él; acá un `.db` de 0 bytes con nombre de backup *parece* un
  respaldo. Y agotar la cota **levanta**: sin backup no se escribe al dominio.

## 8. Cómo se verificó

| verificación | resultado |
|---|---|
| RED con `reloj_de_pared_congelado` (2 tests, uno por call site) | fallan 2/2 antes del arreglo, por el motivo correcto (1 archivo, no 2) |
| Mutante 1: reserva sin `O_EXCL` | caen 5 tests |
| Mutante 2: sin sufijo `_2`/`_3` | caen 7 (incluidos 2 preexistentes: el fallo pasa a ser *cerrado*) |
| Mutante 3: sin limpiar la reserva si `copy2` falla | cae 1 test, y sólo ese |
| Mutante 4: al agotar la cota devuelve en vez de levantar | cae 1 test, y sólo ese |
| Repro de campo (dos HotkeyManager, un F8) | 2 archivos; el primero **byte a byte** igual al estado previo |

Los mutantes no son opcionales: un test que nunca vio fallar el código no prueba que lo esté
mirando (A3).

## 9. Lo que queda señalado, sin tocar (E3)

1. **`Monitor.stop()` no para el `HotkeyManager`** — es la causa raíz de la doble llamada, y
   sobrevive a este arreglo. Con el backup ya a salvo, lo que queda es que un F8 (y F9, y F10)
   se ejecuten N veces después de N ciclos de parar/arrancar. `HotkeyManager.stop()` ya existe y
   no tiene llamador. **Un cambio por vez, y éste pide su propio QA en vivo.**
2. **Otros que arman nombre de backup con el mismo patrón**, no medidos:
   `app/ui/controller.py:669` (`backup_session_`, código de producción),
   `app/scripts/qa/apply_migration.py:83`, `app/scripts/{restandarize_inventory_discs,
   score_existing_inventory,seed_substat_preferences}.py`, `tools/apply_migration_0{8,9}.py`.
   Todos pueden pasar a `respaldar_db` cuando se los toque.

---

**Archivos:** `app/db/connection.py` (+`respaldar_db`) · `app/core/census_store.py` ·
`app/core/roster_declaration.py` · `app/tests/conftest.py` (fixture
`reloj_de_pared_congelado`) · `app/tests/unit/test_db_backup.py` (nuevo) ·
`app/tests/unit/test_census_cierre.py` · `app/tests/unit/test_roster_declaration.py`.

# El flake que era pérdida de datos: el reloj no es un discriminador

> **2026-08-19.** Cierra el hilo que quedó abierto en
> [`2026-08-19_DIAG_Classify...`](./2026-08-19_DIAG_Classify_el_costo_lo_pone_el_frame.md) §"Un
> flake ajeno": `test_dos_tandas_no_se_pisan` fallaba ~1 de cada 30 corridas. No era un test
> nervioso — era el síntoma barato de una pérdida de datos de auditoría en producción.

---

## 1. El código

```python
# app/core/teardown_batch.py:376
# Marca con microsegundos: dos tandas seguidas no pueden pisarse.
nombre = f"{datetime.now():%Y%m%d_%H%M%S_%f}_desmontaje.json"
```

El comentario afirma lo contrario de lo que el código garantiza. `%f` imprime microsegundos, pero
**imprimir seis dígitos no es medir seis dígitos**: el reloj solo separa dos escrituras si alcanza
a avanzar entre una y otra.

Idéntico en `app/core/census.py:502` (`_censo_roster`, par `.json` + `.md`).

## 2. Por qué el reloj no alcanza — y por qué el número no es nuestro

En Windows `datetime.now()` lee `GetSystemTimeAsFileTime`. Su granularidad **no es una propiedad
de la app ni del lenguaje: es una propiedad global y mutable del sistema.**

```
NtQueryTimerResolution (esta máquina, 2026-08-19)
  máxima (por defecto):   15.625 ms
  mínima (mejor posible):  0.5   ms
  ACTUAL:                  1.0   ms   ← la sostiene OTRO proceso con timeBeginPeriod
```

Es la misma trampa que ya dejó [`thread_time` en Windows](./00_Practicas_Aprendidas.md): la API
*declara* `resolution=1e-07` y *avanza* de a un tick del scheduler. Acá `%f` declara microsegundos
y el reloj avanza de a un tick del timer global.

Medido, con el timer global en 1,0 ms:

| escritura | dura | colisión en 2 llamadas seguidas |
|---|---|---|
| `write_teardown_record` | ≈0,96 ms | **14 %** (56/400) |
| `write_census_report` | ≈1,73 ms | **1 %** (2/200) |

El censo colisiona menos **solo porque tarda más** — no porque esté mejor escrito. Y la lectura
importante es al revés: en un equipo donde nadie subió el timer, el tick es 15,625 ms y **las dos
colisionan casi siempre**. Que hoy funcione está prestado de un proceso ajeno que el usuario
podría cerrar.

## 3. El daño real no es el nombre repetido

`os.replace` pisa sin preguntar: ese es su propósito. Dos tandas con el mismo nombre no producen
error, ni warning, ni archivo extra — producen **una tanda de auditoría menos**, en silencio. La
bitácora es lo único que el desmontaje deja detrás (no toca la DB): perderla no se recupera.

El test viejo tampoco medía eso. Escribía el mismo registro dos veces y comparaba **nombres**; con
contenido idéntico, ni siquiera habría notado el pisón. Un test así mide qué tenía abierto el
usuario, no el código.

## 4. El arreglo

Una autoridad única en `app/core/audit_paths.py` — el módulo que ya respondía "dónde va un
artefacto de `audit/`" — que ahora responde también "con qué nombre, sin pisar a nadie":

```python
reservar_rutas(carpeta, etiqueta, extensiones=("json",)) -> list[Path]
```

Tres decisiones, y el porqué de cada una:

- **El sello se queda.** Es para que un humano ubique la corrida en su día. Lo que no puede quedar
  colgado de él es la unicidad. Sobre colisión: `_2`, `_3`, …
- **`O_CREAT | O_EXCL`, no `if destino.exists()`.** Preguntar y después escribir son dos pasos y
  entre medio cabe otro escritor. `O_EXCL` crea *solo si no existe* en un paso indivisible del SO:
  el que pierde la carrera recibe `FileExistsError` y prueba el número siguiente. Vale entre hilos
  y entre procesos (el `.exe` corriendo mientras un script de QA escribe en la misma carpeta).
- **El juego de hermanos se toma entero o ninguno.** El censo escribe `.json` y `.md` bajo un mismo
  sello; si un solo hermano está ocupado se sueltan los ya creados y se pasa al siguiente. Si no,
  dos corridas podrían repartirse el par y quedar cada reporte con la mitad del otro.

La reserva deja un archivo de 0 bytes que el escritor pisa enseguida. Si el proceso muere en el
medio queda un vacío: ruido **visible**, y estrictamente mejor que el modo de falla que reemplaza.

## 5. Cómo se verificó (y por qué el bucle no alcanzaba)

El pedido era correr el test 30+ veces, no una. Pero un bucle sobre un test probabilístico sigue
midiendo suerte: con el timer en 1 ms, 40 corridas verdes son perfectamente compatibles con el bug
intacto. **Primero había que sacar el azar del test.**

`reloj_de_pared_congelado` (fixture en `conftest.py`) congela `datetime.now()` en los tres módulos.
Congelar es llevar "dentro del mismo tick" a su límite — que es exactamente lo que pasa en un
equipo con el timer por defecto. Con eso el test falla **siempre** antes del arreglo, no a veces.

| verificación | resultado |
|---|---|
| RED con reloj congelado (3 tests nuevos) | fallan 3/3 antes del arreglo |
| Mutante 1: reserva sin `O_EXCL` | 6 tests caen |
| Mutante 2: sin rollback de hermanos | cae el test de hermanos, y solo ese |
| Mutante 3: no levanta al agotar intentos | cae el test de la cota, y solo ese |
| 500 escrituras seguidas, reloj real | 500 nombres distintos, 0 `.tmp`, 0 vacíos, 500 registros íntegros |
| 40 corridas aisladas de ambos archivos | 0 fallos |
| Suite completa | 1818 passed, 471 skipped |

Los mutantes son la parte que no se puede saltear: un test que nunca vio fallar el código no prueba
que lo esté mirando (A3 — verificar el efecto, no la intención).

## 6. Lo que queda señalado, sin tocar

`census_store.py:313` y `roster_declaration.py:277` arman el nombre del **backup de la DB** con
`%Y%m%d_%H%M%S` — granularidad de **segundo**, sin microsegundos siquiera:

```python
backup = destino.with_name(f"{destino.stem}.backup_precenso_{sello}.db")
```

Misma clase de defecto y consecuencia peor (es el backup de RNF-01, el que prueba el estado previo
a una escritura al dominio), pero exposición mucho menor: las dos las dispara una acción humana que
ocurre una vez. **No medido, no arreglado acá** — un cambio por vez (E3).

---

**Archivos:** `app/core/audit_paths.py` (+`reservar_rutas`) · `app/core/teardown_batch.py` ·
`app/core/census.py` · `app/tests/conftest.py` (fixture) ·
`app/tests/unit/test_desmontaje_audit.py` · `app/tests/unit/test_census_cierre.py`.

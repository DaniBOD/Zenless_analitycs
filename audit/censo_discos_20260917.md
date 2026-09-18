# Censo de discos — pasada completa del 2026-09-17

**Fase 4** de la hoja de ruta del log en S9. Pasada en vivo hecha por Daniel con la app
**escribiendo** (`qa_launch.ps1 -FromSource -Metrics -NoRamGuard -MemDiag`, sin `-ReadOnly`).
Snapshot de la DB resultante: `audit/danibod_zzz_v2.censo_discos_20260917.db`.
Migración de cierre: `db/migrations/2026-09-17_36_censo_discos_baja_de_17_desmontados.sql`.

## 1. Resultado

```
[censo-discos] resumen de la sesión — 380/380 registrados · 311 con dueño · 69 libres · 0 sin resolver
```

| | |
|---|---|
| contador del header de S9 (autoridad) | **380** |
| registrados por el censo | **380** |
| filas distintas persistidas | **380** |
| sin resolver | **0** |
| filas nuevas (discos farmeados) | 12 |
| filas en DB que la pasada no vio | 17 |
| duración | 20:48 → 22:49 (con pausas del usuario) |

**Es la primera pasada que cierra.** El censo del 2026-08-30 tenía predicho que no podía:
calculaba su propia identidad y el OCR leía el nombre del set distinto entre pasadas
(`Firmamento Ilameante` vs `llameante`), así que el total era inalcanzable **por diseño**
(~317 de 339 previstos). Cierra recién desde que la identidad es **la fila** que tocó la
persistencia — una autoridad, no dos.

## 2. Por qué acá la ausencia sí significa algo

La regla del proyecto es que **la ausencia no prueba la inexistencia** (B2): que el sistema no
vea algo puede querer decir que no lo recorriste. Lo que habilita la baja es el **criterio de
completitud**, y se cumplió:

- el contador —la autoridad del conteo— leyó 380;
- el censo registró 380/380 con **0 sin resolver**;
- y la persistencia tocó **380 filas distintas**.

Dos caminos independientes (contar discos en pantalla, contar filas en la DB) dieron el mismo
número ⇒ hubo **biyección**. Si se tocaron tantas filas como discos hay en pantalla, lo que quedó
afuera no está en la pantalla.

### Un cruce que no se buscó

El censo contó **69 libres**; la DB tenía **86**. La diferencia es **17** — exactamente las filas
no vistas. Nadie lo construyó así: son dos cuentas que se hicieron por caminos distintos.

## 3. Las 17 filas dadas de baja

Todas **libres**, **no equipadas**, **vigentes**, y sin ninguna referencia en
`inventory_disc_evaluations` (la única FK a `inventory_discs`).

| nivel | n |
|---|---|
| Nv0 | 13 |
| Nv3 | 2 |
| Nv15 | 2 |

Es el perfil exacto del descarte de farmeo, y Daniel confirmó que estuvo desmontando.

**Sobre los repetidos.** Entre las 17 hay **4 filas idénticas** (`Aria radiante` slot 2 ATK Nv0)
y **3 idénticas** (`Melodía de Faetón` slot 3 DEF Nv0). Preguntar *cuál* borrar no tiene sentido:
son indistinguibles en todo campo observable, así que borrar unas u otras es la misma operación.
Lo que la evidencia sostiene es el **número**.

## 4. La pregunta que habilitó la Fase 3

De los **23** discos en Nivel 0 que la DB arrastraba sin poder verificar:

| | |
|---|---|
| se volvieron a ver en la pasada | **10** |
| de esos, **siguen en Nivel 0** | **10** ← genuinos |
| eran mala lectura del OCR | **0** |
| no aparecieron (desmontados) | 13 |

**El Nivel 0 era real en todos los casos verificables.** La sospecha de partida —"esos 23 son
lecturas fallidas"— era **falsa**, y lo que permitió comprobarlo en vez de seguir suponiendo fue
separar "no lo leí" de "Nivel 0" (Fase 3). En toda la pasada hubo **0 filas con nivel NULL y 0
marcadas**: el nivel se leyó en los 380.

Quedan 12 vigentes en Nivel 0 = los 10 genuinos + 2 farmeados durante la pasada misma.

## 5. Estado después de la migración 36

| | antes | después |
|---|---|---|
| filas totales | 403 | **386** |
| vigentes | 397 | **380** |
| con dueño | 311 | 311 |
| libres | 86 | **69** |
| Nivel 0 vigentes | 25 | **12** |
| PJs con los 6 slots | 51 | **51** |

`PRAGMA foreign_key_check` sin filas · `PRAGMA integrity_check` = ok · 7/7 smoke checks exactos.

**51 de 52 PJs con los 6 slots** (en agosto eran 43/51). El único incompleto es **Nekomata (5/6)**.

## 6. Hallazgos abiertos

- **Harumasa ↔ Antón.** Daniel lo reportó en vivo y el log lo confirma: `id=355` pasó
  Harumasa→Antón a las 22:46:57 y volvió Antón→Harumasa a las 22:47:50 (`s17_move`, "corrección
  tardía"). **Se autocorrigió** y los dos terminan 6/6, pero la confusión es real. 3 `DESPLAZADO`
  en total en la pasada. Sin tocar, por pedido de Daniel.
- **Latencia peor que el cierre de la Fase 2.** `click→log` p50 **3391 ms** en esta ventana contra
  los **2562 ms** con los que cerró la Fase 2. Las dos explicaciones cómodas **no aguantan**: la
  persistencia mide 16-47 ms (no es "ahora escribe"), y el OCR del panel está **más rápido**
  (p50 618 ms contra 1608 ms). Lo que creció es el `detector` (p50 595 ms) y el `loop_period`
  (p50 1187 ms contra ~391 ms). **Sin diagnosticar**, y la comparación no es limpia: la Fase 2
  midió una pasada controlada de ~10 discos y esto son 124 muestras de una pasada larga con dos
  relevos del worker de OCR en el medio.
- **El censo de armas no puede cerrar nunca** tal como está: el contador incluye los W-Engines de
  rango B y Daniel no los quiere censar, así que siempre va a reportar un hueco. Es justo la
  condición inalcanzable que el censo de agosto advirtió que no hay que aceptar. Hace falta poder
  declarar un alcance.

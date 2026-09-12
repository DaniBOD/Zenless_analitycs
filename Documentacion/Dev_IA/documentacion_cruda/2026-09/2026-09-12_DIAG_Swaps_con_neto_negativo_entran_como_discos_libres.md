# DIAG · Los swaps con neto ≤ 0 entran a la build rotulados como discos libres

> **Fecha:** 2026-09-12 · **Tipo:** DIAG (sin cambios de código) · **Alcance:** `app/core/optimizer.py`
> **Viene de:** [FIX del baseline](2026-09-12_FIX_El_optimizador_media_contra_una_tabla_vacia.md) §5.1
> **Prácticas en juego:** A1, A5 (conteos sobre el total), E1, E3 (diagnóstico antes que arreglo)

---

## 1. La pregunta

Con el baseline arreglado, 51/51 PJs seguían mostrando una mejora, y la mediana de esa mejora
(12.8) era mayor que la mediana del score actual (11.9). RF-06 §4.3 dice *"sólo se proponen swaps
con `swap_neto > 0`"*. ¿El código lo cumple?

## 2. Cómo está armado (lectura del código)

1. **Fase 1** (`_greedy_candidates`) recibe `get_all_active()`: **todos** los discos no
   descartados, incluidos los que llevan otros PJs. Los discos ajenos compiten desde el primer paso,
   por su score para el PJ destino y sin ningún costo.
2. **Fase 2** (`_bonus_pass`) arma las builds con esos candidatos.
3. **Fase 3** (`_compute_swaps`) recorre la build **ya elegida** y devuelve la *lista* de swaps con
   `neto > 0`. **No saca de la build** los discos con neto ≤ 0: esos quedan adentro con
   `swap_origen=None`, que en `DiscInBuild` significa literalmente *"None = free"*.
4. `delta_vs_actual = score_total − score_actual` solo del PJ destino: no descuenta lo que pierden
   los PJs de origen.

Además `neto` no es lo que define el RF. El RF habla de **builds**
(`perdida = S_old − S_new` del PJ origen, con su set bonus y su reemplazo). El código compara el
score del **disco suelto** para el destino contra el score del disco suelto para el origen.

## 3. Medición

Copia de `db/danibod_zzz_v2.db` (sha256 `495f44fa…` igual antes y después), `persist=False`,
top-1 de los 51 PJs con discos equipados. Conteos sobre el total, no muestras.

### 3.1 De dónde salen los discos de la mejor build

| origen del disco | discos (de 306) |
|---|---|
| propios del PJ | 13 |
| libres | 48 |
| **de otro PJ** | **245** |
| ↳ con swap listado (neto > 0) | 153 |
| ↳ **sin swap listado, rotulados "libre"** (neto ≤ 0) | **92** |

- **42 / 51** mejores builds llevan al menos un disco ajeno rotulado como libre.
- **39 / 51** mejores builds no conservan **ningún** disco propio del PJ.
- `protected_build=1`: 0 PJs, así que hoy ningún disco entra por la rama "origen protegido" (que
  tiene el mismo defecto: `continue` ⇒ el disco queda en la build como libre).

### 3.2 Por qué neto ≤ 0: casi siempre es exactamente 0

`score_disco` usa `agent.substat_preferences` si existen y si no, los pesos del arquetipo. Solo
**9 de 51** PJs tienen preferencias (60 filas). Para el resto, el score de un disco depende **solo
del arquetipo**: entre PJs del mismo arquetipo, 8357 pares disco×PJ dan idéntico y 2423 difieren
(los de PJs con preferencias).

Neto de los 92 discos ajenos no listados + los 153 listados, por tipo:

| | neto = 0 | neto > 0 | neto < 0 |
|---|---|---|---|
| mismo arquetipo | **72** | 14 | 10 |
| otro arquetipo | 2 | 139 | 8 |

Los ejemplos lo muestran solos: Miyabi toma el disco 217 **de Jane** (ambas ANOMALY): destino 4.05,
origen 4.05. No es una mejora, es un traslado. El optimizador de Miyabi se lo lleva y lo muestra
como si estuviera libre.

### 3.3 Hipótesis descartada: la escala entre arquetipos

RF-06 §5.2 advierte que el score crudo no es comparable entre arquetipos, y las escalas difieren
(mediana sobre los 339 discos: DEFENSE −0.30, ANOMALY 0.70, ATK_DPS 1.95; máximo 4.0 a 6.2). Parecía
que el neto entre arquetipos distintos era un artefacto de escala. **Medido, es un efecto menor**:
normalizando cada score por `score_maximo_teorico` de su arquetipo, solo **21 de 245** discos
ajenos cambian de signo (13 pasan de >0 a ≤0, 8 al revés). No es la causa principal. Queda anotado
para cuando se cambie la fórmula del neto.

### 3.4 Efecto sobre la mejora reportada

| | PJs con mejora > 0 |
|---|---|
| delta publicado (solo destino) | **51 / 51** |
| delta − score que pierden los orígenes (disco a disco, sin reemplazo) | **24 / 51** |

La corrección de la segunda fila es gruesa: sobreestima la pérdida porque el origen equiparía otro
disco. Aun así alcanza para ver que la mitad de las "mejoras" se sostienen solo con discos ajenos.

## 4. ¿Llega a algún lado?

No hoy. Fuera de `optimizer.py`, `repositories.py` y los tests, nadie en `app/` lee `swap_origen`,
`swaps_requeridos`, `requiere_swaps` ni `optimizer_pending_actions` (grep sin `app/build/`). Y el
disparador del optimizador no está conectado (ver el FIX). Es un defecto latente, pero es
**el mensaje central** de cualquier pantalla que muestre estas builds: *"equipá estos discos, están
libres"* cuando 2 de cada 5 son de otro PJ.

## 5. Opciones de arreglo — ❓ decisión de Daniel

No se implementó nada (E3): hay más de una semántica razonable y el RF no alcanza para elegir.

| opción | qué hace | costo / riesgo |
|---|---|---|
| **A. Marcar siempre** | todo disco ajeno lleva `swap_origen`, con su neto (aunque sea ≤ 0) | mínimo. Deja de mentir "libre", pero la build sigue saqueando: la mejora no cambia |
| **B. Excluir en la build** | un disco ajeno con neto ≤ 0 (u origen protegido) no es candidato para ese PJ; el bonus pass elige con lo que queda | cumple la letra de §4.3. Hay que filtrar **antes** de la fase 2, no después: sacar un disco de una build ya armada rompe el set |
| **C. Neto de build (lo que dice el RF)** | pérdida = `S_old − S_new` del origen, recalculando su build sin el disco | lo más fiel, y cubre set bonus y reemplazo. Caro: una build del origen por disco ajeno (RNF-06: < 1 s) |
| **D. Empate = no mover** | en B o C, neto == 0 cuenta como no-mejora | sin esto, los 72 traslados entre mismo arquetipo siguen apareciendo |

Recomendación: **B + D ahora** (candidato ajeno solo si neto > 0 disco a disco, calculado
antes del bonus pass), con **A** como red (un disco ajeno nunca sale con `swap_origen=None`). **C**
queda para cuando haya una pantalla que muestre swaps y se pueda medir si la versión disco a disco
engaña en la práctica. Antes de cualquier opción: test con dos PJs del mismo arquetipo donde el
único disco bueno lo lleva el otro. Hoy ese test mostraría el disco como libre.

Aparte, y sin relación con los swaps: el filtro de mains por arquetipo deja afuera discos de builds
reales (el slot 4 de Miyabi es `Daño Crítico` y ANOMALY no lo acepta). Es la otra observación
abierta del FIX y sigue sin investigar.

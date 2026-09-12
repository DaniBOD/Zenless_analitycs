# FIX · Un disco ajeno solo entra a la build si gana, y nunca como libre

> **Fecha:** 2026-09-12 · **Tipo:** FIX · **Alcance:** `app/core/optimizer.py`
> **Viene de:** [DIAG swaps con neto ≤ 0](2026-09-12_DIAG_Swaps_con_neto_negativo_entran_como_discos_libres.md) — opciones **B + D, con A de red** (decisión de Daniel)
> **Prácticas en juego:** A3 (romper el test, y romper bien la mutación), B1, E3

---

## 1. Qué cambió

| regla | implementación |
|---|---|
| **B** — un disco que lleva otro PJ es candidato solo si moverlo gana | `best_builds` filtra el inventario **antes** del greedy y del bonus pass con `_admite_disco_ajeno`. Filtrar después habría roto combinaciones de sets ya armadas |
| **D** — neto 0 no es mejora | `neto > 0` estricto, sobre el neto **redondeado a 4 decimales** para que el ruido de coma flotante no convierta un traslado en ganancia |
| origen protegido / sin arquetipo / inexistente | no se toca: el swap lleva `motivo` y B lo rechaza. Sin arquetipo el neto queda en `None` (RNF-02) |
| **A** — red | `_compute_swaps` ya no filtra: devuelve un swap por **cada** disco ajeno de la build. Si alguno no debió pasar, igual se reporta y se loguea un `WARNING` |

Una sola función calcula el swap (`_swap_de_disco_ajeno`) y una sola lo juzga
(`_admite_disco_ajeno`): la usan el filtro y la red (B1). Antes el criterio vivía en
`_compute_swaps` y no se aplicaba a los candidatos.

Además se **borró el bloque `equipped_others`** que agregaba los discos de otros PJs después de la
fase 1. Medido sobre la DB real antes de tocarlo: agregaba **0** discos (`get_all_active` ya los
incluía todos). Con B habría sido la puerta trasera: volvía a meter justo lo que el filtro saca.
El parámetro `set_repo` de `_compute_swaps`, que no se usaba, también salió.

Los dicts de swap suman la clave `motivo` (None si el swap es válido). `swap_origen` en
`DiscInBuild` no cambió de forma.

## 2. Tests

`app/tests/unit/test_optimizer_swaps_ajenos.py`: copia de la DB de dominio, inventario controlado.
Los PJs se eligen **sin preferencias propias** (score = el de su arquetipo), dos ATK_DPS y un
DEFENSE. Cada caso afirma su precondición (el signo del neto) con la misma función de score.

| test | antes del fix |
|---|---|
| D: el compañero de arquetipo (neto 0) no pierde su disco | ❌ |
| B: neto < 0 no es candidato | ❌ (ver abajo) |
| B: neto > 0 entra y lleva el swap | ✅ a propósito: el comportamiento correcto no debía cambiar |
| B: origen protegido no se toca aunque gane | ❌ |
| A: con B apagado (monkeypatch), el disco ajeno sale con `swap_origen` | ❌ |

**Dos veces un test pasó sin tener dientes:**

1. *B neto < 0* pasaba **antes del arreglo**. Tenía un disco libre flojo al lado, y el tanque ya lo
   prefería por score: el test nunca obligaba a elegir. Ahora el disco ajeno es el único candidato.
2. Una mutación de la red A **sobrevivió**, pero el defecto estaba en la mutación, no en el test:
   reusaba `_admite_disco_ajeno`, que el test de la red reemplaza por `True`. Reescrita como era el
   código original (filtro `neto > 0` inline en `_compute_swaps`), el test falla.

Mutaciones, todas en rojo:

| mutación | falla |
|---|---|
| `neto >= 0` | D |
| ignorar `motivo` | protegido |
| sin filtro B en `best_builds` | D, B neto < 0, protegido |
| red con el filtro inline original | A |
| neto sin redondear (+1e-12) | D |

## 3. Efecto medido — y lo que NO arregla

Copia de la DB real, mejor build de los 51 PJs con discos equipados. La DB de dominio no se tocó
(sha256 `495f44fa…` igual).

| | antes | después |
|---|---|---|
| discos ajenos rotulados "libre" | **92** | **0** |
| swaps listados con neto ≤ 0 | 0 (se escondían) | 0 |
| discos ajenos en la mejor build | 245 | **222** |
| builds de 6 discos | 51 | 51 |
| PJs con mejora > 0 | 51 | **51** |
| mediana de la mejora / del score actual | 12.8 / 11.9 | 11.65 / 11.9 |
| `WARNING` de la red A | — | 0 |
| latencia máx. | — | 72 ms (RNF-06: < 1 s) |

49 / 51 PJs cambian de build. La latencia de "antes" (81 ms) salió de una corrida en frío y la de
"después" en caliente, así que **no son comparables**: solo se afirma que está dentro de la cota.

**Lo que queda:** el optimizador ya no miente, pero **sigue saqueando**. 222 de 306 discos de las
mejores builds son de otros PJs, ahora todos con neto disco a disco > 0 (mayoritariamente entre
arquetipos distintos). La mejora sigue siendo solo del PJ destino: no descuenta lo que pierde el
origen en **su** build (set bonus, reemplazo). Eso es la **opción C** del diagnóstico (neto por
build, como define RF-06 §4.3), que quedó diferida a propósito hasta que haya una pantalla de swaps
donde medir si la versión disco a disco engaña en la práctica.

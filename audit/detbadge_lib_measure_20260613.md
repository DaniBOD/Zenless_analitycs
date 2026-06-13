# Librería de DETALLE-badge — cosecha 47/47 + medición (5R.C.4)

**Fecha:** 2026-06-13 · **Snapshot:** `audit/avatar_detbadge_v2_snapshot_20260613_full47.npz` (20 MB)
**Origen runtime:** `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\avatar_detbadge_v2.npz` (gitignoreado).

Cierre de la construcción de la librería propia del **detalle-badge** (avatar junto a "Nivel
15/15" del panel de detalle S17), cosechada en vivo con `qa_launch -BadgeHarvest` sobre el
flujo-ancla (primer disco de cada slot recién abierto = dueño certero del latch). Encuadre
DISTINTO al grid-badge → librería separada (`AgentIdentifier._detbadge`).

## Cobertura

**47/47 PJs · 316 refs.** Cosechado en 3 tramos (driver TDR cerró ZZZ en el 1º; reinicios por
fuga RNF-06). La mayoría con 7 refs.

| | |
|---|---|
| Completos (≥5 refs) | 44 PJs |
| **Flacos** | **Lycaon(1)**, Rina(3), Seth(3) |

- **Lycaon quedó en 1 ref** y no reforzó entre pasadas: su avatar (cara de lobo) es de baja
  saturación → el localizador por blob saturado (`_DET_SAT_MIN=50`) no lo engancha en la
  mayoría de slots. Cubierto por la librería de grid (7 refs) + voto. Limitación conocida.

## Medición (leave-one-out sobre los descriptores cosechados)

`tools/measure_badge_lib.py <npz>` — saca cada ref de su PJ y la matchea contra el resto:

| Guard | Top-1 | Abstención | **Wrong (RNF-02)** |
|-------|-------|-----------|--------------------|
| sin guard | 76.9% | 17.4% | 5.7% |
| **0.80 (S17 en vivo)** | **75.3%** | 23.1% | **1.6% (5/316)** |

Wrongs bajo guard 0.80: `Alice→Sunna`, `Yixuan→Anby`, `Astra Yao→Anby`, `Jane→Anby`,
`Seth→Yixuan`.

### Lectura

- **El detalle discrimina PEOR que el grid** (75% vs 90% top-1; 1.6% vs 0.9% wrong). El avatar
  del panel es más chico/baja-res → menos señal en el descriptor.
- **Su valor NO es discriminación — es LOCALIZACIÓN: 100% vs 73% del grid** (medido sobre video,
  ver `Documentacion/Videos_flujo/Flujo_Grillas_Badges.md` §2). Llena el hueco cuando el grid da
  NOLOC (transición) o se confunde con el arte amarillo "llama".
- **Imán Anby:** Yixuan/Astra Yao/Jane caen falsamente en Anby bajo guard. A vigilar; el voto
  multi-frame + la fuente de grid deberían taparlo en vivo.
- **Ambas fuentes votan al MISMO acumulador** por firma-de-disco (`_s17_owner_votes`, 10 fps).
  El 1.6% por-frame se diluye con ~10 s de frames por disco. El número real-real sale del **QA
  en vivo contra el equip_map** (pendiente).

## Estado de cableado

Implementado y commiteado en **c701a56** (`crop_detail_badge`, `_detbadge` matcher,
`learn_s17_detail`/`s17_match_detail`, cosecha + voto en `_sample_s17_owner`). Inerte hasta esta
cosecha → ahora **activo** (vota en S17 con el grid de respaldo).

## Nota de fuga RNF-06

Durante las pasadas la app tocó **10–11.4 GB en pocos minutos** (ceiling ~12 GB → cuelgue). Es
la fuga pre-existente del loop de monitoreo/OCR (ver `Documentacion/Dev_IA/2026-06-12_BUG_fuga_
memoria_RNF-06.md`), NO el path del detalle (verificado: votos = floats acotados, crops →
descriptores, sin retención de frames). **Bloqueante para sesiones largas** (incl. QA en vivo
extenso y C.5). Mitigación actual: reiniciar cada pocos PJs.

## Próximo

QA en vivo (yield real con grid+detalle votando contra el equip_map) — limitado por la fuga.
Candidato a priorizar el fix RNF-06 antes de validaciones largas.

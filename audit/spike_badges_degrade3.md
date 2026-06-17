# Spike embedding (Hito E.0) — 2026-06-16

> ¿Algún embedder off-the-shelf supera al descriptor con **0 wrong** (RNF-02)?

## Setup
- **GOLD** (medición, leave-one-out): `audit/harvest_badges/*__grid__*` — 180 crops de badge REALES in-game (recortados de los frames harvest con la lógica de la app `detector.crop_*`; etiqueta = latch = dueño certero).
- Refs: `avatar_refs` ico (53) + GOLD-limpio multi-ref. Reject: 13.
- Refs extra grid_diag (label-plata, conf>=0.95): no.
- Máscara circular: sí.
- **Degradación de queries:** duro (refs siempre limpias). ⭐ test real del gate (simula scroll en vivo)
- ⚠️ labels gold fuera de equip_map owners: ['n.aº11']

## Resultados

| Motor | dim | lat ms/crop | top-1 s/guarda | wrong s/guarda | CERO-WRONG top-1 | abst | τ |
|---|---|---|---|---|---|---|---|
| `descriptor(hist+ncc)` | — | 2.5 | 71.7% | 27.8% | **25.6%** | 74.4% | 0.057 |
| `emb:onnx(mobilenetv3)` | 1280 | 12.0 | 11.1% | 66.7% | **1.1%** | 98.9% | 0.068 |
| `emb:mobilenetv3` | 960 | 32.5 | 9.4% | 64.4% | **3.9%** | 96.1% | 0.042 |

## Confusiones (sin guarda) — foco look-alikes (RNF-02)

- `descriptor(hist+ncc)`: ben→soukaku×3  alice→burnice×2  corin→anby×2  miyabi→zhuyuan×2  panyinhu→koleda×2  rina→piper×2  alice→piper×1  astrayao→qingyi×1  cesar→lucia×1  cesar→miyabi×1
- `emb:onnx(mobilenetv3)`: ben→sporos×4  billy→anton×4  harumasa→anton×4  evelyn→alice×3  koleda→manato×3  lucy→sporos×3  yeshunguang→alice×3  yuzuha→anton×3  astrayao→anton×2  burnice→alice×2
- `emb:mobilenetv3`: harumasa→anton×4  ben→sporos×3  billy→anton×3  anton→harumasa×2  astrayao→anton×2  corin→anton×2  ellen→anton×2  evelyn→piper×2  grace→anton×2  grace→nekomata×2

## Lectura del gate

- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).
- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.
- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe cumplirlo; CLIP suele exceder → solo baseline de precisión.

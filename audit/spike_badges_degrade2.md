# Spike embedding (Hito E.0) — 2026-06-16

> ¿Algún embedder off-the-shelf supera al descriptor con **0 wrong** (RNF-02)?

## Setup
- **GOLD** (medición, leave-one-out): `audit/harvest_badges/*__grid__*` — 180 crops de badge REALES in-game (recortados de los frames harvest con la lógica de la app `detector.crop_*`; etiqueta = latch = dueño certero).
- Refs: `avatar_refs` ico (53) + GOLD-limpio multi-ref. Reject: 13.
- Refs extra grid_diag (label-plata, conf>=0.95): no.
- Máscara circular: sí.
- **Degradación de queries:** medio (refs siempre limpias). ⭐ test real del gate (simula scroll en vivo)
- ⚠️ labels gold fuera de equip_map owners: ['n.aº11']

## Resultados

| Motor | dim | lat ms/crop | top-1 s/guarda | wrong s/guarda | CERO-WRONG top-1 | abst | τ |
|---|---|---|---|---|---|---|---|
| `descriptor(hist+ncc)` | — | 2.5 | 86.7% | 12.8% | **17.8%** | 82.2% | 0.092 |
| `emb:onnx(mobilenetv3)` | 1280 | 12.0 | 18.9% | 73.3% | **1.1%** | 98.9% | 0.081 |
| `emb:mobilenetv3` | 960 | 31.9 | 17.8% | 73.3% | **2.2%** | 97.8% | 0.056 |
| `emb:efficientnet_lite0` | 1280 | 36.7 | 15.0% | 83.3% | **1.1%** | 98.9% | 0.050 |

## Confusiones (sin guarda) — foco look-alikes (RNF-02)

- `descriptor(hist+ncc)`: anton→harumasa×2  ben→soukaku×2  cissia→alice×1  corin→alice×1  dialyn→yixuan×1  ellen→nekomata×1  harumasa→anton×1  lycaon→harumasa×1  miyabi→anton×1  miyabi→zhuyuan×1
- `emb:onnx(mobilenetv3)`: ben→sporos×4  billy→anton×4  harumasa→anton×4  panyinhu→anton×4  ellen→anton×3  grace→anton×3  jufufu→piper×3  koleda→manato×3  lucy→sporos×3  nangongyu→anton×3
- `emb:mobilenetv3`: harumasa→anton×4  n.aº11→piper×4  yeshunguang→nekomata×4  ben→sporos×3  jane→nekomata×3  jufufu→piper×3  miyabi→nekomata×3  seth→corin×3  soukaku→sporos×3  yuzuha→nangongyu×3
- `emb:efficientnet_lite0`: alice→cesar×4  burnice→cesar×4  manato→zhao×4  n.aº11→yixuan×4  piper→cesar×4  seth→yixuan×4  sunna→yixuan×4  anby→yixuan×3  cissia→cesar×3  evelyn→yixuan×3

## Lectura del gate

- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).
- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.
- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe cumplirlo; CLIP suele exceder → solo baseline de precisión.

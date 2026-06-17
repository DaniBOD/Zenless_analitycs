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
| `descriptor(hist+ncc)` | — | 2.5 | 87.8% | 12.2% | **76.1%** | 23.9% | 0.030 |
| `emb:onnx(mobilenetv3)` | 1280 | 12.2 | 31.1% | 68.3% | **7.2%** | 92.8% | 0.046 |
| `emb:mobilenetv3` | 960 | 24.7 | 38.3% | 61.1% | **8.3%** | 91.7% | 0.041 |

## Confusiones (sin guarda) — foco look-alikes (RNF-02)

- `descriptor(hist+ncc)`: corin→alice×2  dialyn→jane×2  anby→qingyi×1  anby→alice×1  ben→soukaku×1  cesar→lucia×1  corin→burnice×1  ellen→astrayao×1  jane→nangongyu×1  lycaon→zhao×1
- `emb:onnx(mobilenetv3)`: harumasa→gatillo×4  panyinhu→anton×4  sunna→corin×4  yixuan→anton×4  anby→corin×3  burnice→alice×3  cesar→corin×3  dialyn→anton×3  jane→anton×3  lucy→sporos×3
- `emb:mobilenetv3`: harumasa→gatillo×4  miyabi→gatillo×4  n.aº11→anton×4  seth→corin×4  sunna→corin×4  yixuan→anton×4  burnice→alice×3  cesar→corin×3  orfiaymagas→nicole×3  qingyi→corin×3

## Lectura del gate

- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).
- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.
- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe cumplirlo; CLIP suele exceder → solo baseline de precisión.

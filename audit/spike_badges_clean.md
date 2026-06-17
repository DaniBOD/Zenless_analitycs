# Spike embedding (Hito E.0) — 2026-06-16

> ¿Algún embedder off-the-shelf supera al descriptor con **0 wrong** (RNF-02)?

## Setup
- **GOLD** (medición, leave-one-out): `audit/harvest_badges/*__grid__*` — 180 crops de badge REALES in-game (recortados de los frames harvest con la lógica de la app `detector.crop_*`; etiqueta = latch = dueño certero).
- Refs: `avatar_refs` ico (53) + GOLD-limpio multi-ref. Reject: 13.
- Refs extra grid_diag (label-plata, conf>=0.95): no.
- Máscara circular: sí.
- **Degradación de queries:** no (crops limpios) (refs siempre limpias). — no separa motores (ver caveat)
- ⚠️ labels gold fuera de equip_map owners: ['n.aº11']

## Resultados

| Motor | dim | lat ms/crop | top-1 s/guarda | wrong s/guarda | CERO-WRONG top-1 | abst | τ |
|---|---|---|---|---|---|---|---|
| `descriptor(hist+ncc)` | — | 6.0 | 95.0% | 5.0% | **92.2%** | 7.8% | 0.023 |
| `emb:onnx(mobilenetv3)` | 1280 | 12.6 | 97.8% | 2.2% | **93.9%** | 6.1% | 0.017 |
| `emb:mobilenetv3` | 960 | 34.6 | 98.9% | 1.1% | **94.4%** | 5.6% | 0.020 |
| `emb:efficientnet_lite0` | 1280 | 38.5 | 97.2% | 2.8% | **94.4%** | 5.6% | 0.011 |

## Confusiones (sin guarda) — foco look-alikes (RNF-02)

- `descriptor(hist+ncc)`: alice→cesar×1  anby→corin×1  ben→soukaku×1  corin→cesar×1  corin→burnice×1  miyabi→anton×1  seth→lucia×1  seth→yanagi×1  zhuyuan→miyabi×1
- `emb:onnx(mobilenetv3)`: anton→harumasa×2  ben→soukaku×2
- `emb:mobilenetv3`: anton→harumasa×1  ben→soukaku×1
- `emb:efficientnet_lite0`: anton→harumasa×3  ben→soukaku×2

## Lectura del gate

- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).
- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.
- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe cumplirlo; CLIP suele exceder → solo baseline de precisión.

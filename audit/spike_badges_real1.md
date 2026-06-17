# Spike embedding (Hito E.0) — 2026-06-16

> ¿Algún embedder off-the-shelf supera al descriptor con **0 wrong** (RNF-02)?

## Setup
- **GOLD** (medición, leave-one-out): `audit/harvest_badges/*__grid__*` — 180 crops de badge REALES in-game (recortados de los frames harvest con la lógica de la app `detector.crop_*`; etiqueta = latch = dueño certero).
- Refs: `avatar_refs` ico (53) + GOLD-limpio multi-ref. Reject: 13.
- Refs extra grid_diag (label-plata, conf>=0.95): no.
- Máscara circular: sí.
- **Degradación de queries:** leve (refs siempre limpias). ⭐ test real del gate (simula scroll en vivo)
- ⚠️ labels gold fuera de equip_map owners: ['n.aº11']

## Resultados

| Motor | dim | lat ms/crop | top-1 s/guarda | wrong s/guarda | CERO-WRONG top-1 | abst | τ |
|---|---|---|---|---|---|---|---|
| `descriptor(hist+ncc)` | — | 2.5 | 95.6% | 4.4% | **83.3%** | 16.7% | 0.034 |
| `emb:onnx(mobilenetv3)` | 1280 | 12.6 | 58.3% | 41.7% | **27.2%** | 72.8% | 0.042 |
| `emb:mobilenetv3` | 960 | 33.7 | 67.8% | 32.2% | **30.6%** | 69.4% | 0.041 |

## Confusiones (sin guarda) — foco look-alikes (RNF-02)

- `descriptor(hist+ncc)`: cesar→alice×1  cissia→alice×1  miyabi→zhuyuan×1  n.aº11→lucia×1  seth→vivian×1  seth→yanagi×1  sunna→cesar×1  vivian→cissia×1
- `emb:onnx(mobilenetv3)`: ben→sporos×4  cesar→corin×4  rina→corin×4  seth→corin×4  sunna→corin×4  anby→corin×3  harumasa→anton×3  jane→anton×3  koleda→manato×3  lucy→sporos×3
- `emb:mobilenetv3`: evelyn→gatillo×4  seth→corin×4  sunna→corin×4  anby→corin×3  harumasa→gatillo×3  n.aº11→anton×3  grace→nekomata×2  jane→anton×2  koleda→nicole×2  lucy→nangongyu×2

## Lectura del gate

- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).
- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.
- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe cumplirlo; CLIP suele exceder → solo baseline de precisión.

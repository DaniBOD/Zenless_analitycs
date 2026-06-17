# Spike embedding (Hito E.0) — 2026-06-16 · VEREDICTO CORREGIDO

> **Gate:** ¿un embedding aprendido off-the-shelf identifica el dueño del badge MEJOR
> que el descriptor hand-crafted, con 0 wrong (RNF-02) y siendo enviable?
> **Veredicto: NO — el gate FALLA. El descriptor GANA.** Recomendación: **detener el
> pivote a embedding (E.1–E.4)** y redirigir a la localización (el cuello real).

## ⚠️ Corrección metodológica (importante)
La primera corrida usó por error `audit/harvest/*.png`, que son **frames completos
2560×1440**, no crops de badge. El descriptor/embedder terminaron matcheando PANTALLAS
por PJ (tarea distinta y más fácil) → dio un falso "embedding gana 13×". Corregido:
se extrajeron los badges reales de esos frames con la lógica de la app
(`detector.crop_grid_selected_badge`, `tools/extract_harvest_badges.py` →
`audit/harvest_badges/`), etiqueta = latch del flujo-ancla (dueño CERTERO). Esta es la
medición válida. **Sanity:** el descriptor da 92%@0-wrong en limpio, consistente con su
performance conocida (~90% top-1, `measure_badge_lib`) → el set mide bien.

## Setup
- GOLD: `audit/harvest_badges/*__grid__*` — 180 badges de grilla S17 reales, 45 PJs (label oro).
- Refs: `avatar_refs` ico (53) + GOLD-limpio multi-ref. Reject: 13. Leave-one-out.
- Motores: descriptor (`avatar_descriptor.py`), `onnx` (= pipeline runtime `onnx_embedder.py`,
  onnxruntime+cv2), MobileNetV3 y EfficientNet-lite0 (timm). Métrica = top-1 con **CERO-WRONG**.

## Resultados

### Limpio (badges bien localizados)
| Motor | lat ms/crop | top-1 s/guarda | wrong | **CERO-WRONG top-1** |
|---|---|---|---|---|
| `descriptor` | 6 | 95.0% | 5.0% | 92.2% |
| `onnx` (runtime) | 12.6 | 97.8% | 2.2% | 93.9% |
| `mobilenetv3` | 34.6 | 98.9% | 1.1% | **94.4%** |
| `efficientnet_lite0` | 38.5 | 97.2% | 2.8% | 94.4% |

En limpio el embedding gana apenas **~2pp** sobre el descriptor. (El `onnx` reproduce al
timm: 93.9 vs 94.4 → export/preprocesado validados end-to-end.)

### Degradación REALISTA (jitter de localización + motion blur vertical; lo que de verdad pasa en scroll)
| Motor | nivel 1 (leve) CERO-WRONG | nivel 2 (medio) CERO-WRONG |
|---|---|---|
| `descriptor` | **83.3%** | **76.1%** |
| `onnx` | 27.2% | 7.2% |
| `mobilenetv3` | 30.6% | 8.3% |

### Degradación FULL (downscale 65% + JPEG + rotación — NO realista para captura de pantalla)
| Motor | medio CERO-WRONG | duro CERO-WRONG |
|---|---|---|
| `descriptor` | 17.8% | 25.6% |
| `onnx` / `mobilenetv3` | 1.1% / 2.2% | 1.1% / 3.9% |

## Lectura — por qué el embedding pierde
- El descriptor fue **diseñado para esta tarea**: badges chicos, dominados por color, círculo
  enmascarado, CLAHE para iluminación. Su histograma HSV + medias por banda apenas cambian con
  blur/jitter → robusto.
- El embedding ImageNet espera fotos reales a 224px; un badge **anime de 60px upscaleado 3.7×**
  ya está fuera de distribución, y el blur/jitter lo empuja más → los vectores se agrupan y
  colapsan (muchos wrongs). Pierde en limpio degradado y, sobre todo, bajo CUALQUIER degradación.
- **El cuello real NO es la discriminación** (el descriptor clava 92%@0-wrong en limpio). Es la
  **LOCALIZACIÓN** del badge (NOLOC en transición, anillo confundido con arte de discos "llama"),
  ya identificada en commit c701a56. El embedding **no toca la localización** → no resuelve el
  "dueño incierto" en vivo.

## Veredicto y recomendación
- **Gate FALLA.** Off-the-shelf no supera al descriptor; lo empeora bajo degradación. No justifica
  enviar modelo 17 MB + onnxruntime + latencia.
- **Recomendado: DETENER el pivote a embedding (E.1–E.4).** Redirigir el esfuerzo a:
  1. **Localización robusta** del grid-badge (el cuello): separar el anillo del badge del arte
     amarillo/lima de discos; bajar el NOLOC en transición.
  2. **Apoyarse en el detail-badge** (`crop_detail_badge`, 100% localización) + **voto multi-frame**
     ya existentes — atacan el cuello sin cambiar el motor de similitud.
  3. (Opcional, sólo si tras 1-2 la discriminación pasa a ser el cuello) re-evaluar **fine-tuning**
     (E.4) de un modelo chico sobre badges reales — pero es esfuerzo grande con payoff incierto.
- Lo construido NO se tira: `onnx_embedder.py` + export + spike quedan como infraestructura
  reusable si en el futuro se entrena un modelo a medida.

## Artefactos
- Spike: `tools/spike_embedding.py` (+ `--gold`, `--degrade`, `--realistic`, motor `onnx`).
- Extractor de badges gold: `tools/extract_harvest_badges.py` → `audit/harvest_badges/` (347 crops).
- Export ONNX: `tools/export_embedder_onnx.py` → `app/resources/avatar_embedder.{onnx,json}` (17 MB).
- Embedder runtime: `app/core/onnx_embedder.py` (onnxruntime CPU, lazy).
- Reportes crudos: `audit/spike_badges_{clean,degrade2,degrade3,real1,real2}.md`.
- Venv del spike: `.venv_spike` (torch+timm, gitignoreado, fuera del build).

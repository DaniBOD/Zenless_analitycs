# Plan — Embedding aprendido como motor de identidad de badges (Fase 5R)

> **Estado:** APROBADO 2026-06-13 (planning interactivo con el usuario). Próximo = Hito E.0.
> Reemplaza el descriptor hand-crafted por un embedding ONNX para identificar dueños de badges
> sin wrongs (RNF-02). NO confundir con el plan de RNF-06 (fuga de memoria, ya CERRADA — commit 0863319).

## Context

Identificar QUÉ PJ tiene equipado un disco se hace mirando su badge/avatar circular en la grilla
S17. El motor actual es un **descriptor hand-crafted** (`app/core/avatar_descriptor.py`: histograma
HSV + NCC sobre patch Lab + medias por banda). OFFLINE da 75-90% top-1, pero el **QA en vivo
2026-06-13 dio yield pobre**: la mayoría de los discos caen en `dueño incierto` o `sin badge → sin
asignar`; solo el flujo-ancla (1er disco del slot) se identifica seguro. Causa: los recortes en
vivo varían en encuadre/escala/compresión respecto a las refs, y el descriptor a mano abstiene.
Tunear pesos ya se descartó (callejón sin salida).

**Objetivo:** reemplazar el *motor de similitud* por un **embedding aprendido** (una red chica
convierte el crop en un vector ~512-d; "esencia visual"; match por **cosine similarity**), que
discrimina mejor a través de variaciones de encuadre. **Meta dura (RNF-02): CERO dueño equivocado**
— subir el top-1 (menos "incierto") manteniendo wrongs = 0 vía abstención.

> **Para el dev:** un embedding no compara píxeles ni bordes (eso hacía el descriptor) — proyecta la
> imagen a un espacio donde "parecido visual" = "vectores cercanos". Robusto a que el badge esté más
> chico/comprimido/movido, que es donde el descriptor a mano falla.

### ⚠️ Correcciones al md `zenless-analytics-context.md` (tenía imprecisiones)
1. **NO es "ORB + SIFT".** El descriptor real es **HSV-hist + NCC-Lab**. El embedding reemplaza ESO.
2. **NADA de torch en la app.** El build PaddleOCR está fijado (numpy 1.26.4) y `rebuild.ps1` aborta
   si detecta torch/numpy 2.x. Runtime = **onnxruntime CPU puro**; torch/CLIP solo offline.
3. **CLIP ViT-B/32 NO se empaqueta** (350 MB + torch + 650 MB RAM viola RNF-06). Solo para validar
   offline; se envía un modelo chico ONNX (~20 MB).
4. La **latencia 3-7s es del OCR**, no del badge. El embedder corre en el voto a 10 fps → modelo
   rápido (<~30 ms CPU).
5. **Fine-tuning es CONDICIONAL**, no el primer paso.
6. **Dataset ya existe** (confirmado en disco): `audit/grid_diag/` ~808 crops de badge in-game
   (etiqueta lectura+conf en filename, usar conf≥0.85), `audit/harvest/` 544 (etiqueta latch =
   dueño certero, `nombre__S17__N.png`), `app/resources/avatar_refs/` 53 ico limpios,
   `app/resources/avatar_reject/` 13 reject.

**Fuera de scope:** paralelización del pipeline (<1s) y UI QWebEngineView (venían en el md, son
esfuerzos separados).

## Principio rector
Se reutiliza TODA la maquinaria (reject-set, voto multi-frame por firma, abstención, flujo-ancla,
las 3 superficies `_row`/`_badge`/`_detbadge`). Solo cambia la similitud: `descriptor + distancia
combinada` → `vector + (1 − coseno)`. El `EmbeddingMatcher` espeja la interfaz de `AvatarMatcher`
(`app/core/avatar_descriptor.py`) → `agent_identifier.py`, `monitor.py` y `measure_badge_lib.py`
casi no cambian.

## Hitos

### E.0 — Spike offline (de-risk; NO toca app ni build)
`tools/spike_embedding.py` en venv separado: comparar 2-3 embedders ONNX (CLIP ViT-B/32 export,
DINOv2-small, MobileNetV3/EfficientNet-lite). Refs = `avatar_refs` + crops etiquetados
(`audit/harvest` latch + `audit/grid_diag` conf≥0.85). Leave-one-out (adaptar `measure_badge_lib.py`)
+ cruce con `audit/equip_map_20260612.json` (47/47). Métricas: top-1 / abstención / **WRONG=0**.
Foco look-alikes (Lycaon↔Pan Yinhu, Ben↔Soukaku). **Gate:** ¿off-the-shelf supera al descriptor con
0 wrong? SÍ→E.1 (preferir el chico); NO→E.4. Entregable: `audit/spike_embedding_<fecha>.md`.
**Prerrequisito:** `onnxruntime` NO está instalado en `.venv` (instalarlo) + bajar los .onnx.

### E.1 — EmbeddingMatcher + onnx_embedder + librería
`app/core/onnx_embedder.py` (onnxruntime CPU, `embed→vector L2-norm`, mismo preprocesado circular que
`build_descriptor`, lazy-load). `EmbeddingMatcher` espejando `AvatarMatcher` (refs/reject/abstención/
`match→MatchResult`/`from_folders`/`add_reference`/`load_merge`/`save`); distancia `1−coseno`;
**aplicar el fix de `load_merge` (.copy() — RNF-06)**. Construir `avatar_emb_*.npz`. Tests.
**Aceptación:** leave-one-out ≥ baseline del spike, 0 wrong, suite verde.

### E.2 — Integración ensemble + build
`AgentIdentifier`: EmbeddingMatcher PRIMARIO + AvatarMatcher fallback/desempate (conserva piso
0-wrong), flag A/B. `main.spec`: `collect_all("onnxruntime")` + `.onnx` como data file en
`app/resources/`. Rebuild. **RNF-06:** latencia embed <~30 ms (voto 10 fps) + RAM idle <200 MB.
**Aceptación:** `.exe` arranca, latencia/RAM OK, suite verde.

### E.3 — QA en vivo + medición vs equip_map
`qa_launch -ReadOnly` sobre grillas S17 (incl. look-alikes), scorecard identificados/incierto/WRONG.
**Aceptación:** top-1 en vivo >> el del descriptor, **WRONG=0**. Cierra la sub-fase.

### E.4 — (CONDICIONAL) Fine-tuning de modelo chico
Solo si off-the-shelf no separa los look-alikes. Esfuerzo mayor (venv torch, dataset etiquetado por
flujo-ancla/equip_map, fine-tune EfficientNet-B0/MobileNetV3, export ONNX). Plan aparte.

## Riesgos
- Transferencia a avatares de anime (modelos ImageNet/CLIP son de fotos reales) → el spike prueba
  varios; fallback E.4.
- Look-alikes caras animales → voto + abstención + flujo-ancla los cubren.
- Tamaño del build (onnxruntime ~pocos MB + modelo 20 MB chico / 350 MB CLIP) → preferir chico.
- ToS RNF-03: todo pixels-en-pantalla, ONNX es inferencia local → equivalente legal a lo actual.

## Decisiones pendientes (post-spike, necesitan OK del usuario)
- **Modelo final** (lo decide E.0 con números): chico ImageNet vs DINOv2 vs CLIP-onnx.
- **Ensemble vs reemplazo total** del descriptor (recomendado: ensemble primero — conserva 0-wrong).

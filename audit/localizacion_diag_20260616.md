# Diagnóstico de localización del grid-badge (L.0) — 2026-06-16

> Tras descartar el embedding (E.0: el descriptor ya discrimina ~92%@0-wrong; el cuello
> es la LOCALIZACIÓN, no la discriminación), se caracteriza el modo de falla.

## Qué se midió
Sobre los 30 crops `audit/grid_diag/*NOLOC*` (= región `_GRID_REGION` de frames donde la
localización del grid-badge falló), se reaplicó la lógica de `_selected_grid_tile_bbox`
(máscara HSV amarillo/lima → componentes → filtro de forma: tamaño-tile + hueco) para
clasificar la causa.

## Resultado
| Causa | Crops | Detalle |
|---|---|---|
| Anillo NO es tamaño-tile | 25/30 | Hay highlight pero ningún componente cae en la ventana de tile (~175×172px). **Mediana = 260 componentes** de máscara amarilla → el arte de discos (llama/oro) satura el rango HSV `[20-45 H, 90-255 S, 120-255 V]` y fragmenta. |
| Anillo roto (fragmentos chicos) | 4/30 | Frame de transición: el aro no se cierra → solo trozos < área mínima. |
| Sin highlight | 1/30 | Máscara vacía. |

## Lectura
- El cuello es el **frame de transición** (scroll a mitad): el anillo de selección no forma un
  cuadrado-tile limpio. La máscara amarilla es **muy ruidosa** (260 componentes del arte de discos).
- **Matiz RNF-02:** un frame de transición puede NO tener una selección estable. Forzar la
  localización ahí (p.ej. con cierre morfológico agresivo) arriesga recortar el badge de OTRO tile
  → dueño equivocado. NOLOC en transición es, en parte, **abstención correcta**.
- El sistema en vivo ya tiene dos mitigaciones: **voto multi-frame** (al asentarse el scroll, el
  frame es limpio y localiza 100% — confirmado: 180/180 sobre frames harvest) y el **detail-badge**
  (`crop_detail_badge`, 100% loc, fijo, fondo oscuro, ya vota al mismo acumulador).

## Por qué el QA en vivo daba "mayoría incierto" — hipótesis a verificar EN VIVO
Si el grid-badge localiza 100% al asentarse y el detail-badge localiza siempre y ambos votan, el
"incierto" debe venir del **sistema integrado**, no de un crop aislado. Candidatos:
1. **Timing de emisión:** el disco se emite (recomendación) ANTES de juntar votos de un frame
   asentado → decide con frames de transición.
2. **Voto/discriminación del detail-badge:** el detail-badge discrimina menos (~75% vs ~90% del
   grid) → abstiene seguido bajo el guard actual; el voto combinado no junta confianza.
3. **Localización del detail-badge en vivo:** en la extracción offline dio 167/180 (93%, no 100%)
   sobre frames harvest S18 → hay un gap a entender (¿frames de carga? ¿guard `_DET_SAT_MIN`?).

## Paso decisivo (RNF-02: medir el sistema real antes de tocarlo)
La causa raíz vive en el **pipeline integrado en vivo**, ahora medible porque la **fuga RNF-06 está
resuelta** (commit 0863319). Se propone un **QA en vivo instrumentado**: loguear por disco
seleccionado `{grid_loc, det_loc, grid_match, det_match, voto_final, frames_hasta_emitir}` y cruzar
con `audit/equip_map_20260612.json`. Eso dice exactamente cuál de los 3 candidatos es el cuello,
antes de cambiar localización (L.1) o timing/voto (L.2).

## Artefactos
- Diagnóstico: este doc. Datos: `audit/grid_diag/*NOLOC*` (30), frames `audit/harvest/` (latch).
- Lógica analizada: `app/core/detector.py::_selected_grid_tile_bbox` / `crop_grid_selected_badge` /
  `crop_detail_badge`.

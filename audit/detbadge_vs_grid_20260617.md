# Detail-badge vs Grid-badge — medición de discriminación (descriptor) · 2026-06-17

> Tras la redirección del usuario (olvidar la grilla volátil, usar el detail-badge del
> panel S17 + stats), se mide cuánto discrimina cada superficie con el descriptor.
> Set: `audit/harvest_badges/*__{grid,det}__*` (badges reales, etiqueta=latch certero;
> det re-extraído de S17 — antes salía de S18 por bug del extractor → ruido).

## Localización (extracción sobre frames S17)
- **grid**: 180/180 localizados.
- **det**: 171/180 (9 fallos = avatares baja-saturación tipo Lycaon, gap `_DET_SAT_MIN`).

## Discriminación (descriptor, leave-one-out)
| Superficie | top-1 crudo | wrong crudo | CERO-WRONG top-1 | abstención |
|---|---|---|---|---|
| GRID limpio | 95.0% | 5.0% | **92.2%** | 7.8% |
| DET limpio | 95.9% | 4.1% | **55.6%** | 44.4% |
| GRID realista n2 | 90.6% | 9.4% | 77.2% | 22.8% |
| DET realista n2 | 70.2% | 29.8% | 28.7% | 71.3% |

## Lectura clave
- **El top-1 CRUDO del det es igual de bueno (95.9% ≈ grid 95.0%)**: el detail-badge SÍ
  identifica bien al dueño la mayoría de las veces.
- **Pero al bar de 0-wrong cae a 55.6%** (vs grid 92.2%): el avatar es más chico → menos
  pixeles → menos MARGEN entre PJs → para garantizar 0 wrong por-frame hay que abstenerse mucho.
- **PERO los wrongs del det limpio son TODOS ×1** (harumasa→soukaku, lucia→zhao, lucy→cesar,
  pulchra→alice, seth→cissia, yixuan→piper…): **aleatorios, no sistemáticos**. → el **voto
  multi-frame los resuelve** (un frame malo suelto queda en minoría sobre un badge que vota
  en CADA frame). El metric "0-wrong por-frame" es pesimista para un sistema que vota.
- Bajo degradación realista aparecen confusiones semi-sistemáticas (imán "miyabi":
  anby/astrayao/dialyn/jane→miyabi) — a vigilar, pero el panel de detalle NO desliza, así que
  en vivo el det sufre MUCHO menos degradación que el grid en transición.

## Conclusión
El enfoque del usuario es **viable**: el detail-badge **localiza estable (sin el NOLOC del
grid, que era el cuello)** y su top-1 crudo (96%) + errores aleatorios → **voto multi-frame
da alta precisión**. El grid sigue sumando un voto de alta calidad CUANDO localiza.
- **Trade correcto:** se cambia margen-por-frame (peor en det) por localización estable
  (lo que L.0 mostró que era el cuello). El voto cierra la brecha de margen.
- **Gaps a manejar:** (1) localización det de baja-sat (Lycaon, 9/180) → bajar `_DET_SAT_MIN`
  o fallback al grid; (2) imán "miyabi" bajo degradación → reject-set/abstención.

## Próximo
QA en vivo con la instrumentación `DANIBOD_ID_DIAG` (ya lista) para confirmar en el sistema
integrado que det+voto sube el yield real (identificados/incierto/WRONG vs equip_map), y
calibrar el guard del det para que vote sin meter wrongs. Implementación: detail-badge
PRIMARIO para la decisión equipado/candidato/libre + grid como boost de voto + flujo-ancla.

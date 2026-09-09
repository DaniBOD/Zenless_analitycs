# Fase de CONFIABILIDAD del detector — endurecimiento anti-FP · 2026-07-07

**Estado:** CERRADO (código) · commit `96b4e13` en `main`. Pendiente: QA en vivo (mañana).
**Contexto:** **pausa la fase de extracción** (farmeo S2/S3 e inventario) hasta regular la
confiabilidad del detector. Dirección del usuario.

## Síntoma

En QA en vivo, navegando **solo menús** (eventos, guía rápida, banners, pase de batalla, menú
de pausa, modo libre/foto) el detector disparaba **falsos positivos (FP) constantes de S2**
(Resultado del desafío) **y S18** (perfil de agente) — ambos estados que capturan/reportan. El
sistema "quería" capturar discos donde no había ninguno.

## Metodología — QA negativo masivo (offline)

El usuario juntó **33 screenshots negativos** en
`Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/` (Eventos, Guia_Rapida,
Modo_Libre/foto, Menu_Pausa, Pase_batalla, Banners, Detalle_set_disco, Dispara_disco_descarte,
Resultado_desafio_otro_farmeo). Ninguno debe gatillar un estado de captura.

Harness nuevo `app/tests/unit/test_detector_fp_negative_qa.py`:
- Parametriza los 33 FP y **replica la decisión REAL del monitor** (`_monitor_decision` =
  `detector.classify()` + fallback `_deep_detect_s18` con **PaddleOCR real** si da S12 y no hay
  tab-bar). El tab-override ya vive dentro de `classify()`.
- Asserta `decision.code in allowed` según el grupo (por prefijo de nombre de archivo).
- Además vuelca `code · conf · method · template` en el mensaje de assert → sirve de **baseline
  de diagnóstico** (qué dispara y por qué path) además de guardia de regresión.

### Criterio "pasa" por grupo (decidido con el usuario)

| Grupo | Allowed | Razón |
|---|---|---|
| Eventos, Guia, Modo_Libre/foto, Menu_Pausa, Pase, Banners | `{S12}` | Deben ser NO reconocidas |
| `Detalle_set_disco` | `{S16, S12}` | S16 (modal Info de conjunto) es correcto y **no captura** |
| `Dispara_disco_descarte` | `{S11, S12}` | S11 (desmontaje) es correcto y **no captura** |
| `Resultado_desafio_otro_farmeo` | `{S12}` | Es un "RESULTADOS DEL DESAFÍO" real (mismo template) pero las recompensas NO son discos → **forzar S12** |

## Baseline: 15 FP / 33

- **11 por template S2**: S2 no tenía verificación secundaria → cualquier pantalla que matcheara
  el template `s2_resultado_desafio` a ≥0.80 pasaba (eventos/banners/guía/pase y el resultado de
  otro farmeo matcheaban por layout general).
- **3 por HSV S18** (`hsv_stats_grid`): fallback que detectaba "4+ líneas horizontales en el
  panel central → S18 0.55". Disparaba en Guia_Rapida (listas con separadores).
- **1 por HSV S10** (`hsv_green_bar`): barra EXP verde → S10 0.60, en Menu_Pausa.

## Fixes (commit `96b4e13`)

**1. `_verify_s2` (nuevo)** — alta en `_VERIFICATION_REGISTRY` (`app/core/detector.py`).
Verifica que S2 sea un **farmeo de discos** real contando **franjas de rareza** (bandas
horizontales gold/purple/blue al borde inferior de cada tile de disco = firma robusta del drop
de discos) en la grilla de recompensas. Helper `count_reward_rarity_strips` en `parser_s2.py`
(reutiliza la geometría `_grid_region`, sin duplicar; `_RARITY_BANDS` en HSV). Umbral
`_DISC_STRIP_MIN = 3` — **calibrado**: farmeo real da 3 (todas las capturas), pantallas sin
discos ≤2. Con <3 franjas ⇒ verify FALLA ⇒ el pipeline degrada la confianza ×0.7 y cae a **S12**.
Idea del usuario: distinguir el ícono del disco vs chips/monedas/otros items farmeables. Sin OCR
(RNF-06). Elimina los 11 FP de template (incl. `otro_farmeo` → S12).

**2. Removida rama HSV S18 `hsv_stats_grid`** (`_classify_by_hsv`). Fallback demasiado genérico
(cualquier menú con listas/separadores lo disparaba). S18 real ya se cubre por template
(s18a/b/c) + tab-override (`detect_active_tab`) + `_deep_detect_s18` (OCR, en el monitor).
Elimina los 3 FP de Guía.

**3. Removida rama HSV S10 `hsv_green_bar`**. El `green_ratio` NO separa: Menu_Pausa mide 0.377,
dentro del rango de S10 real (0.0–0.503; varias S10 reales dan 0.0 → ni siquiera es discriminante
positivo). Heurística FP-prone. S10 real usa template `s10_modal_upgrade` + `_verify_s10`.
Elimina el 1 FP.

**4. `monitor.py`** — diagnósticos `[s2_diag]`/`[s3_diag]` gateados por `_id_diag_on` (log del
resumen S2 y del ciclo del aggregator S3), para apoyar el QA en vivo de mañana.

## Regresión positiva (los fixes NO rompen la detección real)

En el mismo harness:
- **S2 farmeo real** (`01_Pantalla_Resultado_Desafio/*` + `s2_resultado_ejemplo_1/2`) → sigue S2
  (`_verify_s2` no sobre-rechaza: hay ≥3 franjas).
- **S18** (7 `atributos_base_ejemplo_*`) → sigue S18 tras remover la rama HSV.

## Resultado

- Harness negativo **33/33** en su allowed-set (con PaddleOCR real).
- Regresión positiva **13/13** (6 S2 + 7 S18).
- **Suite completa: 599 passed.**

## Pendiente

1. **QA en vivo (mañana):** navegar eventos/guía/banners/pausa + un resultado no-disco →
   confirmar **0 FP** en el log; farmeo real de discos → S2 + resumen sigue funcionando. Usar
   `-IdDiag` para ver los `[s2_diag]`/`[s3_diag]`.
2. **Reanudar la fase de extracción** (diferida): diagnóstico S2/S3 en vivo (has_s_discs /
   madurez), mejora del parseo de upgrade S10. Ver `project-context-IA.md` §5.

## Referencias

- Commit `96b4e13` (main). Archivos: `app/core/detector.py`, `app/core/parser_s2.py`,
  `app/core/monitor.py`, `app/tests/unit/test_detector_fp_negative_qa.py`.
- Plan: `.claude/plans/prosigue-en-planing-vivid-snowflake.md`.
- RNF-06 (CLAUDE.md §2): sin OCR para señales de detección donde alcance con pixels/color.

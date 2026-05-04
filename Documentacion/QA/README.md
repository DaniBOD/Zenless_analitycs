# Plan maestro QA — Proyecto ZZZ DaniBOD

**Versión:** v1.0 · 2026-05-01
**Alcance:** Estrategia de Quality Assurance para validar que la lógica diseñada en los RF se ejecuta correctamente extremo a extremo.
**Filosofía:** RNF-01 (ETL sin fallas) + RNF-02 (análisis minucioso, cero shortcuts) son las reglas no negociables. QA existe para hacerlas evidenciables, no decorativas.

---

## 1. Por qué este módulo

El proyecto tiene 8 RFs con diseño cerrado y 5 migraciones aplicadas, pero **ninguna línea del `.exe` standalone está escrita**. Cuando arranque la implementación (Fase 2 en adelante) habrá que validar:

- Que la lógica documentada (greedy + bonus pass de RF-06, runtime determinista de RF-12, retro-feedback bayesiano de RF-13, etc.) se ejecuta como está descrita.
- Que el OCR híbrido Tesseract+Paddle no inventa valores (RNF-02).
- Que los presupuestos de latencia (RNF-06) se cumplen bajo carga real, no solo en sandbox.
- Que las llamadas a Claude API permanecen dentro del cap mensual configurado y no alucinan sinergias inexistentes.
- Que tras cada patch del juego (~6 semanas) la base no degrada — sets/armas/PJs nuevos se ingieren sin romper integridad.

**Sin QA estructurado, los bugs llegan al usuario como recomendaciones erróneas durante el juego, exactamente lo opuesto a la propuesta de valor.**

---

## 2. Capas de testing

El proyecto trabaja con **5 capas complementarias**. Cada una atrapa una clase distinta de bug.

| Capa | Nombre | Cuándo se ejecuta | Quién lo hace | Cobertura |
|------|--------|-------------------|---------------|-----------|
| **L1** | Validación de schema y datos | Tras cada migración, carga, merge | Automático (`PRAGMA` + scripts) | Integridad referencial, CHECK, FK, constraints |
| **L2** | Unit tests deterministas | Cada commit en `app/core/*` | Automático (`pytest`) | Funciones puras: scoring, recommender, optimizer, tier_list_calculator, retro_feedback |
| **L3** | Integration tests con fixture | Pre-merge a `main` | Automático (`pytest` con DB temporal) | Flujos cross-módulo (captura → OCR → scoring → insert + auto-trigger RF-04→RF-06) |
| **L4** | Pruebas reales en juego (manual) | Daniel jugando | Manual con checklist | OCR sobre frames reales, latencia percibida, hotkeys globales, toast lifecycle, cobertura de pantallas del juego |
| **L5** | Validación cruzada con fuentes | Semanal + post-patch | Mixto: scrapers + revisión manual | Comparación contra Prydwen tier list, Hakush.in datamine, screenshots HoYoLAB del propio jugador |

**Regla:** un RF se considera **listo para producción** cuando pasa L1+L2+L3 automáticamente y Daniel lo valida en L4 sobre 10+ casos reales sin rehallar bugs.

---

## 3. Matriz de cobertura por RF

| RF | L1 ETL | L2 Unit | L3 Integration | L4 Real | L5 Cruzada | Doc QA |
|----|:------:|:-------:|:--------------:|:-------:|:----------:|--------|
| RF-01 (roster) | ✅ | — | — | ✅ | ✅ | [QA-01_ETL_Integridad.md](./QA-01_ETL_Integridad.md) |
| RF-02 (inventario discos) | ✅ | — | — | ✅ | ✅ | [QA-01_ETL_Integridad.md](./QA-01_ETL_Integridad.md) |
| RF-03 (inventario armas) | ✅ | — | — | ✅ | ✅ | [QA-01_ETL_Integridad.md](./QA-01_ETL_Integridad.md) |
| RF-04 (sync equipo) | ✅ | ✅ | ✅ | ✅ | — | [QA-03_OCR_y_Captura.md](./QA-03_OCR_y_Captura.md) |
| RF-05 (sync upgrade) | ✅ | ✅ | ✅ | ✅ | — | [QA-03_OCR_y_Captura.md](./QA-03_OCR_y_Captura.md) |
| RF-06 (optimizador build) | — | ✅ | ✅ | ✅ | ✅ | [QA-02_Scoring_y_Optimizador.md](./QA-02_Scoring_y_Optimizador.md) |
| RF-09 (OCR) | — | ✅ | ✅ | ✅ | — | [QA-03_OCR_y_Captura.md](./QA-03_OCR_y_Captura.md) |
| RF-11 (UI .exe) | — | — | ✅ | ✅ | — | [QA-06_Performance_y_UX.md](./QA-06_Performance_y_UX.md) |
| RF-12 (team-aware IA) | ✅ | ✅ | ✅ | ✅ | ✅ | [QA-04_IA_Catalogadora.md](./QA-04_IA_Catalogadora.md) |
| RF-13 (lategame) | ✅ | ✅ | ✅ | ✅ | ✅ | [QA-05_Lategame_y_Bayesiano.md](./QA-05_Lategame_y_Bayesiano.md) |
| RF-14 (W-Engines) | ✅ | ✅ | ✅ | ✅ | ✅ | [QA-02_Scoring_y_Optimizador.md](./QA-02_Scoring_y_Optimizador.md) |
| Transversal latencia | — | ✅ | ✅ | ✅ | — | [QA-06_Performance_y_UX.md](./QA-06_Performance_y_UX.md) |
| Por patch ZZZ | ✅ | — | ✅ | ✅ | ✅ | [QA-07_Regresion_Patches.md](./QA-07_Regresion_Patches.md) |

---

## 4. Criterios de aceptación globales

Aplican a todos los RFs salvo override explícito en su QA específico.

### 4.1 Datos
- `PRAGMA integrity_check` retorna `ok` tras cada operación que toca DB.
- `PRAGMA foreign_key_check` retorna 0 filas tras cada operación.
- Toda inserción con campos derivados (`score_evaluacion`, `agentes_compatibles`, `confianza`) deja registro auditable en su tabla `*_evaluations` o `ai_catalog_runs`.
- Backup de DB antes de cualquier merge de IDs o ALTER TABLE no idempotente.

### 4.2 Lógica
- Funciones de scoring son **deterministas:** mismo input → mismo output, byte por byte.
- Funciones puras tienen al menos **1 unit test por golden case documentado** en su QA específico.
- Pipelines con OCR exponen confianza por campo; campos por debajo de un umbral se marcan `requires_review=1` en lugar de inventarse.

### 4.3 Performance (RNF-06)
- Cada superficie con presupuesto de latencia **mide y registra `latency_p50` + `latency_p99`** en `app/core/metrics.py` (a crear).
- Una superficie que excede su p99 más de 3 días seguidos abre un task de regresión.

### 4.4 IA (RF-12, RF-14)
- Cada llamada a Claude API queda registrada en `ai_catalog_runs` con `tokens_input`, `tokens_output`, `costo_usd`, `prompt_hash`, `response_json`.
- Sinergias generadas con `confianza < 0.50` no se aplican automáticamente; se marcan para revisión manual.
- El cap mensual (`user_config.toml::ai_catalog.cap_usd_mensual`) se respeta; al alcanzar el 90 % se notifica al usuario.

### 4.5 OCR (RF-09)
- Precisión sobre golden set de 50 capturas reales: **≥ 95 %** en main stat + slot + set, **≥ 90 %** en substats con rolls.
- Latencia OCR por disco: **< 200 ms** p99 (presupuesto interno de RF-11 es 180 ms).

### 4.6 Compatibilidad TOS (RNF-03)
- Cero llamadas a APIs de proceso del juego, cero injection, cero simulación de input.
- El `.exe` solo lee pixels; ese principio es validado por revisión de código en cada PR que toque `app/core/capturer.py` o `app/core/detector.py`.

---

## 5. Roles del QA

| Rol | Responsable | Frecuencia |
|-----|-------------|------------|
| Diseño de unit tests (L2) | Quien implementa el módulo | Mismo PR del módulo |
| Mantenimiento de fixtures (L3) | Quien implementa el módulo | Mismo PR del módulo |
| Pruebas reales en juego (L4) | **Daniel** | Continuo durante el uso normal |
| Captura de regresiones | **Daniel** + IA agente | Cuando aparece comportamiento inesperado |
| Validación cruzada con fuentes (L5) | Scrapers automáticos + revisión Daniel | Semanal + post-patch |
| Revisión por patch (L4 + L5) | **Daniel** con checklist [QA-07](./QA-07_Regresion_Patches.md) | Cada patch ZZZ (~6 semanas) |
| Triage de hallazgos | IA agente con consulta a Daniel | On-demand al recibir bug |

**Daniel hace L4** porque las pruebas reales requieren jugar ZZZ con la app corriendo y observar el toast/panel/dashboard. Ningún CI puede simular esto sin violar TOS.
**La IA agente puede generar tests L1-L3** y proponer regresiones reproducibles en L4 (lista de pasos), pero no sustituye la validación percibida.

---

## 6. Capa transversal: telemetría y observabilidad

El sistema debe registrar suficientes métricas como para responder estas preguntas operativas sin tener que reproducir el bug:

| Pregunta | Tabla / log que la responde |
|----------|-----------------------------|
| ¿El optimizador tardó más de 500 ms? | `metrics_latency` (a crear) con `(superficie, p50_ms, p99_ms, fecha)` |
| ¿Cuánto gasté en Claude API este mes? | `ai_catalog_runs` agregada por mes |
| ¿Qué disco tomó la decisión de "Equipar"? | `inventory_disc_evaluations` con `score`, `recomendacion`, `agente_target`, `arquetipo` |
| ¿Por qué un par dejó de tener override RF-12? | `team_synergy_adjustments` con `motivo_bayesiano`, `runs_evidencia`, `confianza_pre/post` |
| ¿Qué runs entraron en el último snapshot del tier list? | `tier_list_personal` con `snapshot_id` + JOIN con `lategame_runs` por fecha |
| ¿Cuántos discos OCR fueron marcados `requires_review`? | `inventory_disc_evaluations` con `requires_review=1` |

> **Decisión QA:** crear en migración futura una tabla `metrics_latency` y un wrapper `app/core/metrics.py` que toda función con presupuesto de latencia llame al inicio y al fin (decorator `@measure_latency('superficie')`). Registro en RAM con flush periódico (cada 60 s) para no saturar disco.

---

## 7. Roadmap QA por fase

Sincronizado con el roadmap principal del proyecto.

| Fase | RFs | QA prioritario | Salidas esperadas |
|------|-----|----------------|-------------------|
| **Fase 1.x (cerrada)** | RF-01/02/03 + 5 migraciones | L1 ETL sobre DB actual ([QA-01](./QA-01_ETL_Integridad.md)) | Snapshot de checks aplicados a `danibod_zzz_v2.db` 2026-05-01 |
| **Fase 2** (RF-04/05/06/09/11 base) | Scoring + optimizador + OCR + UI | L2 unit golden cases ([QA-02](./QA-02_Scoring_y_Optimizador.md), [QA-03](./QA-03_OCR_y_Captura.md)) + L4 toasts reales | 50+ unit tests verdes; toast disparado en <500 ms p99 sobre 30 frames reales |
| **Fase 3** (RF-12) | Team-aware IA | L1 sinergias canónicas + L5 sanity ([QA-04](./QA-04_IA_Catalogadora.md)) | Caso Ellen+Dialyn pasa con confianza ≥0.85; cap mensual respetado |
| **Fase 4** (RF-13) | Lategame + bayesiano | L2 buckets + L3 pipeline F11 ([QA-05](./QA-05_Lategame_y_Bayesiano.md)) | 20 runs reales validados; tier list reproduce delta vs Prydwen documentado |
| **Fase 5** (RF-14) | W-Engines | L2 scoring contextual ([QA-02](./QA-02_Scoring_y_Optimizador.md)) | Caso "la roca" ranquea S+ DA / B HZ; armas `trigger_tipo='always'` invariantes a contenido |
| **Continuo** | Patches ZZZ | L5 + L1 ([QA-07](./QA-07_Regresion_Patches.md)) | Checklist completo por patch sin pérdida de integridad |

---

## 8. Cómo usar este módulo

1. **Antes de implementar un RF nuevo:** abrir su QA específico, escribir los unit tests planeados como TODO, definir los golden cases en código.
2. **Durante implementación:** ir marcando golden cases verdes; mantener los que fallan visibles en CI.
3. **Antes de pasar a "Cerrado en producción":** validar L4 sobre 10+ casos reales con Daniel; documentar capturas como evidencia bajo `Documentacion/QA/evidencia/<RF>/<fecha>/`.
4. **Tras un patch ZZZ:** seguir [QA-07_Regresion_Patches.md](./QA-07_Regresion_Patches.md) en orden.
5. **Si aparece un bug en producción:** crear regresión reproducible (script en `app/tests/regressions/<fecha>_<descripcion>.py`) **antes** de fixear. La regresión queda como L2 perpetuo.

---

## 9. Sub-documentos de este módulo

| Doc | Cubre | Cuándo consultarlo |
|-----|-------|--------------------|
| [QA-01_ETL_Integridad.md](./QA-01_ETL_Integridad.md) | L1: schema, FK, integridad, migraciones, backups | Al tocar DB |
| [QA-02_Scoring_y_Optimizador.md](./QA-02_Scoring_y_Optimizador.md) | L2/L3: RF-06 + RF-14, golden cases scoring, top-3 builds | Al implementar `scoring.py`, `optimizer.py`, `weapon_*` |
| [QA-03_OCR_y_Captura.md](./QA-03_OCR_y_Captura.md) | L2/L4: RF-04/05/09 OCR híbrido, edge cases visuales | Al implementar `ocr_*`, `sync_*` |
| [QA-04_IA_Catalogadora.md](./QA-04_IA_Catalogadora.md) | L1/L5: RF-12 sinergias IA, hallucination, cap costo, modelo local roadmap | Al implementar `ai_catalog.py`, `team_optimizer.py` |
| [QA-05_Lategame_y_Bayesiano.md](./QA-05_Lategame_y_Bayesiano.md) | L2/L3/L5: RF-13 captura F11, tier list, retro-feedback | Al implementar `lategame_capture.py`, `tier_list_calculator.py`, `retro_feedback.py` |
| [QA-06_Performance_y_UX.md](./QA-06_Performance_y_UX.md) | L4 transversal: presupuestos latencia, RAM, hotkeys, accesibilidad | Al medir cualquier superficie sensible a latencia |
| [QA-07_Regresion_Patches.md](./QA-07_Regresion_Patches.md) | L1+L4+L5: checklist por patch ZZZ | Cada ~6 semanas al actualizar el juego |

---

## 10. Pendientes operativos del propio QA

- [ ] Crear migración `2026-05-XX_06_metrics_latency.sql` con tabla `metrics_latency` y vistas agregadas.
- [ ] Crear `app/core/metrics.py` con decorator `@measure_latency('superficie')`.
- [ ] Crear `app/tests/` con estructura `unit/`, `integration/`, `regressions/`, `fixtures/`.
- [ ] Crear `app/tests/fixtures/golden_cases.json` con los casos canónicos referenciados en cada sub-doc QA.
- [ ] Crear `Documentacion/QA/evidencia/` (gitignored salvo .gitkeep) para almacenar capturas de pruebas L4.
- [ ] Decidir framework: `pytest` + `pytest-cov` + `pytest-benchmark` (recomendado).
- [ ] Definir CI: GitHub Actions con job para L1+L2+L3 + reporte de cobertura.

---

*Mantener este README sincronizado con el resto del proyecto. Cada vez que se cierre un RF o se aplique migración nueva, actualizar §3 (matriz cobertura) y §7 (roadmap).*

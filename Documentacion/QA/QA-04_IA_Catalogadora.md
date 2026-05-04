# QA-04 — IA Catalogadora (RF-12) y roadmap modelo local

**Capa:** L1 (datos generados por IA) + L5 (cruzada con fuentes humanas) + L4 (validación percibida)
**RFs cubiertos:** RF-12 (team-aware con Claude API).
**Cuándo consultar:** al implementar `ai_catalog.py`, al diseñar prompts, al monitorear costos, al evaluar futuro switch a modelo local.

> **Principio:** la IA es **catalogadora, no decisora**. Su rol es poblar tablas (`team_synergies`, `team_compositions`) que el runtime determinista de RF-12 luego consume con lookups <50 ms. Esto significa que la calidad del sistema se juega 100% en la validación de lo que la IA genera offline.
>
> **Anti-principio:** nunca poner Claude API en el camino crítico de decisión en tiempo real. Si un día Claude responde lento o genera basura, el sistema debe seguir funcionando (con datos cacheados; degradación grácil).

---

## 1. Qué se valida exactamente

`ai_catalog.py` hace dos tipos de llamadas a Claude API:

| Operación | Modelo recomendado | Output esperado | Tabla destino |
|-----------|-------------------|-----------------|---------------|
| `team_synergy_pair(pj_a, pj_b)` | `claude-sonnet-4-6` | JSON con `sinergia_existe`, `tipo`, override pesos, set recomendado, confianza, justificación | `team_synergies` |
| `team_composition_topN(pj_principal, n=5)` | `claude-opus-4-6` | JSON con top-N composiciones, `score_composicion`, `flag_anti_shill`, justificación | `team_compositions` |

QA debe validar:
- **Forma del output** (schema JSON estricto, sin texto suelto).
- **Plausibilidad** (los pares con sinergia obvia deben aparecer; los obvios negativos también).
- **Costos** (cap mensual respetado, retries acotados).
- **Hallucination detection** (set_id que no existe, PJs que no son del roster, valores fuera de rango).
- **Reproducibilidad razonable** (con prompt caching, dos llamadas seguidas deben dar resultados iguales o casi).

---

## 2. Validación de schema del output

Cada respuesta de Claude pasa por un validador estricto antes de tocar la DB.

### 2.1 Schema esperado para `team_synergy_pair`
```python
SCHEMA_SYNERGY = {
    "type": "object",
    "required": ["sinergia_existe","confianza","justificacion"],
    "properties": {
        "sinergia_existe": {"type": "boolean"},
        "tipo": {
            "type": "string",
            "enum": [
                "disorder_elemento","additional_ability_faccion",
                "core_passive_ult","stun_synergy","support_buff",
                "anomaly_chain","element_shred","off_field_proc",
                "no_synergy"
            ]
        },
        "set_recomendado_pj_a": {"type": ["integer","null"]},
        "set_recomendado_pj_b": {"type": ["integer","null"]},
        "override_pesos_pj_a": {"type": ["object","null"]},
        "override_pesos_pj_b": {"type": ["object","null"]},
        "descripcion_buff": {"type": "string"},
        "confianza": {"type": "number","minimum":0,"maximum":1},
        "justificacion": {"type": "string","minLength": 50}
    }
}
```

### 2.2 Test L2 sobre fixture de respuestas
```python
# app/tests/unit/test_ai_catalog.py
import jsonschema, json, pytest
from app.core.ai_catalog import validate_response, SCHEMA_SYNERGY

@pytest.mark.parametrize('fixture', [
    'fixtures/ai_responses/synergy_ellen_dialyn.json',
    'fixtures/ai_responses/synergy_miyabi_yanagi.json',
    'fixtures/ai_responses/synergy_no_synergy_anton_zhao.json',
])
def test_response_schema(fixture):
    data = json.load(open(fixture))
    jsonschema.validate(instance=data, schema=SCHEMA_SYNERGY)
```

### 2.3 Validación de FKs implícitas
Si Claude devuelve `set_recomendado_pj_a=99` pero `disc_sets` tiene IDs 1-26, la respuesta es **inválida** y se rechaza antes de insertar:

```python
def validate_set_ids(response, db):
    valid_set_ids = {r[0] for r in db.execute("SELECT id FROM disc_sets")}
    for key in ['set_recomendado_pj_a','set_recomendado_pj_b']:
        v = response.get(key)
        if v is not None and v not in valid_set_ids:
            raise HallucinationError(f"{key}={v} no existe en disc_sets")
```

Misma validación para `pj_id` contra `agents` y para `tipo` contra el enum cerrado.

---

## 3. Casos canónicos del roster — golden L5

Estos casos son referencias compartidas con el resto del proyecto (especialmente RF-12 §8 y QA-05). La IA debe acertarlos antes de considerarse calibrada.

### 3.1 Caso A — Ellen + Dialyn → Puffer Electro
**Fuente humana:** README §3.1 RF-12. La Core Skill de Dialyn habilita Ult adicional que se beneficia del bonus electric/energy de Puffer Electro, sustituyendo el Polar Metal habitual de Ellen.

| Campo | Esperado |
|-------|----------|
| `sinergia_existe` | true |
| `tipo` | `core_passive_ult` |
| `set_recomendado_pj_ellen` | `Puffer Electro` (id 40) |
| `confianza` | ≥ 0.85 |
| `descripcion_buff` | menciona "Ult adicional" o equivalente |

Test:
```python
def test_ellen_dialyn_canonical():
    resp = ai_catalog.team_synergy_pair('Ellen', 'Dialyn')
    assert resp.sinergia_existe == True
    assert resp.tipo == 'core_passive_ult'
    assert resp.set_recomendado_para('Ellen') == 40   # Puffer Electro
    assert resp.confianza >= 0.85
```

Si este caso falla, la IA está mal prompteada o el modelo cambió. Investigar antes de avanzar.

### 3.2 Caso B — Miyabi + Yanagi → Section 6 Additional Ability
| Campo | Esperado |
|-------|----------|
| `sinergia_existe` | true |
| `tipo` | `additional_ability_faccion` |
| `descripcion_buff` | menciona Section 6 o facción común |
| `confianza` | ≥ 0.80 |

### 3.3 Caso C — Burnice + Lucy → Sons of Calydon
| Campo | Esperado |
|-------|----------|
| `sinergia_existe` | true |
| `tipo` | `additional_ability_faccion` |
| `descripcion_buff` | menciona Sons of Calydon |
| `confianza` | ≥ 0.80 |

### 3.4 Caso D — sin sinergia obvia (Antón + Zhao)
PJs A-rank en distintos elementos sin facción común ni sinergia mecánica.
```python
def test_no_synergy_canonical():
    resp = ai_catalog.team_synergy_pair('Antón', 'Zhao')
    assert resp.sinergia_existe == False
    assert resp.tipo == 'no_synergy'
    assert resp.confianza >= 0.70    # alta confianza en "no hay nada"
```

### 3.5 Caso E — composición Miyabi top-1 debe contener Yanagi
```python
def test_miyabi_topcomp():
    comp = ai_catalog.team_composition_topN('Miyabi', n=5)
    top1 = comp.compositions[0]
    assert 'Yanagi' in top1.companions
    # Al menos 1 stunner o 1 support en la top-5
    assert any(stunner_or_support(c) for c in comp.compositions[:5])
```

### 3.6 Caso F — `flag_anti_shill` aparece cuando aplica
La composición Ellen + Dialyn (anti-shill) debe tener `flag_anti_shill=True` en la composición que tenga ese par:
```python
comp = ai_catalog.team_composition_topN('Ellen', n=5)
ellen_dialyn_comp = next(c for c in comp.compositions
                          if 'Dialyn' in c.companions)
assert ellen_dialyn_comp.flag_anti_shill == True
```

---

## 4. Detección de alucinaciones

Patrones que disparan rechazo automático:

| Patrón | Razón |
|--------|-------|
| `set_recomendado_pj_X` con id no en `disc_sets` | Claude inventó set |
| `tipo` fuera del enum cerrado (§2.1) | Claude inventó categoría |
| PJ name en `team_compositions.companions` no existe en `agents` | Claude inventó PJ |
| `confianza > 1.0` o `< 0.0` | Output mal formado |
| `confianza == 1.0` exacto | Sospechoso (la IA rara vez está absolutamente segura — flag para revisión) |
| `descripcion_buff` < 50 caracteres | Insuficiente justificación |
| Mismo `(pj_a, pj_b)` con dos respuestas distintas en una semana | Inconsistencia → comparar con prompt cache, posible bug |
| Sinergia entre PJ y sí mismo (`pj_a == pj_b`) | Bug del prompt o de la lógica de batching |

Test L2:
```python
@pytest.mark.parametrize('bad_response', [
    {'set_recomendado_pj_a': 999, 'sinergia_existe': True},
    {'tipo': 'inventado_por_claude'},
    {'confianza': 1.5},
    {'descripcion_buff': 'corto'},
])
def test_hallucination_rejected(bad_response):
    with pytest.raises(HallucinationError):
        ai_catalog._persist_response(bad_response)
```

---

## 5. Costos: cap, observabilidad y retries

### 5.1 Cap mensual
`user_config.toml::ai_catalog.cap_usd_mensual` (default $5/mes).

```python
def test_cap_respected():
    config['ai_catalog']['cap_usd_mensual'] = 0.10
    # Forzar 1000 llamadas — debe parar antes
    for _ in range(1000):
        ai_catalog.team_synergy_pair_safe(...)
    spent = sum_costo_mes_actual()
    assert spent <= 0.10 * 1.05    # margen 5% por la última llamada en curso
    assert ai_catalog.cap_alcanzado_callbacks_invocados == True
```

### 5.2 Logging de cada llamada
Toda llamada a Claude API queda en `ai_catalog_runs`:
```sql
SELECT operacion, modelo, tokens_input, tokens_output, costo_usd,
       duracion_ms, exito, prompt_hash
FROM ai_catalog_runs
WHERE timestamp >= datetime('now','-1 day');
```

Test:
```python
def test_audit_logged():
    before = count('ai_catalog_runs')
    ai_catalog.team_synergy_pair('Ellen','Dialyn')
    after = count('ai_catalog_runs')
    assert after == before + 1

    last = db.execute("SELECT * FROM ai_catalog_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert last.operacion == 'team_synergy_pair'
    assert last.tokens_input > 0
    assert last.tokens_output > 0
    assert last.costo_usd > 0
    assert last.duracion_ms > 0
```

### 5.3 Retries y backoff
- Reintentos: máx 3, backoff exponencial 1s/2s/4s.
- Tras 3 fallos: marcar el par como `error` en `ai_catalog_runs.exito=0`, NO insertar en `team_synergies`.
- El job de seed completo no se aborta por un par fallado — sigue con los demás y deja una lista de retry.

### 5.4 Prompt caching
Claude API soporta prompt caching. El prompt sistema (roster + catálogo de sets + descripciones de habilidades) debe ir cacheado. Test:
```python
def test_prompt_caching_savings():
    # Primera llamada — escribir caché
    r1 = ai_catalog.team_synergy_pair('Ellen','Dialyn')
    cost1 = r1.costo_usd

    # Segunda llamada con mismo system prompt — leer caché
    r2 = ai_catalog.team_synergy_pair('Ellen','Yanagi')
    cost2 = r2.costo_usd

    # cost2 debe ser sustancialmente menor (≥30% ahorro esperado con cache hit)
    assert cost2 < cost1 * 0.85
```

---

## 6. Reproducibilidad y consistencia

Claude no es 100% determinista pero con `temperature=0` debería ser muy estable.

### 6.1 Test de variabilidad
```python
def test_consistency_across_runs():
    runs = [ai_catalog.team_synergy_pair('Ellen','Dialyn') for _ in range(5)]

    # set_recomendado debe ser idéntico en las 5
    sets = {r.set_recomendado_para('Ellen') for r in runs}
    assert len(sets) == 1

    # confianza puede variar pero <0.05
    confs = [r.confianza for r in runs]
    assert max(confs) - min(confs) < 0.05
```

Si la variabilidad es mayor, el prompt no es lo suficientemente específico — refinarlo.

### 6.2 Versionado del prompt
Cada cambio en el prompt → nueva versión. `ai_catalog_runs.modelo_version` tracea el prompt usado para auditar cuándo cambió la calidad de las respuestas.

---

## 7. Validación cruzada con Prydwen (L5)

Los `team_synergies` generados por la IA deben coincidir con el conocimiento humano consolidado. Métrica:

```python
def test_synergies_align_with_prydwen():
    pairs_with_synergy = db.execute(
        "SELECT pj_a_id, pj_b_id FROM team_synergies "
        "WHERE sinergia_existe=1 AND confianza>=0.80"
    ).fetchall()

    prydwen_known = load_prydwen_known_synergies()  # de scrape

    overlap = set(pairs_with_synergy) & set(prydwen_known)
    coverage = len(overlap) / len(prydwen_known)
    assert coverage >= 0.80    # IA debe encontrar ≥80% de las sinergias documentadas
```

Si la cobertura es <80%: el prompt está perdiendo información. Iterar.

Si la IA encuentra sinergias **adicionales** no documentadas en Prydwen: no es bug — son los casos `flag_anti_shill` que justifican el RF. Pero deben validarse manualmente con L4 (jugarlas y ver si funcionan; eso lo cubre RF-13 con runs reales).

---

## 8. Pruebas L4 reales

Daniel valida en juego con composiciones recomendadas por la IA:

| Caso L4 | Acción | Resultado esperado |
|---------|--------|---------------------|
| Jugar Ellen + Dialyn + (X) en Shiyu | composición sugerida `flag_anti_shill=True` | obtiene 3★ con tiempo competitivo |
| Cambiar Polar Metal → Puffer Electro en Ellen para ese equipo | re-equipar y jugar | DPS de Ellen NO baja (si baja: la IA se equivocó) |
| Composición top-1 vs top-5 para Miyabi | jugar ambas y comparar | top-1 debe ser ≥ top-5 en `rate_3star` agregado tras 5+ runs |

Daniel registra en `Documentacion/QA/evidencia/RF-12/<fecha>_<caso>.md` con:
- Composición jugada.
- Resultado (estrellas, tiempo).
- Su criterio (¿la IA acertó?).

Este registro alimenta el bayesiano de RF-13 — ver [QA-05_Lategame_y_Bayesiano.md](./QA-05_Lategame_y_Bayesiano.md).

---

## 9. Roadmap modelo local (post-v1, idea futura)

Daniel mencionó: hardware RX 9060 XT 16GB VRAM, futuro fallback a modelo local. Documentado como **nota de roadmap, no compromiso**.

### 9.1 Hardware disponible
- RX 9060 XT 16GB VRAM.
- ROCm/HIP en Windows tiene soporte limitado vs CUDA. Considerar si se usa Linux o WSL2.

### 9.2 Alternativas plausibles a evaluar (cuando llegue el momento)
| Opción | Motor | Modelo | Ventana | VRAM | Comentario |
|--------|-------|--------|---------|------|------------|
| A | Ollama | Llama 3.1 8B Q5 | 8K | ~6 GB | Liviano, bajo costo, calidad media |
| B | Ollama | Qwen 2.5 14B Q4 | 32K | ~10 GB | Buena relación calidad/tamaño |
| C | Ollama | Mistral Small 22B Q4 | 32K | ~14 GB | Cerca del límite de VRAM |
| D | llama.cpp | DeepSeek-R1 distill 14B Q4 | 32K | ~10 GB | Razonamiento bueno |
| E | vLLM (Linux) | Cualquiera de las anteriores | — | — | Throughput alto si hay batching |

Sin compromiso. La elección dependerá de cómo se vea el ecosistema cuando se evalúe.

### 9.3 QA para modelo local cuando se implemente
Cuando se evalúe el switch:

```python
# Comparar Claude vs modelo local sobre el mismo set de pares canónicos
casos_canonicos = ['Ellen-Dialyn','Miyabi-Yanagi','Burnice-Lucy','Anton-Zhao','...']

for caso in casos_canonicos:
    resp_claude = ai_catalog.team_synergy_pair(*caso, backend='claude')
    resp_local  = ai_catalog.team_synergy_pair(*caso, backend='ollama_qwen14b')
    # comparar set_recomendado, tipo, confianza
    log_divergencia(caso, resp_claude, resp_local)
```

Métricas para considerar el switch viable:
- **Coincidencia top-1** (set recomendado) ≥ 85% sobre 100 pares canónicos.
- **Coverage de sinergias** vs Prydwen ≥ 75% (vs 80% de Claude — un poco menos aceptable porque ahorra costo).
- **Tiempo por inferencia** ≤ 8 s en RX 9060 XT (vs 2-4 s de Claude API).
- **Costo de electricidad** estimado < costo de Claude API en uso normal.

### 9.4 Híbrido (lo más pragmático)
Cuando se decida, lo más probable es híbrido:
- **Claude API** para casos críticos (composiciones top-N, sinergias complejas, dudosas).
- **Modelo local** para casos masivos baratos (refresh trimestral de 990 pares, primer pase rápido).
- Daniel usa la lógica `confianza_local < 0.75 → escalar a Claude API`.

Eso requiere que `ai_catalog.py` tenga la abstracción `backend: ['claude','local','hybrid']` desde v1, aunque el local no se implemente. **Recomendación de diseño:** el RF-12 implementa la interfaz abstracta hoy; los modelos locales se enchufan después sin tocar la lógica de validación L1/L5.

---

## 10. Cobertura mínima antes de cerrar Fase 3 (RF-12)

- [ ] Validador de schema implementado y testeado (§2).
- [ ] 5 casos canónicos pasan (§3 Caso A-F).
- [ ] Tests de hallucination detection cubriendo §4.
- [ ] Cap mensual respetado en stress test (§5.1).
- [ ] Audit logging completo en `ai_catalog_runs` (§5.2).
- [ ] Cobertura cruzada vs Prydwen ≥ 80% (§7).
- [ ] L4 Daniel: 5 composiciones recomendadas jugadas con resultado documentado.
- [ ] Diseño del backend abstracto listo para enchufe futuro de modelo local (§9.4).

---

*La IA es un asistente que puede equivocarse. El valor del sistema viene de validar lo que genera, no de confiar ciegamente. Ese es el espíritu detrás de la confianza ajustada bayesianamente en RF-13.*

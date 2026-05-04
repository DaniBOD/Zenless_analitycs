# QA-05 — Lategame y Retro-feedback Bayesiano (RF-13)

**Capa:** L2 (unit) + L3 (integration) + L5 (cruzada con Prydwen + scrapers)
**RFs cubiertos:** RF-13 (validación lategame + tier list personal + retro-feedback bayesiano).
**Cuándo consultar:** al implementar `lategame_capture.py`, `tier_list_calculator.py`, `retro_feedback.py`, scrapers de enemies/cycles, hotkey F11.

> **Principio:** RF-13 es donde el sistema **cierra el loop empírico**. Cualquier sinergia que la IA generó en RF-12 termina validada (o invalidada) por runs reales que Daniel juega. La calidad del bayesiano determina si el sistema converge a la realidad o se queda atrapado en sesgos de la IA o de Prydwen.

---

## 1. Pipeline a validar

```
[Daniel termina run en Shiyu/DA] → F11 → 2 screenshots (resumen + Battle Stats)
   → ocr_backend (Tesseract texto + Paddle números)
   → parser breakdown DMG
   → validación consistencia (Σ DMG ≈ 100%, PJs en roster)
   → INSERT lategame_runs + lategame_run_damage
   → si runs_nuevos ≥ 3 (o domingo 03:00) → recálculo tier list
   → snapshot atómico tier_list_personal
   → comparar con prydwen_tier_snapshots → delta
   → para cada equipo recomendado por RF-12 con ≥3 runs → retro-feedback
   → UPDATE team_synergies.confianza
   → INSERT team_synergy_adjustments (auditoría)
```

Cada nodo tiene checks específicos.

---

## 2. Captura F11 — golden cases OCR

`fixtures/lategame/` debe contener parejas (resumen, battle_stats) reales con su transcripción esperada.

### 2.1 Estructura
```
fixtures/lategame/
  shiyu_001_3star_98s_miyabi_yanagi_astra/
    resumen.png
    battle_stats.png
    expected.json
  da_001_3star_180s_lycaon_burnice_lucy/
    ...
```

### 2.2 JSON esperado por run
```json
{
  "contenido": "shiyu_critical",
  "ciclo_id": 12,
  "frente": 1,
  "fecha": "2026-05-XX",
  "estrellas": 3,
  "tiempo_segundos": 98,
  "equipo": ["Miyabi","Yanagi","Astra Yao"],
  "breakdown_dmg": [
    {"agente":"Miyabi",   "dmg_total": 4_200_000, "dmg_porcentaje": 62.0},
    {"agente":"Yanagi",   "dmg_total": 2_100_000, "dmg_porcentaje": 31.0},
    {"agente":"Astra Yao","dmg_total":   470_000, "dmg_porcentaje":  7.0}
  ]
}
```

### 2.3 Test L2 sobre golden set
```python
def test_lategame_capture_golden():
    for case_dir in Path('fixtures/lategame').iterdir():
        expected = json.loads((case_dir / 'expected.json').read_text())
        actual = lategame_capture.process_pair(
            case_dir / 'resumen.png',
            case_dir / 'battle_stats.png'
        )
        assert actual.contenido == expected['contenido']
        assert actual.estrellas == expected['estrellas']
        assert abs(actual.tiempo_segundos - expected['tiempo_segundos']) <= 2
        assert sorted(actual.equipo) == sorted(expected['equipo'])

        for got, exp in zip(actual.breakdown_dmg, expected['breakdown_dmg']):
            assert got['agente'] == exp['agente']
            assert abs(got['dmg_porcentaje'] - exp['dmg_porcentaje']) < 1.5
```

### 2.4 Validación de consistencia (regla negocio)
```python
def test_dmg_sum_consistency():
    run = lategame_capture.process_pair(...)
    total_pct = sum(d['dmg_porcentaje'] for d in run.breakdown_dmg)
    assert 98.0 <= total_pct <= 102.0   # margen 2% por redondeos OCR

def test_team_matches_roster():
    run = lategame_capture.process_pair(...)
    for agente in run.equipo:
        assert agente in roster_names()
```

Si la consistencia falla:
- Marcar `lategame_runs.requires_review=1`.
- NO disparar recálculo tier list hasta que Daniel valide.
- Loguear en `inventory_disc_evaluations.notas` equivalente.

---

## 3. Tier list calculator — golden cases

### 3.1 Fórmula del score (RF-13)
```
score_norm = 0.45 × rate_3star
           + 0.20 × win_rate
           + 0.20 × avg_dmg_share_normalized_by_role
           + 0.15 × avg_tiempo_normalized
```

Buckets fijos (no cuartiles):
| Bucket | Score |
|--------|-------|
| S+ | ≥ 90 |
| S | 80-89 |
| A | 65-79 |
| B | 50-64 |
| C | 30-49 |
| D | 0-29 |

### 3.2 Test L2 — buckets deterministas
```python
@pytest.mark.parametrize('score,expected_tier', [
    (95.0, 'S+'),
    (90.0, 'S+'),     # exactamente en el corte
    (89.99,'S'),
    (80.0, 'S'),
    (79.99,'A'),
    (65.0, 'A'),
    (64.99,'B'),
    (50.0, 'B'),
    (49.99,'C'),
    (30.0, 'C'),
    (29.99,'D'),
    (0.0,  'D'),
])
def test_tier_buckets(score, expected_tier):
    assert assign_tier(score) == expected_tier
```

### 3.3 Test L3 — recálculo full
```python
def test_tier_list_recalc_performance():
    seed_runs(45 * 5)         # 5 runs por PJ
    t = time.perf_counter()
    snapshot = tier_list_calculator.recalculate_all()
    elapsed = (time.perf_counter() - t)
    assert elapsed < 3.0      # RNF-06: <3s para 45 PJs × 3 contenidos
    assert len(snapshot.entries) == 45 * 3
    assert all(e.tier in ('S+','S','A','B','C','D') for e in snapshot.entries)
```

### 3.4 Snapshots atómicos (no UPDATE)
```python
def test_snapshots_are_atomic():
    snap1 = tier_list_calculator.recalculate_all()
    snap2 = tier_list_calculator.recalculate_all()
    assert snap1.snapshot_id != snap2.snapshot_id
    # snap1 debe seguir siendo legible íntegro
    rows = db.execute(
        "SELECT * FROM tier_list_personal WHERE snapshot_id=?",
        [snap1.snapshot_id]
    ).fetchall()
    assert len(rows) == 45 * 3
```

### 3.5 K mínimo y K máximo
RF-13 define `K_min=3` runs antes de calcular, `K_max=20` (window).
```python
def test_k_min_threshold():
    seed_runs_for_pj('Ellen', count=2)
    snapshot = tier_list_calculator.recalculate_all()
    ellen = next(e for e in snapshot.entries if e.pj_id == ellen_id)
    assert ellen.tier is None
    assert ellen.flag == 'insufficient_data'

def test_k_max_window():
    seed_runs_for_pj('Ellen', count=50)
    snapshot = tier_list_calculator.recalculate_all()
    ellen = next(e for e in snapshot.entries if e.pj_id == ellen_id)
    # solo los últimos 20 deben pesar
    assert ellen.runs_considered == 20
```

---

## 4. Delta vs Prydwen

### 4.1 Test de delta por entrada
```python
def test_delta_vs_prydwen():
    # En Prydwen Yanagi está S; en mi cuenta con M2 + Tecno Pícido 4pc, S+
    snapshot = tier_list_calculator.recalculate_all()
    yanagi = next(e for e in snapshot.entries if e.pj_id == yanagi_id and e.contenido=='shiyu_critical')

    # Prydwen baseline tier_list_general 2026-05-XX
    prydwen_yanagi = prydwen_tier_snapshots_latest('Yanagi','shiyu_critical')

    assert yanagi.delta_vs_prydwen in ('S+ ↑ S', 'igual', 'S ↓ A', ...)
    assert yanagi.justificacion_delta is not None
    assert len(yanagi.justificacion_delta) > 30
```

### 4.2 Justificación textual autogenerada
RF-13 §4 da plantilla: `"Yanagi sube de S a S+ atribuible a M2 + Tecno Pícido 4pc, rate 3★ 94% vs típico 80%"`.

Test:
```python
def test_justificacion_template():
    yanagi = ...  # con delta positivo
    j = yanagi.justificacion_delta
    assert 'rate 3★' in j or 'rate 3-star' in j
    assert '%' in j
    # menciona alguna razón mecánica (Mindscape, set, arma, awakening)
    assert any(t in j for t in ['M2','M3','M6','set','arma','awakening','Mindscape'])
```

---

## 5. Retro-feedback bayesiano

### 5.1 Fórmula (de RF-13)
```
peso_prior   = 1 / (1 + 0.3 × runs_evidencia)
peso_evid    = 1 - peso_prior
likelihood   = min(1.5, rate_3star_observado × factor_normalizacion)
confianza_post = peso_prior × confianza_ai + peso_evid × likelihood
```

### 5.2 Caso canónico Ellen+Dialyn (RF-13 doc + RF-12 §8)
Estado inicial:
- `confianza_ai = 0.85` (lo asignó la IA en RF-12).
- 5 runs jugados con rate 3★ = 0.20 (4 de 5 fueron 2★ o menos).

Cálculo:
```
runs = 5
peso_prior = 1 / (1 + 0.3 × 5) = 1 / 2.5 = 0.40
peso_evid  = 0.60
likelihood = min(1.5, 0.20 × 1.0) = 0.20
confianza_post = 0.40 × 0.85 + 0.60 × 0.20 = 0.34 + 0.12 = 0.46
```

> RF-13 documenta el resultado como **0.50** aproximadamente (ligero ajuste por factor de normalización del rate). Cualquier valor en `[0.40, 0.55]` es aceptable.

Test:
```python
def test_ellen_dialyn_retro_feedback():
    # Setup: confianza inicial 0.85
    db.execute("UPDATE team_synergies SET confianza=0.85 "
               "WHERE pj_a_id=? AND pj_b_id=?", (ellen_id, dialyn_id))
    # 5 runs Ellen+Dialyn con 1 de 5 = 3★
    seed_runs_for_team(ellen_id, dialyn_id, runs=[
        {'estrellas': 3}, {'estrellas': 2}, {'estrellas': 2},
        {'estrellas': 1}, {'estrellas': 2}
    ])
    retro_feedback.recompute_for_pair(ellen_id, dialyn_id)

    new_conf = db.execute("SELECT confianza FROM team_synergies "
                          "WHERE pj_a_id=? AND pj_b_id=?",
                          (ellen_id, dialyn_id)).fetchone()[0]
    assert 0.40 <= new_conf <= 0.55

    # Auditoría
    adj = db.execute("SELECT * FROM team_synergy_adjustments "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert adj.runs_evidencia == 5
    assert abs(adj.confianza_pre - 0.85) < 0.01
    assert abs(adj.confianza_post - new_conf) < 0.01
    assert adj.motivo_bayesiano is not None
```

### 5.3 Likelihood capada en 1.5
Sin cap, una racha afortunada (5 runs todos 3★) podría disparar la confianza a >1.0. RF-13 cap fija = 1.5.

```python
def test_likelihood_capped():
    seed_runs_for_team(...,runs=[{'estrellas':3}]*10)
    rate_observed = 1.0
    lik = compute_likelihood(rate_observed)
    assert lik <= 1.5
```

### 5.4 Cross de umbral 0.70 → desaplicar override automáticamente
RF-13: si `confianza < 0.70` el override deja de aplicarse en RF-12 lookup automáticamente.

```python
def test_low_confidence_disables_override():
    # confianza_post = 0.46 (caso Ellen+Dialyn)
    set_confianza(ellen_id, dialyn_id, 0.46)

    # RF-12 lookup ya NO debe aplicar el override de set
    result = team_optimizer.lookup_for(ellen_id, [dialyn_id])
    assert result.override_set_applied == False
    assert result.set_objetivo != 40    # NO Puffer Electro
    assert result.razon_no_aplicado == 'confianza_below_0.70'
```

### 5.5 Override manual con `congelado=1`
```python
def test_congelado_blocks_retro_feedback():
    db.execute("UPDATE team_synergies SET congelado=1, confianza=0.85 "
               "WHERE pj_a_id=? AND pj_b_id=?", (ellen_id, dialyn_id))
    # 10 runs con rate 0
    seed_runs_for_team(...,runs=[{'estrellas':0}]*10)
    retro_feedback.recompute_for_pair(ellen_id, dialyn_id)
    new_conf = ...
    assert new_conf == 0.85  # congelado, NO se ajusta
    # auditoría debe registrar el skip
    adj = db.execute("SELECT * FROM team_synergy_adjustments ORDER BY id DESC LIMIT 1").fetchone()
    assert adj.skipped_reason == 'congelado'
```

---

## 6. Scrapers (RF-13: enemies, cycles, Prydwen tier list)

### 6.1 `scrape_enemies.py` (Hakush.in + Prydwen)
- Output esperado: ~80 enemigos iniciales con `hp_base`, `escalado_dificultad` JSON, `enemy_resistances` por elemento.
- Frecuencia: cada patch (~6 sem).

Tests:
```python
def test_scrape_enemies_smoke():
    result = scrape_enemies.run(dry_run=True)
    assert len(result.enemies) >= 70
    assert all(e.hp_base > 0 for e in result.enemies)
    # Resistencias coherentes
    for e in result.enemies:
        assert len(e.resistances) == 6   # 6 elementos
        assert all(0.0 <= r.multiplier <= 2.0 for r in e.resistances)

def test_enemies_hash_stable():
    # Ejecutar scrape 2 veces seguidas debe dar mismo output (Hakush no cambia entre minutos)
    r1 = scrape_enemies.run(dry_run=True)
    r2 = scrape_enemies.run(dry_run=True)
    assert hash_response(r1) == hash_response(r2)
```

### 6.2 `scrape_prydwen_tierlist.py`
Output: snapshot semanal con tier por (PJ, contenido). Frecuencia: domingos 03:00.

Tests:
```python
def test_prydwen_scrape_complete():
    snap = scrape_prydwen_tierlist.run(dry_run=True)
    # Cada PJ del roster debe aparecer al menos en 'general'
    pj_in_snap = {e.pj_name for e in snap.entries}
    for roster_pj in roster_names():
        assert roster_pj in pj_in_snap or roster_pj in PJ_RECIENTES_PRYDWEN_LAG

def test_prydwen_scrape_idempotent_snap():
    s1 = scrape_prydwen_tierlist.run(dry_run=True)
    s2 = scrape_prydwen_tierlist.run(dry_run=True)
    # mismas tier para mismo timestamp del scrape
    assert {(e.pj_name,e.contenido,e.tier) for e in s1.entries} == \
           {(e.pj_name,e.contenido,e.tier) for e in s2.entries}
```

### 6.3 Falla de scraper — graceful degradation
Si Prydwen está caído o cambió HTML, el scrape no debe romper la app:
- Logueo de error.
- Snapshot anterior queda vigente (lookup por `MAX(snapshot_id)`).
- Notificación al usuario via tray icon (badge "scraper failed").
- NO borrar snapshots viejos.

---

## 7. Edge cases del pipeline F11

### 7.1 Daniel termina un run pero NO presiona F11
No hay nada que hacer — no hay datos. Loguear visualmente en panel "Lategame" un recordatorio si pasaron >24h sin runs nuevos.

### 7.2 F11 disparado pero no estoy en pantalla de resumen
Detector debe identificar la pantalla; si no es la esperada:
- Mostrar toast: "Captura F11 fuera de pantalla de resumen — ignorada".
- NO insertar nada.

### 7.3 OCR del breakdown DMG falla parcialmente (ej. solo 2 de 3 PJs detectados)
- Marcar `requires_review=1`.
- Mostrar al usuario el frame + transcripción para corrección.
- Si Daniel corrige y aprueba, insertar.

### 7.4 Enemigo no está en `enemies`
Run en frente con boss recién agregado al juego. Inserción debe permitirlo (FK no requiere existencia de enemigo concreto en `lategame_runs` — el FK es a través de `shiyu_cycles.frentes` JSON). Pero el log debe alertar al patch checklist [QA-07](./QA-07_Regresion_Patches.md).

### 7.5 Run con composición no canónica (3 supports, 0 DPS)
Permitido — Daniel puede experimentar. Pero el `avg_dmg_share_normalized_by_role` puede dividirse por 0 si el rol esperado es DPS. Manejar:
```python
def normalize_dmg_share(role, dmg):
    expected = EXPECTED_BY_ROLE[role]
    if expected == 0:
        return None  # marcar 'role_mismatch' en el snapshot
    return dmg / expected
```

---

## 8. Pruebas L4 reales

Daniel valida el flujo completo:

| Caso L4 | Acción | Resultado esperado |
|---------|--------|---------------------|
| Run Shiyu 3★ | Termina run → F11 | Toast confirmación + insert visible en panel "Lategame" |
| Run DA con boss desconocido | Termina run → F11 | Insert OK + alerta "enemigo X no en catálogo" |
| 3 runs nuevos completados | espera | Recálculo tier list dispara solo + notificación |
| Domingo 03:00 | espera scheduled job | Recálculo + snapshot Prydwen |
| Composición Ellen+Dialyn × 5 runs con rate 3★ <0.30 | jugar 5 runs y revisar panel | `team_synergies.confianza` baja a ~0.46; override deja de aplicarse en próxima recomendación |
| Override manual `congelado=1` en panel | toggle + 5 runs malos | confianza queda en 0.85 |

Daniel registra en `Documentacion/QA/evidencia/RF-13/<fecha>_<caso>.md`.

---

## 9. Métricas de validación end-to-end

Tras 4 semanas de uso real (post-implementación de RF-13):

| Métrica | Esperado | Investigar si |
|---------|----------|---------------|
| Runs cargados/semana | ≥ 5 | < 3 (Daniel no está usando F11) |
| % runs con `requires_review=1` | < 15% | > 25% (OCR breakdown DMG necesita tuning) |
| PJs con tier asignado | ≥ 30/45 | < 20 (insufficient_data masivo — bajar K_min temporalmente) |
| Sinergias con `confianza < 0.70` por bayesiano | 5-15 (sano: hay corrección) | 0 (no se está corrigiendo) o >30 (la IA estaba muy mal) |
| Tier list converge tras 4 semanas | sí (cambios <5 PJs por snapshot) | no (oscila — ventana K muy chica o calibración mala) |

---

## 10. Cobertura mínima antes de cerrar Fase 4

- [ ] Pipeline F11 captura → OCR → insert con golden set 10+ casos.
- [ ] Buckets fijos S+/S/A/B/C/D pasan unit test (§3.2).
- [ ] Recálculo tier list <3s sobre fixture 45×5 runs.
- [ ] Caso canónico Ellen+Dialyn bayesiano pasa (§5.2).
- [ ] Override `congelado=1` respeta el bloqueo (§5.5).
- [ ] Confianza < 0.70 desactiva override en RF-12 (§5.4).
- [ ] Scrapers Hakush.in y Prydwen funcionan + graceful degradation cuando fallan.
- [ ] L4 Daniel: 20 runs reales cargados, 1 retro-feedback cycle completo (≥3 runs por composición).
- [ ] Tier list snapshot generado y comparable contra Prydwen.

---

*El bayesiano es elegante pero solo es útil con datos. Los primeros 50 runs son los más valiosos — calibran el modelo. Documentar ahí cualquier sorpresa.*

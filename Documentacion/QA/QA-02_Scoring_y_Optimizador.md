# QA-02 — Scoring engine y Optimizadores (RF-06 + RF-14)

**Capa:** L2 (unit) + L3 (integration) + L5 (cruzada)
**RFs cubiertos:** RF-06 (optimizador build de discos), RF-14 (optimizador W-Engines), engine compartido `app/core/scoring.py`.
**Cuándo consultar:** al implementar cualquier función de scoring, optimizador, recommender o el toggle "Optimizar también el arma".

> **Principio:** la fórmula de scoring es **determinista, pura y reproducible**. Mismo disco + mismo PJ + mismo arquetipo → mismo score, byte por byte, hoy y dentro de 6 meses. Cualquier indeterminismo (orden de iteración sobre dict, random no seeded, lectura de wall-clock) es un bug.

---

## 1. Fórmula canónica del scoring

Tomada de README §3.1 RF-06 + RF-Logic_Captura_Discos §11. Engine único en `app/core/scoring.py`, invocado por:
- evaluador de capturas de RF-04
- optimizador de RF-06
- weapon_scoring de RF-14 (extiende con uptime contextual)

```
score_disco =
    Σ (positivos_i × valor_i × (1 + rolls_i × 0.25))
  - Σ (perjudiciales_j × valor_j × (1 + rolls_j × 0.5))
  + bonus_main_arquetipo
  + bonus_nivel
```

Donde:
- `positivos` y `perjudiciales` son substats con peso del arquetipo del PJ (lookup en `agent_substat_preferences` o fallback a `disc_archetypes.pesos_json`).
- `rolls_i` ∈ {0,1,2,3,4} representa upgrades extra del substat.
- `bonus_main_arquetipo` recompensa main stat alineado con el arquetipo (ej: ATK% en disco 4 para ATK_DPS).
- `bonus_nivel` escala lineal con `nivel/15`.

---

## 2. Golden cases para `scoring.py`

Cada caso es un **unit test L2** ejecutable vía `pytest`. Vivirá en `app/tests/unit/test_scoring.py`.

### 2.1 Caso A — Disco perfecto para arquetipo ATK_DPS
```python
disco_A = {
    'set_id': 17,                  # Polar Metal (ATK_DPS primario)
    'slot': 4,
    'main_stat': 'ATK%',
    'main_valor': 30.0,
    'sub1': 'crit_rate',  'val1': 9.6,  'rolls1': 4,
    'sub2': 'crit_dmg',   'val2': 19.2, 'rolls2': 4,
    'sub3': 'atk_pct',    'val3': 9.6,  'rolls3': 4,
    'sub4': 'pen_pct',    'val4': 4.8,  'rolls4': 1,
    'nivel': 15
}
agente = 'Ellen'  # ATK_DPS, ice element

# Esperado
assert scoring(disco_A, agente).score >= 0.95
assert scoring(disco_A, agente).recomendacion == 'Equipar'
assert scoring(disco_A, agente).arquetipo == 'ATK_DPS'
```

### 2.2 Caso B — Disco neutro (rolls bajos en stats relevantes)
```python
disco_B = {
    'set_id': 17, 'slot': 4, 'main_stat': 'ATK%', 'main_valor': 30.0,
    'sub1': 'crit_rate', 'val1': 2.4, 'rolls1': 0,
    'sub2': 'hp_flat',   'val2': 112, 'rolls2': 0,
    'sub3': 'def_flat',  'val3': 15,  'rolls3': 0,
    'sub4': 'er',        'val4': 0.05,'rolls4': 0,
    'nivel': 15
}

assert 0.40 <= scoring(disco_B, 'Ellen').score < 0.75
assert scoring(disco_B, 'Ellen').recomendacion in ('Reserva','Mejorar')
```

### 2.3 Caso C — Disco basura (substats todos perjudiciales)
```python
disco_C = {
    'set_id': 17, 'slot': 4, 'main_stat': 'HP%', 'main_valor': 10.0,
    'sub1': 'def_flat', 'val1': 15, 'rolls1': 0,
    'sub2': 'def_pct',  'val2': 3.2,'rolls2': 0,
    'sub3': 'hp_flat',  'val3': 112,'rolls3': 0,
    'sub4': 'hp_pct',   'val4': 3,  'rolls4': 0,
    'nivel': 0
}

assert scoring(disco_C, 'Ellen').score < 0.30
assert scoring(disco_C, 'Ellen').recomendacion == 'Descartar'
```

### 2.4 Caso D — Mismo disco, distinto PJ → distinto score
```python
disco_D = disco_A.copy()
ellen_score   = scoring(disco_D, 'Ellen').score      # ATK_DPS Hielo
nicole_score  = scoring(disco_D, 'Nicole').score     # SUPPORT_ER Éter

assert ellen_score > nicole_score                    # ATK% en slot 4 escala distinto
assert abs(ellen_score - nicole_score) > 0.20        # delta significativo
```

### 2.5 Caso E — Determinismo
```python
# Mismo input 1000 veces → mismo output exacto
results = [scoring(disco_A, 'Ellen').score for _ in range(1000)]
assert len(set(results)) == 1                        # un único valor
```

### 2.6 Caso F — Upgrade sub_unlocked (RF-05 propaga a scoring)
```python
disco_F_pre  = {...,'sub4': None, 'val4': None, 'rolls4': 0, 'nivel': 9}
disco_F_post = {...,'sub4': 'crit_rate','val4': 2.4,'rolls4': 0,'nivel':12}

s_pre  = scoring(disco_F_pre, 'Ellen').score
s_post = scoring(disco_F_post, 'Ellen').score
assert s_post > s_pre                                # nuevo substat útil sube score
```

### 2.7 Caso G — Burnice AM > 300 cap (regla negocio)
```python
disco_G = {... 'sub1': 'anomaly_mastery', 'val1': 35, 'rolls1': 4, ...}
# Burnice ya está en AM 398; el threshold cap es 300 (RNF-02 §6.2 imprecisión documentada)
score_burnice = scoring(disco_G, 'Burnice')

assert score_burnice.flags['anomaly_mastery_wasted'] == True
# El score puede igualmente ser alto, pero el flag debe existir para que la UI lo señale
```

---

## 3. Golden cases para `optimizer.py` (RF-06)

Vivirán en `app/tests/integration/test_optimizer.py` con DB fixture cargada desde `app/tests/fixtures/danibod_baseline.sql`.

### 3.1 Top-3 builds determinismo
```python
builds = optimizer.top_builds_for(agent='Ellen', k=3)
assert len(builds) == 3
assert builds[0].score >= builds[1].score >= builds[2].score

# Ejecutar 5 veces, debe retornar exactamente lo mismo
runs = [optimizer.top_builds_for('Ellen', 3) for _ in range(5)]
hashes = {hash(tuple(b.id for b in r)) for r in runs}
assert len(hashes) == 1
```

### 3.2 Set bonus 4pc preferido sobre 2+2+2 cuando empata
```python
# Disponibles: 4 discos Polar Metal con score similares + 2 Puffer Electro + 2 Soul Rock
# El optimizador debe elegir 4pc Polar (mayor sinergia con set bonus) salvo que el delta sea grande
build = optimizer.top_builds_for('Ellen', k=1)[0]
assert build.set_bonus_aplicado in ('4pc Polar Metal','3+3','2+2+2')
assert build.set_bonus_4pc_id == 17 or build.score_delta_with_4pc < 0.05
```

### 3.3 Swap entre PJs detectado
```python
# Caso: el mejor disco para Ellen está equipado en Lycaon
swap = optimizer.swap_recommendations(agent_destino='Ellen')
assert any(s.tipo == 'swap_entre_pj' for s in swap)
for s in swap:
    if s.tipo == 'swap_entre_pj':
        assert s.delta_destino > 0
        assert s.delta_origen <= 0    # quien pierde, pierde
        assert s.neto > 0             # solo recomendar si neto positivo
```

### 3.4 Performance budget (L3)
```python
import time
start = time.perf_counter()
builds = optimizer.top_builds_for('Ellen', k=3)
elapsed_ms = (time.perf_counter() - start) * 1000
assert elapsed_ms < 500            # RNF-06 §RF-06 budget con 332 discos

# Proyección 1500 discos
expanded = optimizer.top_builds_for('Ellen', k=3, inventory_size=1500)
elapsed_ms = ...
assert elapsed_ms < 1000
```

### 3.5 Reproducibilidad cross-arquetipo
| PJ | Arquetipo esperado | Set 4pc esperado en top build (mid 2026) |
|----|--------------------|------------------------------------------|
| Ellen | ATK_DPS | Polar Metal (id 17) |
| Burnice | ANOMALY | Jazz Caótico (id 8) |
| Lycaon | STUN | Aria brillante o Punk Hormonal |
| Astra Yao | SUPPORT_ER | Notas encadenadas |
| Manato | HP_DISRUPT | (set HP%) |
| Zhao | DEFENSE | Punk Primitivo o Jazz Oscilante |

Si la realidad post-Prydwen scrape divergiera, no es bug — actualizar la tabla esperada y dejar evidencia del cambio en `audit/`.

---

## 4. Golden cases para `weapon_scoring.py` y `weapon_optimizer.py` (RF-14)

### 4.1 Caso "la roca" — uptime contextual
Núcleo Fosilizado Precioso (Stunner S-rank, +Impact% mientras HP enemigo > 50%):

```python
# DA: bosses con HP largo, uptime ~95%
score_da   = weapon_scoring(weapon='Núcleo Fosilizado Precioso',
                            pj='Lycaon', contenido='da')
# Hollow Zero: enemigos rápidos, uptime ~30%
score_hz   = weapon_scoring(weapon='Núcleo Fosilizado Precioso',
                            pj='Lycaon', contenido='hollow_zero')
# General: ~70% promedio
score_gen  = weapon_scoring(weapon='Núcleo Fosilizado Precioso',
                            pj='Lycaon', contenido='general')

assert score_da > score_gen > score_hz
# Tier expected: S+ DA, B HZ
assert tier_for(score_da) == 'S+'
assert tier_for(score_hz) == 'B'
```

### 4.2 Pasivas `trigger_tipo='always'` — invariantes a contenido
```python
# Coctelera incandescente (Burnice, S-rank, AP boost siempre activo)
scores = [weapon_scoring(weapon='Coctelera incandescente',
                          pj='Burnice', contenido=c)
          for c in ['shiyu_critical','da','hollow_zero','general']]
# Todos los scores casi iguales (delta < 5%)
assert max(scores) - min(scores) < max(scores) * 0.05
```

### 4.3 Refinamiento R1↔R5 lineal
```python
# Misma weapon, misma PJ, mismo contenido, distinto refinamiento
s_r1 = weapon_scoring(weapon='X', pj='Y', refinamiento=1, contenido='shiyu_critical')
s_r5 = weapon_scoring(weapon='X', pj='Y', refinamiento=5, contenido='shiyu_critical')
s_r3 = weapon_scoring(weapon='X', pj='Y', refinamiento=3, contenido='shiyu_critical')

# Interpolación lineal: s_r3 ≈ (s_r1 + s_r5) / 2 con error < 5%
assert abs(s_r3 - (s_r1 + s_r5)/2) / s_r3 < 0.05
```

### 4.4 Build full coordinado RF-06 + RF-14
```python
# Top 3 armas × top 3 builds c/u → top 3 combinaciones por score combinado
combos = build_full_optimizer(pj='Ellen', contenido='shiyu_critical', k=3)
assert len(combos) == 3
assert all(c.score_combinado > 0 for c in combos)
# Latencia
elapsed_ms < 1500
```

### 4.5 Performance W-Engine ranking
```python
# 49 armas para 1 PJ en 1 contenido < 100 ms
ranking = weapon_optimizer.rank(pj='Ellen', contenido='shiyu_critical')
assert len(ranking) == 49
assert elapsed_ms < 100

# Recálculo full (45 PJs × 49 armas × 4 contenidos = 8820 evaluaciones) < 8 s
recalc_all_evaluations() ; elapsed_s < 8
```

---

## 5. Validación cruzada con Prydwen (L5)

Los rankings calculados por el sistema deben **converger razonablemente** con los de Prydwen (no ser idénticos — el sistema personaliza por inventario y contenido).

### 5.1 Métrica de divergencia aceptable
Para cada PJ del roster:
```
divergencia = |rank_local(weapon) - rank_prydwen(weapon)| / 49
```

| Métrica | Aceptable | Investigar |
|---------|-----------|------------|
| Top-1 weapon coincide con Prydwen | ≥ 70% PJs | < 50% (revisar pesos `pj_weapon_synergy`) |
| Top-3 contiene la #1 de Prydwen | ≥ 90% PJs | < 80% |
| Divergencia promedio | < 0.15 | > 0.25 |

### 5.2 Casos donde la divergencia es **esperada** (no bug)
- "La roca" en Hollow Zero (Prydwen general dice S, local dice B). Documentar como **decisión, no error**.
- Awakenings parciales (DaniBOD-específico) que cambian el peso óptimo de Energy Regen.
- M0 vs Mindscape alto: Manato M6 tiene comportamiento distinto a Manato M0 que asume Prydwen.

### 5.3 Test L5 reproducible
```python
# app/scripts/qa/cruzar_prydwen.py
discrepancias = []
for pj in roster:
    local = weapon_optimizer.rank(pj.id, contenido='general')[:3]
    prydwen = prydwen_weapon_snapshots_latest_for(pj.id)
    if local[0].weapon_id != prydwen.top_weapon_id:
        discrepancias.append((pj.nombre, local[0], prydwen.top_weapon_id))

print(f"{len(discrepancias)} divergencias top-1")
# Si > 30% → investigar pesos
```

---

## 6. Edge cases que históricamente rompen scoring engines

### 6.1 Substats con valor 0
- `val=0, rolls=0`: tratar como "substat presente con valor base, pero sin upgrade". Score contribuye solo el bonus base.
- `val=None, rolls=0`: substat NO desbloqueado (slot vacío). NO debe contar.
- `val=X, rolls=4` con stat irrelevante: penalización debe escalar con rolls (multiplicador 0.5 vs 0.25 para positivos).

### 6.2 Disco con set desconocido
Si llega un disco con `set_id` que no está en `disc_sets` (ej: nuevo set post-patch sin onboarding), el scoring debe:
1. Calcular el score como si fuera "set neutro" (sin bonus de set bonus pass).
2. Marcar `flags['set_unknown']=True`.
3. Loguear en `inventory_disc_evaluations.notas`: `"set_id=X no catalogado, requiere Onboarding_Nuevos_Assets.md"`.

NO debe lanzar excepción ni retornar score=0.

### 6.3 PJ sin arquetipo en `agent_substat_preferences`
Si `agent_substat_preferences` está vacía para el PJ (estado actual: 0 filas), caer al arquetipo primario derivado del rol. Test:
```python
score = scoring(disco_A, 'PJ_sin_preferences')
assert score.flags['fallback_to_archetype'] == True
assert score.arquetipo == arquetipo_por_rol(pj.rol)
```

### 6.4 Awakening inactivo
Burnice con ER 1.56 (< 1.8) tiene su despertar `Boiling Point Party` inactivo. El scoring del optimizador para Burnice debe:
- Pesar más el ER (para que el optimizador sugiera builds que cierren el gap).
- NO sumar el bono del awakening al score base del PJ.
- Marcar flag `flags['awakening_locked']=True` con razón humana.

---

## 7. Tests de regresión perpetuos

Cada bug encontrado en producción genera un test L2/L3 que vive para siempre en `app/tests/regressions/<fecha>_<descripcion>.py`. Plantilla:

```python
# app/tests/regressions/2026-XX-XX_burnice_am_cap.py
"""
Bug histórico: el scoring no marcaba flag wasted cuando AM>300 en Burnice.
Detectado: 2026-XX-XX
Fix commit: <sha>
"""
def test_burnice_am_cap_flag():
    disco = {... 'sub1':'anomaly_mastery','val1':35,'rolls1':4 ...}
    result = scoring(disco, 'Burnice')
    assert result.flags['anomaly_mastery_wasted'] == True
```

---

## 8. Pruebas reales en juego (L4)

Daniel valida en juego con la app corriendo:

| Caso | Acción | Resultado esperado |
|------|--------|---------------------|
| Equipa disco S-rank en Ellen | toast aparece <500 ms | ✅ Verde "Equipar" + score visible |
| Equipa disco basura (HP en disco 4 ATK_DPS) | sin toast | sin alerta, queda en histórico marcado Descartar |
| Sube disco de nivel 0→3 | toast con delta | "Mejora" si delta>0 |
| Mismo disco evaluado en sesiones distintas | mismo score | sin variación entre sesiones |

Daniel registra cada divergencia en `Documentacion/QA/evidencia/RF-06/<fecha>_<caso>.md` con:
- Screenshot del juego.
- Output del toast.
- Log de la app (`inventory_disc_evaluations`).
- Su criterio personal (¿el sistema acertó? ¿por qué creé que no?).

---

## 9. Cobertura mínima antes de cerrar Fase 2

Antes de marcar Fase 2 como **cerrada en producción**:

- [ ] 30+ unit tests verdes en `test_scoring.py` cubriendo §2.
- [ ] 15+ integration tests verdes en `test_optimizer.py` cubriendo §3.
- [ ] Performance: optimizador <500 ms p99 sobre fixture de 332 discos (medido con `pytest-benchmark`).
- [ ] L4 Daniel: 50 toasts disparados sin error de scoring percibido.
- [ ] L5 cruzada: <15% divergencia promedio vs Prydwen para top-3 builds en los 5 PJs principales (Ellen, Miyabi, Burnice, Yanagi, Lycaon).

Antes de marcar Fase 5 (RF-14) como **cerrada**:
- [ ] Caso "la roca" pasa con tier S+ DA / B HZ.
- [ ] 49 armas × 1 PJ × 1 contenido < 100 ms p99.
- [ ] Build full < 1.5 s p99.
- [ ] Snapshot Prydwen weapons cargado y comparativo poblado.

---

*Estos golden cases viven en código, no en doc. Este `.md` es la especificación; los tests reales son la verdad ejecutable.*

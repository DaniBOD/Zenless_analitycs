# RF-14 — Optimizador de Armas (W-Engines) con Scoring Contextual

**Estado:** 🟦 Diseño cerrado (abril 2026)
**Última actualización:** 2026-04-25
**Owner:** DaniBOD
**Documentos relacionados:**
- [`RF-Logic_Optimizador_Build.md`](../RF_Optimizador/RF-Logic_Optimizador_Build.md) (RF-06 — build de discos por PJ)
- [`RF-Logic_Optimizador_Equipos.md`](../RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md) (RF-12 — team-aware)
- [`RF-Logic_Lategame_Validation.md`](../RF_Lategame_Validation/RF-Logic_Lategame_Validation.md) (RF-13 — validación lategame + retro-feedback)
- `../../README.md` §3.1 RF-14, §10

---

## §1 — Origen y motivación

El sistema cubre la optimización de discos (RF-06), team-aware (RF-12) y validación empírica (RF-13), pero **falta el eje "qué arma equipar"**. Las W-Engines son la otra mitad del equipamiento de un PJ y su impacto es comparable al del set de discos: una buena arma puede sumar 30-50% de DPS efectivo respecto a una mediocre.

### 1.1 — Por qué el modelo de Prydwen no alcanza

Prydwen mantiene tier lists de armas por PJ, pero asumen:
- Refinamiento R5 (en mi cuenta, casi todas R1).
- Contenido genérico (no diferencia DA vs Shiyu vs Hollow Zero).
- Composición canónica (no considera mi roster real).

**El caso "la roca" (Núcleo Fosilizado Precioso / Precious Fossilized Core, S-rank Stunner):**
- Pasiva: *"Mientras el HP del enemigo está sobre el 50%, +X% Impact"* (escala con refinamiento).
- En **Shiyu Defense Critical**: TTL típico de un boss son 60-90 segundos, el HP cae rápido bajo 50% → uptime de la pasiva ~50-60% → bonus moderado.
- En **Deadly Assault**: el contenido es una *carrera de score* (cuánto daño podés acumular en 90 s), normalmente NO matás al boss → HP del enemigo se mantiene >50% durante todo el run → uptime 90-100% → **bonus máximo, esta arma es S+ aquí**.
- Prydwen la pone en "S general" sin distinguir; en mi cuenta debería verse como **"S+ en DA, A en Shiyu, B en HZ"**.

Generalizando: **toda arma con pasiva condicional tiene un perfil de uptime que depende del contenido**. Sin modelar eso, el ranking pierde su valor principal.

### 1.2 — Patrón de armas por tipo de pasiva

Del schema actual (`weapons.pasiva_tipo`):

| `pasiva_tipo` | Naturaleza | Sensibilidad al contexto |
|---------------|-----------|--------------------------|
| `dmg_boost` | +X% DMG bajo condición | **Alta** — depende de uptime de la condición |
| `anomaly_proficiency` | +X AP / Mastery | Baja — efecto pasivo siempre |
| `energy_regen` | +X% ER | Media — depende del rol del PJ (off-field más beneficiado) |
| `crit` | +X% CR / +X% CD bajo condición | Media-Alta |
| `pen_ratio` | +X% Pen Ratio | Baja — efecto pasivo |
| `atk_boost` | +X ATK bajo condición | Media — uptime variable |
| `mixed` | Combinaciones | Variable, requiere inspección |

RF-14 trata cada tipo según su sensibilidad: las de baja sensibilidad rankean igual en todo contenido (ahorro de cómputo), las de alta requieren scoring contextual completo.

---

## §2 — Alcance v1

### 2.1 — Tres entregables principales

```
┌─────────────────────────────────────────────────────────────────┐
│  1. RANKING IDEAL — top-N del catálogo completo (49 W-Engines)  │
│     "Si pudiera tener cualquier arma, ¿cuál sería óptima para    │
│      este PJ en este contenido?"                                 │
│     Sirve como target para banners de armas y farmeo.            │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. RANKING DISPONIBLE — top-N de inventory_weapons              │
│     "De lo que tengo equipable hoy (40 + 10 sueltas), ¿qué es   │
│      lo mejor para este PJ?"                                     │
│     Considera refinamiento real, no R5 hipotético.               │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. BUILD FULL (RF-06 + RF-14) — arma óptima + 6 discos juntos  │
│     "Para Lycaon en DA, ¿cuál es la combinación ARMA + DISCOS   │
│      que maximiza el score esperado?"                            │
│     Resuelve interacciones (ej. arma con +ATK% prefiere disco    │
│     con CRIT% para balancear; arma con +CRIT prefiere ATK%).    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 — Lo que NO entra en v1

- **Simulador de banner** (¿vale la pena pull?) — diferido a v2 si hay demanda.
- **Comparativo R1 vs R5** automático — datos de escalado por refinamiento se cargan, pero el simulador "qué pasaría si subo a R3" queda como query manual en v1.
- **Modelado de armas que aún no salieron** (próximas versiones del juego) — solo armas en el catálogo actual.
- **W-Engines de Bangboo** — fuera de scope; los Bangboo tienen su propio sistema, futuro RF.

---

## §3 — Modelo de datos

Migración: `2026-04-XX_05_weapon_optimizer.sql` (3 tablas nuevas + 1 tabla `weapons` extendida + índices).

### 3.1 — Pasivas estructuradas

```sql
-- Modelado formal de pasivas para scoring automático
CREATE TABLE weapon_passives_structured (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id INTEGER NOT NULL UNIQUE REFERENCES weapons(id),
    -- Trigger: cuándo se activa la pasiva
    trigger_tipo TEXT NOT NULL CHECK(trigger_tipo IN (
        'always',                  -- siempre activa
        'on_skill_use',            -- al usar skill
        'on_basic_attack',         -- al hacer basic
        'on_dodge_counter',        -- al esquivar / counter
        'on_chain_attack',         -- al hacer chain
        'on_ultimate',             -- al usar ultimate
        'on_anomaly_trigger',      -- al activar anomalía
        'on_stun',                 -- al stunear enemigo
        'on_off_field',            -- mientras off-field
        'enemy_hp_above',          -- HP enemigo > umbral
        'enemy_hp_below',          -- HP enemigo < umbral
        'team_has_faction',        -- equipo tiene PJ de facción X
        'team_has_element',        -- equipo tiene PJ de elemento X
        'er_above',                -- ER del PJ > umbral
        'energy_full'              -- energía al máximo
    )),
    -- Parámetros del trigger (JSON flexible)
    -- ej: {"hp_threshold": 50, "stack_max": 3, "duration_s": 12}
    trigger_params TEXT,
    -- Modifiers: qué stat afecta y cuánto
    modifier_stat TEXT NOT NULL,            -- 'atk_pct' | 'crit_rate' | 'crit_dmg' | 'impact' | 'anomaly_mastery' | 'pen_ratio' | 'er' | 'dmg_pct_element_X' | etc.
    modifier_value_r1 REAL NOT NULL,        -- valor a refinamiento R1
    modifier_value_r5 REAL NOT NULL,        -- valor a R5 (interp lineal en medias)
    modifier_stack_max INTEGER DEFAULT 1,   -- stacks máximos
    -- Uptime base (sin contexto): estimación pesimista del % de tiempo que la pasiva está activa en condiciones genéricas
    uptime_base REAL DEFAULT 1.0 CHECK(uptime_base BETWEEN 0 AND 1),
    -- Texto descriptivo para fallback / UI
    descripcion_breve TEXT,
    -- Fuente del modelado
    fuente TEXT NOT NULL DEFAULT 'manual',
    fecha_modelado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

CREATE INDEX idx_passives_weapon ON weapon_passives_structured(weapon_id);
CREATE INDEX idx_passives_trigger ON weapon_passives_structured(trigger_tipo);
```

**Algunas pasivas requieren múltiples filas** (ej. "+10% ATK siempre y +20% CRIT al usar ultimate" = 2 filas). El `weapon_id` no es UNIQUE estrictamente; se relaja a `UNIQUE(weapon_id, modifier_stat, trigger_tipo)`:

```sql
-- Override del UNIQUE para soportar pasivas multi-efecto
DROP INDEX IF EXISTS idx_passives_weapon_unique;
CREATE UNIQUE INDEX idx_passives_weapon_effect
    ON weapon_passives_structured(weapon_id, modifier_stat, trigger_tipo);
```

### 3.2 — Perfiles de contenido (uptime contextual)

```sql
-- Caracteriza cada tipo de contenido para calcular uptime real
CREATE TABLE content_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido TEXT NOT NULL UNIQUE,         -- 'shiyu_critical' | 'da' | 'hollow_zero' | 'general'
    nombre_display TEXT NOT NULL,
    -- Características que afectan uptimes de pasivas
    ttl_boss_promedio_s REAL,               -- tiempo a 0 HP en segundos
    hp_boss_uptime_above_50pct REAL,        -- % del run que el boss tiene HP > 50%
    hp_boss_uptime_above_30pct REAL,
    chain_attacks_por_min REAL,
    skills_por_min REAL,
    ultimates_por_min REAL,
    anomalies_por_min REAL,
    stuns_por_min REAL,
    promedio_pjs_off_field REAL,            -- típicamente 2 (los no activos)
    fuente TEXT NOT NULL,
    fecha_calibrado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

-- Seed inicial (calibrado con runs típicos de DaniBOD + datos de Prydwen)
INSERT INTO content_profiles (contenido, nombre_display, ttl_boss_promedio_s,
    hp_boss_uptime_above_50pct, hp_boss_uptime_above_30pct,
    chain_attacks_por_min, skills_por_min, ultimates_por_min,
    anomalies_por_min, stuns_por_min, promedio_pjs_off_field, fuente)
VALUES
('shiyu_critical', 'Shiyu Defense Critical', 75.0, 0.55, 0.75,
    3.0, 12.0, 1.5, 4.0, 2.0, 2.0, 'calibracion_inicial'),
('da', 'Deadly Assault', 90.0, 0.95, 0.99,
    2.5, 14.0, 2.0, 5.0, 2.5, 2.0, 'calibracion_inicial'),
('hollow_zero', 'Hollow Zero', 25.0, 0.30, 0.55,
    1.8, 10.0, 1.2, 3.0, 1.5, 2.0, 'calibracion_inicial'),
('general', 'Contenido General', 60.0, 0.50, 0.70,
    2.5, 11.0, 1.5, 3.5, 2.0, 2.0, 'calibracion_inicial');
```

Los perfiles son **recalibrables** desde RF-13: los runs reales tienen tiempo + DMG share + estrellas, lo que permite refinar los promedios. v1 arranca con seed manual.

### 3.3 — Evaluaciones de armas (cache + histórico)

```sql
CREATE TABLE weapon_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id INTEGER NOT NULL REFERENCES agents(id),
    weapon_id INTEGER NOT NULL REFERENCES weapons(id),
    refinamiento INTEGER NOT NULL CHECK(refinamiento BETWEEN 1 AND 5),
    nivel INTEGER NOT NULL DEFAULT 60,
    contenido TEXT NOT NULL REFERENCES content_profiles(contenido),
    -- Score final (0-100)
    score_normalizado REAL NOT NULL,
    -- Desglose para auditoría / explicación al usuario
    score_atk_base REAL,
    score_stat_secundario REAL,
    score_pasiva_estructurada REAL,         -- suma de pasivas con uptime contextual
    score_pasiva_textual REAL,              -- bonus subjetivo manual (fallback)
    score_synergy_pj REAL,                  -- bonus por compat con habilidades core del PJ
    -- Comparación con Prydwen
    prydwen_tier_referencia TEXT,
    delta_vs_prydwen TEXT,
    -- Origen del cálculo
    snapshot_id TEXT NOT NULL,              -- agrupa todos los cálculos de la misma corrida
    fecha_calculado DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pj_id, weapon_id, refinamiento, contenido, snapshot_id)
);

CREATE INDEX idx_weval_pj_contenido ON weapon_evaluations(pj_id, contenido, snapshot_id);
CREATE INDEX idx_weval_score ON weapon_evaluations(pj_id, contenido, score_normalizado DESC);
```

### 3.4 — Snapshots de Prydwen para armas

Análogo a `prydwen_tier_snapshots` (RF-13) pero para recomendaciones de armas por PJ.

```sql
CREATE TABLE prydwen_weapon_recommendations_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    pj_id INTEGER NOT NULL REFERENCES agents(id),
    -- JSON: [{"rank":1,"weapon_nombre":"Hailstorm Shrine","tier":"S+","notas":"BiS"}, ...]
    recomendaciones TEXT NOT NULL,
    fuente_url TEXT NOT NULL,
    parser_version TEXT,
    UNIQUE(fecha, pj_id)
);

CREATE INDEX idx_prydwen_weapons_fecha ON prydwen_weapon_recommendations_snapshots(fecha DESC);
```

### 3.5 — Extensión de `weapons`

```sql
ALTER TABLE weapons ADD COLUMN pasiva_modelada INTEGER NOT NULL DEFAULT 0
    CHECK(pasiva_modelada IN (0, 1, 2));
-- 0 = sin modelar (solo texto)
-- 1 = modelada parcialmente (algunos efectos cubiertos)
-- 2 = modelada completamente

ALTER TABLE weapons ADD COLUMN sensibilidad_contexto TEXT
    CHECK(sensibilidad_contexto IN ('baja', 'media', 'alta'));
-- Determina si el ranking varía mucho por contenido
```

---

## §4 — Algoritmo de scoring

### 4.1 — Fórmula general

Para un par `(pj, weapon, refinamiento, contenido)`:

```python
def score_weapon(pj, weapon, refinamiento, contenido, discos_actuales=None):
    profile = content_profiles[contenido]

    # Componente 1: ATK base + stat secundario (lineal)
    score_atk = normalize(weapon.atk_base, max=900) * 25  # peso 25 pts
    score_stat2 = score_stat_secundario(weapon.stat_secundario,
                                         weapon.stat_secundario_valor, pj.rol) * 15  # peso 15

    # Componente 2: pasivas estructuradas con uptime contextual
    score_pasivas = 0
    for passive in weapon_passives_structured.where(weapon_id=weapon.id):
        valor = lerp(passive.modifier_value_r1, passive.modifier_value_r5,
                     (refinamiento - 1) / 4)
        uptime = calc_uptime(passive.trigger_tipo, passive.trigger_params,
                             profile, pj)
        impact = stat_impact_for_pj(passive.modifier_stat, valor, pj)
        score_pasivas += impact * uptime
    score_pasivas = clip(score_pasivas, 0, 40)  # peso máximo 40

    # Componente 3: pasiva textual fallback (cuando no está modelada)
    score_textual = 0
    if weapon.pasiva_modelada in (0, 1):
        score_textual = manual_bonus.get((pj.id, weapon.id, contenido), 0)
        # Daniel puede setear overrides manuales en una tabla aparte
    score_textual = clip(score_textual, 0, 10)

    # Componente 4: sinergia con habilidades core del PJ
    score_synergy = synergy_lookup(pj.id, weapon.pasiva_tipo,
                                    weapon.pasiva_descripcion) * 10  # peso 10

    score_total = score_atk + score_stat2 + score_pasivas + score_textual + score_synergy
    return clip(score_total, 0, 100)
```

### 4.2 — Cálculo de uptime contextual

```python
def calc_uptime(trigger_tipo, trigger_params, profile, pj):
    if trigger_tipo == 'always':
        return 1.0

    if trigger_tipo == 'enemy_hp_above':
        threshold = trigger_params['hp_threshold']  # ej. 50
        if threshold == 50:
            return profile.hp_boss_uptime_above_50pct
        elif threshold == 30:
            return profile.hp_boss_uptime_above_30pct
        else:
            # interpolación lineal entre puntos conocidos
            return interpolate_hp_uptime(threshold, profile)

    if trigger_tipo == 'on_chain_attack':
        # uptime ≈ chain_attacks_por_min × duración / 60
        duration = trigger_params.get('duration_s', 12)
        return min(1.0, profile.chain_attacks_por_min * duration / 60)

    if trigger_tipo == 'on_skill_use':
        duration = trigger_params.get('duration_s', 8)
        return min(1.0, profile.skills_por_min * duration / 60)

    if trigger_tipo == 'on_off_field':
        # solo aplica si el PJ es off-field en la composición típica
        return 0.7 if pj.rol in ('Anomalía', 'Soporte') else 0.3

    if trigger_tipo == 'team_has_element':
        # uptime depende de si existe un compañero del elemento requerido
        # En v1 sin team context: uptime = 0.5 (asume probabilidad base)
        # Con team context (RF-12): uptime = 1.0 si match, 0 si no
        return 0.5  # placeholder, sobreescrito por integración con RF-12

    # ... resto de triggers

    return 1.0  # default conservador
```

### 4.3 — `stat_impact_for_pj` — traducir modifier a impacto de DPS

Tabla de pesos por rol (similar a arquetipos de RF-06):

```python
STAT_IMPACT_PER_ROL = {
    'Ataque':       {'atk_pct': 1.0, 'crit_rate': 1.5, 'crit_dmg': 1.5, 'impact': 0.2,  'anomaly_mastery': 0.3, 'er': 0.4, ...},
    'Anomalía':     {'atk_pct': 0.8, 'crit_rate': 0.6, 'crit_dmg': 0.6, 'impact': 0.1,  'anomaly_mastery': 1.5, 'er': 1.2, ...},
    'Aturdimiento': {'atk_pct': 0.4, 'crit_rate': 0.3, 'crit_dmg': 0.3, 'impact': 1.5,  'anomaly_mastery': 0.2, 'er': 1.0, ...},
    'Soporte':      {'atk_pct': 0.5, 'crit_rate': 0.2, 'crit_dmg': 0.2, 'impact': 0.3,  'anomaly_mastery': 0.3, 'er': 1.5, ...},
    'Defensa':      {'atk_pct': 0.4, 'crit_rate': 0.2, 'crit_dmg': 0.2, 'impact': 0.4,  'anomaly_mastery': 0.2, 'er': 1.0, ...},
    'Disruptivos':  {'atk_pct': 0.7, 'crit_rate': 0.6, 'crit_dmg': 0.6, 'impact': 0.5,  'anomaly_mastery': 0.5, 'er': 0.8, ...},
}
```

Estos pesos se calibran con la misma fuente que RF-06 (Prydwen + 141store) y se reutilizan para mantener coherencia entre RF-06 y RF-14.

### 4.4 — Score de sinergia con habilidades core

`synergy_lookup(pj.id, weapon.pasiva_tipo, weapon.pasiva_descripcion)` consulta una tabla seed:

```sql
CREATE TABLE pj_weapon_synergy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id INTEGER NOT NULL REFERENCES agents(id),
    weapon_pasiva_tipo TEXT NOT NULL,
    bonus REAL NOT NULL DEFAULT 0 CHECK(bonus BETWEEN -1 AND 2),
    razon TEXT,                            -- "Yanagi escala con Anomaly Mastery; armas con AP boost = sinergia natural"
    fuente TEXT,
    UNIQUE(pj_id, weapon_pasiva_tipo)
);
```

Seed inicial: ~45 PJs × ~3-5 categorías de pasiva relevantes = ~180 filas. Carga manual + Claude API one-time (similar a RF-12 pero más acotado).

---

## §5 — Build full (RF-06 + RF-14 conjunto)

### 5.1 — Por qué necesita coordinarse

Una arma con `+ATK%` favorece discos con `CRIT%` (balance de stats), mientras una arma con `+CRIT%` favorece `ATK%`. Optimizar arma y discos por separado ignora estas interacciones.

### 5.2 — Algoritmo

```python
def optimize_full_build(pj, contenido, inventario_armas, inventario_discos,
                        topN_armas=3, topN_builds_por_arma=3):
    """
    Devuelve top combinaciones (arma + 6 discos) ordenadas por score conjunto.
    """
    # 1. Pre-rank armas con score ignorando discos (rápido)
    armas_ranked = sorted(inventario_armas,
                          key=lambda w: score_weapon(pj, w, contenido),
                          reverse=True)[:topN_armas * 2]  # margen 2x

    resultados = []
    for arma in armas_ranked:
        # 2. Para cada arma candidata, optimizar discos asumiendo esa arma
        # (RF-06 con stats efectivos del PJ + arma)
        builds_para_arma = rf06_optimize(pj, arma, inventario_discos,
                                          contenido, topN=topN_builds_por_arma)
        for build in builds_para_arma:
            score_full = score_combinado(pj, arma, build, contenido)
            resultados.append({
                'arma': arma,
                'discos': build.discos,
                'score': score_full,
                'desglose': { ... }
            })

    # 3. Ordenar global y retornar top
    return sorted(resultados, key=lambda x: x['score'], reverse=True)[:topN_armas]
```

`score_combinado` no es la suma simple — pondera con interacciones:
- Penaliza si `CRIT total > 100%` (overflow inútil).
- Bonifica si `(arma + discos)` activa un threshold de `agent_thresholds` (ej. ATK total > 3.400).
- Considera ER total para activar Awakenings condicionales (Burnice nv6: ER ≥ 1.8).

### 5.3 — Latencia objetivo

- Solo armas (sin combinarlo con discos): **< 100 ms** para 49 W-Engines.
- Build full (3 armas × 3 builds RF-06): **< 1.5 s** total (RF-06 corre 3 veces).

---

## §6 — Integración con RF-12 y RF-13

### 6.1 — Con RF-12 (team-aware)

Cuando el optimizador recibe `team_context = [pj_principal, comp1, comp2]`:

- El cálculo de uptime para triggers tipo `team_has_element` o `team_has_faction` deja de ser placeholder (0.5) y se vuelve binario (1.0 o 0).
- Se consulta `team_synergies` para overrides: si una sinergia del par sugiere "para este PJ con este compañero, prefiere armas con ER" (ej. caso Ellen+Dialyn donde la ult adicional necesita energía), el peso de `er` en `STAT_IMPACT_PER_ROL` se ajusta dinámicamente.

### 6.2 — Con RF-13 (retro-feedback)

Cada `lategame_run` registrado contiene el equipo + las armas equipadas. El job de retro-feedback de RF-13 también ajusta:

- **`content_profiles`**: si los runs reales en DA muestran TTL boss promedio de 78s en vez de 90s seed, se actualiza con peso bayesiano (prior seed + likelihood empírica).
- **`weapon_evaluations`**: cuando una arma recomendada como "S+ en DA" rinde mal en 5 runs consecutivos del usuario, baja su tier personal con justificación ("Rendimiento real 2★ promedio vs esperado 3★ — posible conflicto con tu build de discos o sub-óptimo el refinamiento").
- **Calibración de `pj_weapon_synergy.bonus`**: si Daniel arma Lycaon con un W-Engine no convencional y rinde excepcionalmente bien, el bonus de sinergia para ese par se incrementa gradualmente.

---

## §7 — Pipeline de scraping de Prydwen para armas

`app/scripts/scrape_prydwen_weapons.py`:

- Para cada PJ del roster, scrapear la página de Prydwen (`prydwen.gg/zenless/characters/{slug}`) sección "W-Engines".
- Extraer ranking top 5-10 con tier asignado por Prydwen.
- Insertar en `prydwen_weapon_recommendations_snapshots`.
- Frecuencia: semanal (lunes 06:30, junto con `scrape_prydwen_tierlist.py` de RF-13).
- Rate limit: 1 req / 2s, User-Agent identificable, respeta robots.txt.

Volumen: 45 PJs × 1 página = 45 fetches/semana. Trivial.

---

## §8 — UI integration (RF-11)

### 8.1 — Nueva pestaña "Armas"

Subpestañas:
1. **Ranking por PJ** — selector de PJ + selector de contenido → tabla top-N con columnas (rank | arma | tier personal | tier Prydwen | delta | score | refinamiento req | en inventario).
2. **Build full** — para PJ + contenido seleccionado, lista combinaciones (arma + 6 discos) ordenadas por score conjunto. Click expande detalle con desglose por componente.
3. **Catálogo** — vista de las 49 W-Engines con flag `pasiva_modelada` (badge 🟢 completa / 🟠 parcial / 🔴 sin modelar). Editor para agregar overrides manuales en `manual_bonus`.
4. **Comparativo Prydwen** — diferencias entre tu ranking y el de Prydwen, con filtros por delta.

### 8.2 — Toggle en build optimizer (RF-06)

En la vista de RF-06, agregar opción **"Optimizar también el arma (build full)"**: cuando está ON, el output incluye combinaciones (arma + discos) en vez de solo discos. OFF mantiene comportamiento RF-06 base.

### 8.3 — Editor de pasivas estructuradas

Vista admin para agregar/editar entradas en `weapon_passives_structured`. Útil cuando salga un W-Engine nuevo sin modelar, para que Daniel pueda categorizarlo sin esperar update del scraper.

---

## §9 — Output JSON de ejemplo

### 9.1 — Caso "la roca" para Lycaon en DA vs Shiyu

```json
{
  "pj": "Lycaon",
  "pj_id": 5,
  "weapon": "Núcleo Fosilizado Precioso",
  "weapon_id": 22,
  "refinamiento_evaluado": 1,
  "evaluaciones_por_contenido": [
    {
      "contenido": "da",
      "score_normalizado": 92.4,
      "tier_personal": "S+",
      "desglose": {
        "score_atk_base": 24.0,
        "score_stat_secundario": 13.5,
        "score_pasiva_estructurada": 38.7,
        "score_pasiva_textual": 0,
        "score_synergy_pj": 9.2,
        "uptime_pasiva_principal": 0.95,
        "modifier_efectivo": "+18% Impact (95% uptime)"
      },
      "comparacion_prydwen": {
        "tier_prydwen_general": "A",
        "delta": "+2",
        "justificacion": "Núcleo Fosilizado sube de A a S+ en DA. Causa: pasiva 'enemy_hp_above 50%' tiene uptime 95% en este contenido (vs 50% genérico que asume Prydwen). En DA no se mata al boss → la pasiva está activa todo el run."
      }
    },
    {
      "contenido": "shiyu_critical",
      "score_normalizado": 71.2,
      "tier_personal": "A",
      "desglose": {
        "score_pasiva_estructurada": 22.4,
        "uptime_pasiva_principal": 0.55,
        "modifier_efectivo": "+18% Impact (55% uptime)"
      },
      "comparacion_prydwen": {
        "tier_prydwen_general": "A",
        "delta": "=",
        "justificacion": "Alineado con Prydwen. En Shiyu, el TTL del boss es ~75s y el HP cae bajo 50% rápido."
      }
    },
    {
      "contenido": "hollow_zero",
      "score_normalizado": 52.1,
      "tier_personal": "B",
      "desglose": {
        "score_pasiva_estructurada": 11.6,
        "uptime_pasiva_principal": 0.30
      },
      "comparacion_prydwen": {
        "tier_prydwen_general": "A",
        "delta": "-2",
        "justificacion": "Núcleo Fosilizado baja en HZ. Mobs débiles mueren rápido → pasiva con bajo uptime. Considerar alternativas con triggers tipo 'on_chain_attack'."
      }
    }
  ]
}
```

### 9.2 — Build full para Lycaon en DA

```json
{
  "pj": "Lycaon",
  "contenido": "da",
  "top_builds": [
    {
      "rank": 1,
      "score_conjunto": 94.8,
      "arma": {
        "nombre": "Núcleo Fosilizado Precioso",
        "refinamiento": 1,
        "score_arma_solo": 92.4
      },
      "discos": {
        "set_4p": "Aria brillante",
        "set_2p": "Polar Metal",
        "slot_4_main": "Impact%",
        "slot_5_main": "Ice DMG%",
        "slot_6_main": "Impact",
        "score_discos_solo": 89.5
      },
      "interacciones_aplicadas": [
        "ATK total = 2.847 (umbral 2.500 alcanzado → +1.000 ATK del Soukaku)",
        "Impact total = 247 (cap útil 250 cumplido)"
      ],
      "delta_vs_build_actual": "+12.3 score (build actual usa otra arma A-rank)"
    }
  ]
}
```

---

## §10 — Performance esperada

| Operación | Latencia objetivo | Frecuencia |
|-----------|------------------|------------|
| Score de 1 arma para 1 PJ en 1 contenido | < 5 ms | on-demand |
| Ranking de 49 armas para 1 PJ en 1 contenido | < 100 ms | on-demand desde panel |
| Ranking 49 × 4 contenidos | < 500 ms | on-demand desde panel |
| Build full (RF-06+RF-14, 3 armas × 3 builds) | < 1.5 s | on-demand |
| Recálculo full (45 PJs × 49 armas × 4 contenidos = 8.820 evaluaciones) | < 8 s | semanal o tras cambio en `content_profiles` |
| Snapshot Prydwen weapons (45 PJs) | < 90 s | semanal background |

Tabla `weapon_evaluations` mantiene snapshots para evitar recalcular en cada apertura del panel; lookup directo es < 5 ms.

---

## §11 — Status

🟦 **Diseño cerrado (abril 2026)**. Sub-tareas de implementación:

1. Migración `2026-04-XX_05_weapon_optimizer.sql` (5 tablas nuevas + extensiones a `weapons` + índices + seed de `content_profiles` + seed de `pj_weapon_synergy`).
2. Modelado inicial de pasivas: 49 W-Engines × ~1-3 efectos = ~80 filas en `weapon_passives_structured`. **Carga manual** asistida por Claude API one-time (~$3 estimado).
3. `app/scripts/scrape_prydwen_weapons.py` + snapshot inicial.
4. `app/core/weapon_scoring.py` — fórmula de §4 + cálculo de uptime contextual.
5. `app/core/weapon_optimizer.py` — ranking por contenido + integración con RF-06 (build full).
6. `app/ui/weapons_view.py` — pestaña con 4 subpestañas.
7. Toggle "Optimizar también el arma" en `build_optimizer_view.py`.
8. Editor de pasivas estructuradas (admin).
9. Integración con RF-12: lectura de `team_synergies` para uptime de triggers `team_has_*`.
10. Integración con RF-13: hook bayesiano para recalibrar `content_profiles` y ajustar tier personal de armas.
11. Tests E2E — caso "la roca" debe rankear S+ en DA y B en Hollow Zero. Caso de control: armas con `pasiva_tipo='always'` deben rankear igual en todos los contenidos.

---

## §12 — Decisiones cerradas (log)

| Fecha | Decisión | Justificación |
|-------|----------|---------------|
| 2026-04-25 | Alcance v1: **Ranking ideal + disponible** | Sin el ideal, no hay target para banners de armas. Sin el disponible, el ranking es académico. Ambos juntos cubren ambos casos de uso reales (planificación de pulls + optimización inmediata). |
| 2026-04-25 | Modelado de pasivas: **híbrido estructurado + texto fallback** | Permite scoring automático para los casos comunes (~80% de las pasivas siguen patrones repetibles) sin perder casos edge. Pasivas no modeladas usan `score_pasiva_textual` con override manual del usuario. |
| 2026-04-25 | Contexto: **por contenido + delta vs Prydwen** | El caso "la roca" demuestra que sin contexto, el ranking pierde su valor principal. Delta vs Prydwen mantiene coherencia con RF-13 y permite explicar al usuario por qué su ranking difiere. |
| 2026-04-25 | Integración: **coordinado con RF-06 (build full)** | RF-06 + RF-14 trabajando juntos resuelven interacciones (CRIT overflow, thresholds de soporte, ER para Awakenings). Standalone perdería esto. RF-12/13 se enchufan vía hooks ya descritos. |
| 2026-04-25 | Pesos del scoring: **ATK 25 / stat2 15 / pasiva 40 / textual 10 / synergy 10** = 100 | La pasiva es el componente de mayor peso porque distingue entre armas comparables en stat. Refleja el conocimiento del juego (la pasiva define la identidad del W-Engine). |
| 2026-04-25 | Pasivas multi-efecto: **filas separadas en `weapon_passives_structured`** | Permite triggers distintos por efecto (ej. "siempre +ATK" + "al ult, +CRIT") sin estructura JSON anidada compleja. Más queryable, más simple de mantener. |
| 2026-04-25 | `content_profiles` recalibrables vía RF-13 | Los seeds iniciales son estimaciones; el sistema mejora con uso real. Mantiene a RF-14 vivo sin requerir tuning manual constante. |
| 2026-04-25 | Refinamiento: **interpolación lineal R1↔R5** | Datos exactos por refinamiento existen pero la interpolación lineal es suficientemente precisa (error < 5%) y simplifica el modelado. Override manual disponible si una arma escala no-lineal. |
| 2026-04-25 | `pj_weapon_synergy` como tabla seed manual | ~180 filas, carga única con asistencia IA. Datos estables, no requieren refresh frecuente. |
| 2026-04-25 | Build full: **3 armas × 3 builds = top 3 combinaciones** | Equilibra exploración (3 armas distintas) con calidad (3 builds por arma). Más combinaciones = output overwhelming sin valor adicional para el usuario. |
| 2026-04-25 | Diferido a v2: simulador de banner, comparativo R1↔R5 automático, W-Engines de Bangboo | Mantiene v1 enfocado. Estos features tienen valor pero requieren UX dedicada y datos adicionales. |

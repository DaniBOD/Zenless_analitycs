# RF-13 — Validación Lategame + Tier List Personal Calibrado

**Estado:** 🟦 Diseño cerrado (abril 2026)
**Última actualización:** 2026-04-25
**Owner:** DaniBOD
**Documentos relacionados:**
- [`RF-Logic_Optimizador_Build.md`](../RF_Optimizador/RF-Logic_Optimizador_Build.md) (RF-06 — build PJ)
- [`RF-Logic_Optimizador_Equipos.md`](../RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md) (RF-12 — build con equipo)
- `../../README.md` §3.1 RF-13, §10 (próximos pasos)

---

## §1 — Origen y motivación

Prydwen.gg mantiene una tier list general que asume:
- M0 (mindscape 0) salvo nota explícita
- Build "estándar" con set/substats óptimos según meta
- Equipos canónicos del meta corriente

Pero **una cuenta real diverge de esos supuestos en múltiples ejes simultáneos**:
- Mindscapes/cinemas heterogéneos (Daniel tiene Yanagi M2, Burnice M0, Miyabi M1, etc.)
- Builds con substats reales (no idealizados)
- Set 4pc disponible para algunos PJs, set 2+2+2 para otros
- Awakenings v2.5+ activos según ER alcanzado
- Composiciones forzadas por roster (sin Caesar, sin Ju Fufu, etc.)

**Consecuencia:** la tier list de Prydwen es un buen prior, pero **mi tier list real puede diferir significativamente**. Un PJ que Prydwen pone en B puede ser S en mi cuenta gracias al M2 + soporte óptimo; un PJ en S de Prydwen puede ser A si mi build no está terminada.

**RF-13 cierra el loop:** registra runs reales de **contenido lategame** (Shiyu Defense, Deadly Assault) y deriva una tier list **calibrada a la cuenta de Daniel**, comparándola contra Prydwen para hacer explícitas las diferencias.

### 1.1 — Contenido objetivo

| Contenido | Frecuencia | Métricas oficiales | Reset |
|-----------|-----------|--------------------|-------|
| **Shiyu Defense — Critical Node** | Permanente, ciclo ~14 días | Estrellas (0-9), tiempo, equipos por frente | Cada 2 sem (próximo 8 may 2026) |
| **Shiyu Defense — Normal** | Permanente, fijo | Estrellas (0-9), tiempo | N/A (estático) |
| **Deadly Assault** | Permanente, ciclo ~14 días | Score, 3 entidades, weakness | Cada 2 sem (alterna con Shiyu) |
| **Hollow Zero — operaciones** | Permanente | Resilience, claves recolectadas | N/A |

v1 cubre **Shiyu Critical + Deadly Assault** (los dos que rotan y donde la calibración aporta más). Hollow Zero queda diferido a v2.

### 1.2 — Casos paradigmáticos que motivan RF-13

1. **Yanagi M2 + Burnice M0** — Prydwen lo pone en S+ asumiendo M0 en ambos. En mi cuenta, el M2 de Yanagi sube su ceiling de DMG considerablemente; espero que en mi tier list Yanagi suba a "S++ personal" con justificación cuantitativa.
2. **Ellen + Dialyn → Puffer Electro** — RF-12 lo recomienda con `confianza=0.85`. Si mis runs de Shiyu con esa combinación rinden por debajo del esperado (ej. 2★ consistente vs 3★ esperado), RF-13 baja la confianza automáticamente y RF-12 reajusta.
3. **PJ "shilleado" que rinde mal** — un agente que la comunidad pone alto pero que en mi cuenta no funciona (porque no tengo el soporte ideal, o el build es subóptimo) debe aparecer claramente en el delta vs Prydwen para justificar farmeo prioritario.

---

## §2 — Alcance v1 (3 capas)

```
┌─────────────────────────────────────────────────────────────────┐
│  CAPA 1: REGISTRO DE RUNS (manual + OCR del breakdown)          │
│  ──────────────────────────────────────────────────────────────  │
│  Daniel termina un run de Shiyu/DA → toma screenshot del         │
│  resumen → la app extrae: equipo, estrellas, tiempo, DMG share.  │
│  Inserta en lategame_runs + lategame_run_damage.                 │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAPA 2: CÁLCULO DE TIER LIST PERSONAL                          │
│  ──────────────────────────────────────────────────────────────  │
│  Job que se dispara tras cada N runs nuevos (default N=3) o      │
│  on-demand. Calcula por (pj, contenido) métricas agregadas       │
│  → score normalizado → tier S+/S/A/B/C/D → delta vs Prydwen.    │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAPA 3: RETRO-FEEDBACK CON RF-12                               │
│  ──────────────────────────────────────────────────────────────  │
│  Cuando un equipo recomendado por RF-12 acumula evidencia        │
│  (≥3 runs) que contradice la confianza de la sinergia,           │
│  actualiza team_synergies.confianza usando un ajuste bayesiano.  │
│  RF-12 deja de recomendar agresivamente sinergias mal validadas. │
└─────────────────────────────────────────────────────────────────┘
```

**Lo que NO entra en v1:**
- Captura automática durante el run (timeline de buffs/swaps) — diferido a v2 si el manual no escala.
- Hollow Zero, Eventos limitados, Bangboo Tournament — diferidos.
- ML predictivo "qué equipo armar para subir a S+" — eso es RF-12 informado por RF-13, no una nueva capa.
- Subida de runs a comunidad/Discord — fuera de alcance, todo local.

---

## §3 — Modelo de datos

Migración: `2026-04-XX_04_lategame_validation.sql` (8 tablas nuevas + índices).

### 3.1 — Catálogo de enemigos

```sql
-- Enemigos del juego (catálogo estable; raramente cambia entre patches)
CREATE TABLE enemies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_es TEXT NOT NULL UNIQUE,
    nombre_en TEXT,
    tipo TEXT NOT NULL CHECK(tipo IN ('normal','elite','boss','notorious_hunter')),
    faccion TEXT,                         -- 'Ethereal' | 'Thiren' | 'Notorious Hunter' | etc.
    hp_base INTEGER,                      -- HP a nivel referencia (típicamente 80)
    nivel_referencia INTEGER DEFAULT 80,
    escalado_dificultad TEXT,             -- JSON: {"shiyu_critical": 1.5, "da_high": 2.0}
    mecanicas_clave TEXT,                 -- texto libre: enrage, scaling, immunity windows
    fuente TEXT NOT NULL,                 -- 'hakush.in' | 'prydwen' | 'manual'
    fuente_url TEXT,
    fecha_actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

-- Resistencias por elemento (1.0=neutral, <1=resistente, >1=débil)
CREATE TABLE enemy_resistances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enemy_id INTEGER NOT NULL REFERENCES enemies(id) ON DELETE CASCADE,
    elemento TEXT NOT NULL CHECK(elemento IN ('fisico','fuego','hielo','electrico','eter','frost')),
    multiplicador REAL NOT NULL DEFAULT 1.0,
    breakdown_status TEXT CHECK(breakdown_status IN ('weak','neutral','resistant','immune')),
    notas TEXT,
    UNIQUE(enemy_id, elemento)
);

CREATE INDEX idx_enemies_tipo ON enemies(tipo);
CREATE INDEX idx_enemy_res_enemy ON enemy_resistances(enemy_id);
```

### 3.2 — Ciclos rotativos

```sql
-- Cada ciclo ~14 días de Shiyu Critical
CREATE TABLE shiyu_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL UNIQUE,    -- numero secuencial (47, 48, ...)
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    -- JSON: [{"frente":1,"bosses":[enemy_id,...],"modificadores":"...","elemento_recomendado":"..."}, ...]
    frentes TEXT NOT NULL,
    fuente TEXT NOT NULL DEFAULT 'prydwen',
    fecha_capturado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

-- Cada ciclo ~14 días de DA (alterna con Shiyu en términos de meta-attention)
CREATE TABLE da_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL UNIQUE,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    -- JSON: [{"slot":1,"enemy_id":N,"modificadores":"...","weakness_recomendada":"..."},...]
    entidades TEXT NOT NULL,
    fuente TEXT NOT NULL DEFAULT 'prydwen',
    fecha_capturado DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

CREATE INDEX idx_shiyu_fecha ON shiyu_cycles(fecha_inicio, fecha_fin);
CREATE INDEX idx_da_fecha ON da_cycles(fecha_inicio, fecha_fin);
```

### 3.3 — Runs registrados (la fuente primaria de evidencia)

```sql
CREATE TABLE lategame_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    contenido TEXT NOT NULL CHECK(contenido IN ('shiyu_critical','shiyu_normal','da')),
    -- FK condicional según contenido (NULL para 'shiyu_normal' que no rota)
    cycle_id INTEGER,
    -- Frente 1-9 para Shiyu, slot 1-3 para DA
    frente_o_slot INTEGER NOT NULL,
    -- Equipo usado
    pj_principal_id INTEGER NOT NULL REFERENCES agents(id),
    pj_companion_1_id INTEGER REFERENCES agents(id),
    pj_companion_2_id INTEGER REFERENCES agents(id),
    pj_bangboo_id INTEGER,                -- futuro: cuando se modele bangboos
    -- Resultados
    estrellas INTEGER NOT NULL CHECK(estrellas BETWEEN 0 AND 3),
    tiempo_segundos REAL,                 -- NULL si DA (DA reporta score, no tiempo)
    score_juego INTEGER,                  -- score que muestra el juego (DA principalmente)
    completado INTEGER NOT NULL DEFAULT 1 CHECK(completado IN (0,1)),
    -- Trazabilidad
    screenshot_resumen_path TEXT,
    screenshot_breakdown_path TEXT,
    fuente_captura TEXT NOT NULL DEFAULT 'manual_ocr',  -- 'manual_ocr' | 'manual_typed'
    notas TEXT
);

-- Breakdown de DMG por agente del run (lo que el juego muestra al final)
CREATE TABLE lategame_run_damage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES lategame_runs(id) ON DELETE CASCADE,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    posicion INTEGER NOT NULL CHECK(posicion BETWEEN 1 AND 3),
    dmg_total INTEGER NOT NULL,
    dmg_porcentaje REAL NOT NULL,         -- 0-100
    rol_efectivo TEXT,                    -- 'main_dps' | 'sub_dps' | 'support_dmg' | 'enabler'
    UNIQUE(run_id, agent_id)
);

CREATE INDEX idx_runs_fecha ON lategame_runs(fecha DESC);
CREATE INDEX idx_runs_pj ON lategame_runs(pj_principal_id, contenido);
CREATE INDEX idx_runs_equipo ON lategame_runs(pj_principal_id, pj_companion_1_id, pj_companion_2_id);
CREATE INDEX idx_run_dmg_agent ON lategame_run_damage(agent_id);
```

### 3.4 — Tier list calibrada (vista materializada)

```sql
-- Recalculada por el job de la Capa 2; tabla, no view, para soportar histórico
CREATE TABLE tier_list_personal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_id INTEGER NOT NULL REFERENCES agents(id),
    -- Granularidad: 'shiyu_global', 'da_global', 'shiyu_fuego', 'shiyu_hielo',
    -- 'da_eter', 'shiyu_frente_1', etc. — diseño extensible
    contenido TEXT NOT NULL,
    tier TEXT NOT NULL CHECK(tier IN ('S+','S','A','B','C','D')),
    score_normalizado REAL NOT NULL CHECK(score_normalizado BETWEEN 0 AND 100),
    -- Métricas agregadas que justifican el tier
    runs_evaluados INTEGER NOT NULL,
    win_rate REAL,                        -- % completado (3★ no requerido)
    rate_3_estrellas REAL,
    avg_dmg_share REAL,                   -- % promedio del DMG total que aporta
    avg_tiempo_normalizado REAL,          -- tiempo / tiempo_par_3star del ciclo
    -- Comparación
    delta_vs_prydwen TEXT,                -- '+2', '+1', '=', '-1', '-2' (deltas en tiers)
    prydwen_tier_referencia TEXT,
    justificacion TEXT,                   -- texto autogenerado explicando el delta
    fecha_calculado DATETIME DEFAULT CURRENT_TIMESTAMP,
    snapshot_id INTEGER,                  -- agrupa todos los cálculos de la misma corrida
    UNIQUE(pj_id, contenido, snapshot_id)
);

-- Snapshots periódicos de la tier list de Prydwen para comparativos históricos
CREATE TABLE prydwen_tier_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    contenido TEXT NOT NULL,              -- 'shiyu' | 'da' | 'general'
    -- JSON: {"Yanagi":"S+", "Burnice":"S", ...}
    tier_data TEXT NOT NULL,
    fuente_url TEXT NOT NULL,
    parser_version TEXT,
    UNIQUE(fecha, contenido)
);

CREATE INDEX idx_tier_pj ON tier_list_personal(pj_id, snapshot_id);
CREATE INDEX idx_tier_contenido ON tier_list_personal(contenido, snapshot_id);
CREATE INDEX idx_prydwen_fecha ON prydwen_tier_snapshots(fecha DESC, contenido);
```

---

## §4 — Pipeline de captura manual

### 4.1 — Flujo del usuario

```
1. Daniel termina un run de Shiyu/DA → aparece pantalla de resumen.
2. Pulsa F11 (hotkey global definido para RF-13).
3. La app captura DOS screenshots:
   (a) Pantalla de resumen (estrellas, tiempo, equipo).
   (b) Pantalla de "Battle Stats" / breakdown de DMG por agente
       (Daniel debe navegar manualmente a esta pantalla — el toast
        recuerda hacerlo si la primera captura no la incluye).
4. OCR procesa ambas, valida consistencia (los 3 PJs del resumen
   deben estar en el breakdown), inserta en lategame_runs +
   lategame_run_damage.
5. Toast confirma: "Run registrado: Yanagi+Burnice+Soukaku, Frente 4 Shiyu C47, 3★ 1:47, Yanagi 58% DMG."
6. Si el job de tier list se dispara (≥N=3 runs nuevos), notifica:
   "Tier list recalculada: Yanagi sube de S a S+ en Shiyu Critical."
```

### 4.2 — OCR del breakdown DMG

Reutiliza el backend OCR híbrido de RF-09 (`app/core/ocr_backend.py`):
- **Tesseract** para nombres de PJs (texto)
- **PaddleOCR** para los números de DMG y porcentajes

Layout del Battle Stats screen en ZZZ — ROIs precalibrados:
```
┌──────────────────────────────────────────────────────┐
│ BATTLE STATS                                          │
├──────────────────────────────────────────────────────┤
│ [icon] Yanagi          12,847,392     58.3%          │  ← ROI fila 1
│ [icon] Burnice          5,124,101     23.2%          │  ← ROI fila 2
│ [icon] Soukaku          4,082,553     18.5%          │  ← ROI fila 3
└──────────────────────────────────────────────────────┘
```

ROIs calibrados en primer uso (asistente "captura un breakdown de ejemplo y marca las regiones"). Persisten en `user_config.toml::lategame_capture.rois`.

### 4.3 — Validación de consistencia

Antes de insertar, el pipeline valida:
- Suma de `dmg_porcentaje` ≈ 100% (tolerancia ±2% por redondeo del juego).
- Los 3 PJs del breakdown coinciden con los 3 del resumen.
- `pj_principal_id` está en el roster (`agents`).
- Si `contenido='shiyu_critical'`, hay un `shiyu_cycles` activo en `fecha`.

Cualquier fallo: el toast pide confirmación manual ("¿Yanagi 58.3%? [✓] [✗ corregir]").

### 4.4 — Captura de respaldo: typed input

Si OCR falla 2 veces seguidas o el usuario lo prefiere, modal de entrada manual con autocompletado del roster. `fuente_captura = 'manual_typed'` para distinguir en queries de calidad.

---

## §5 — Algoritmo del tier list calibrado

### 5.1 — Trigger del recálculo

- **Automático:** tras cada `N=3` runs nuevos insertados (configurable en `user_config.toml::lategame.recalc_threshold`).
- **On-demand:** botón "Recalcular tier list" en el panel.
- **Programado:** semanal (domingos 03:00) para incorporar drift.

### 5.2 — Snapshot atómico

Cada recálculo genera un nuevo `snapshot_id` (UUID corto o timestamp). Toda la tabla `tier_list_personal` se inserta con ese ID, no se actualiza la anterior. Esto permite:
- Histórico completo de cómo evolucionó la tier list semana a semana.
- Rollback trivial (filtrar por snapshot anterior).
- Comparativos de "cómo cambió el tier de Yanagi en los últimos 6 meses".

Limpieza: mantener todos los snapshots de los últimos 90 días + 1 por mes en histórico anterior (job mensual).

### 5.3 — Métricas agregadas por (pj_id, contenido)

Para cada PJ y cada granularidad de contenido, calcular sobre los últimos `K` runs (default `K=20`, mínimo `K_min=3` para emitir tier):

```python
runs = lategame_runs WHERE pj_principal_id = pj_id
                      AND contenido_match(contenido)
                   ORDER BY fecha DESC
                   LIMIT 20

if len(runs) < 3:
    tier = NULL  # "datos insuficientes"
    continue

win_rate = sum(r.completado) / len(runs)
rate_3star = sum(r.estrellas == 3) / len(runs)
avg_dmg_share = mean(r.damage_breakdown[pj_id].dmg_porcentaje for r in runs)
avg_tiempo_norm = mean(r.tiempo_segundos / par_tiempo_3star(r.cycle_id, r.frente_o_slot)
                       for r in runs if r.tiempo_segundos)
```

### 5.4 — Score normalizado (0-100)

Combinación lineal con pesos que favorecen completar > tiempo > DMG share:

```
score_raw =
    w_3star    × rate_3star          +    # peso 0.45
    w_win      × win_rate            +    # peso 0.20
    w_dmg      × normalize(avg_dmg_share, expected_for_role) +  # peso 0.20
    w_tiempo   × (1 - clip(avg_tiempo_norm - 1, 0, 1))         # peso 0.15

score_normalizado = clip(score_raw × 100, 0, 100)
```

`normalize(dmg_share, expected_for_role)`:
- Para `main_dps`: esperado 50-65% → 100 si ≥55%
- Para `sub_dps`: esperado 25-40% → 100 si ≥30%
- Para `support_dmg`: esperado 10-20% → 100 si ≥15%
- Para `enabler` (Caesar/Soukaku): esperado 5-15% → 100 si ≥8%

El rol esperado se infiere de `agents.rol` cruzado con la composición.

### 5.5 — Asignación de tier

Buckets fijos sobre `score_normalizado`:

| Tier | Rango score |
|------|-------------|
| **S+** | 90-100 |
| **S**  | 80-89 |
| **A**  | 65-79 |
| **B**  | 50-64 |
| **C**  | 30-49 |
| **D**  | 0-29 |

Decisión: **buckets fijos, no cuartiles**, para que la tier list sea estable año a año aunque cambie el meta. Si el meta sube globalmente (todos en S+), el tier refleja eso correctamente — no se "deforma" por curve fitting.

### 5.6 — Cálculo del delta vs Prydwen

```
prydwen_tier = lookup(prydwen_tier_snapshots
                      WHERE fecha = MAX(fecha)
                        AND contenido = strip_subdivision(contenido)
                      → tier_data[pj_nombre])

map_tiers = {'S+': 6, 'S': 5, 'A': 4, 'B': 3, 'C': 2, 'D': 1}
delta = map_tiers[tier_personal] - map_tiers[prydwen_tier]
delta_str = '+{n}' if delta>0 else '={n}' if delta==0 else '-{n}'
```

### 5.7 — Generación de justificación textual

Plantillas parametrizadas según el delta:

- `delta = +2`: *"{pj} sube 2 tiers (Prydwen: {prydwen_tier} → personal: {tier}). Atribuible a {causa_principal}: rate_3star {rate_3star_personal:.0%} vs típico {rate_3star_typical:.0%}. Mindscape M{mindscape} probablemente contribuye."*
- `delta = -1` o peor: *"{pj} baja {abs(delta)} tier(s). Posibles causas: build incompleta ({slots_optimos_pct:.0%} de slots óptimos), soporte subóptimo ({equipo_promedio}), o composición incorrecta para tu meta."*
- `delta = 0`: *"{pj} alineado con Prydwen ({tier}). Performance esperada en tu cuenta."*

`causa_principal` se infiere por correlación: ¿el delta correlaciona con M2+? ¿con tener un set 4pc completo? ¿con jugar con cierto compañero? Heurística simple basada en groupby + media de score.

---

## §6 — Retro-feedback con RF-12 (Loop Completo)

### 6.1 — Disparador

Cuando se inserta un nuevo `lategame_run` y la tupla `(pj_principal_id, pj_companion_1_id, pj_companion_2_id)` coincide con una sinergia recomendada por RF-12 (existe `team_synergies` con confianza ≥ 0.6 para algún par), encolar evento de validación.

### 6.2 — Acumulación de evidencia

Para cada par `(pj_a, pj_b)` registrado en `team_synergies`, mantener métricas rolling:

```sql
-- Vista (no tabla; calculada on-the-fly)
SELECT
    ts.id AS synergy_id,
    ts.confianza AS confianza_ai,
    COUNT(*) AS runs_evidencia,
    AVG(CASE WHEN lr.estrellas = 3 THEN 1.0 ELSE 0.0 END) AS rate_3star_observado,
    AVG(lrd.dmg_porcentaje) FILTER (WHERE lrd.agent_id = ts.pj_a_id) AS dmg_share_pj_a,
    -- ...
FROM team_synergies ts
JOIN lategame_runs lr
  ON (lr.pj_principal_id, lr.pj_companion_1_id) IN ((ts.pj_a_id, ts.pj_b_id), (ts.pj_b_id, ts.pj_a_id))
  OR (lr.pj_principal_id, lr.pj_companion_2_id) IN (...)
LEFT JOIN lategame_run_damage lrd ON lrd.run_id = lr.id
WHERE lr.fecha > date('now', '-90 days')
GROUP BY ts.id;
```

### 6.3 — Ajuste bayesiano de confianza

Cuando `runs_evidencia ≥ 3`, recalcular `team_synergies.confianza`:

```
prior = confianza_ai           # lo que dijo Claude API
expected_3star_rate = 0.75     # asunción: una sinergia "fuerte" debería rendir 75%+ 3★

# Evidencia a favor: el rate observado iguala o supera expected
likelihood_pos = clip(rate_3star_observado / expected_3star_rate, 0, 1.5)

# Bayes simplificado: peso prior decrece con N
peso_prior = 1.0 / (1.0 + 0.3 * runs_evidencia)
peso_evidencia = 1.0 - peso_prior

confianza_post = peso_prior * prior + peso_evidencia * likelihood_pos
confianza_post = clip(confianza_post, 0.0, 1.0)
```

Resultado:
- Sinergia "Ellen+Dialyn → Puffer Electro" recomendada por IA con `confianza=0.85`.
- Daniel registra 5 runs con esa combinación: 1×3★, 4×2★ → `rate_3star = 0.20`.
- `likelihood_pos = 0.20 / 0.75 = 0.27`
- `peso_prior = 1/(1+1.5) = 0.40`, `peso_evidencia = 0.60`
- `confianza_post = 0.40 × 0.85 + 0.60 × 0.27 = 0.50`
- Threshold de RF-12 para aplicar override es `≥ 0.7` → la recomendación deja de aplicarse automáticamente.

### 6.4 — Auditoría del ajuste

Cada ajuste se registra en `team_synergies` actualizando `confianza` + agregando entrada en una tabla nueva `team_synergy_adjustments`:

```sql
CREATE TABLE team_synergy_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synergy_id INTEGER NOT NULL REFERENCES team_synergies(id),
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    confianza_anterior REAL,
    confianza_nueva REAL,
    runs_evidencia INTEGER,
    rate_3star_observado REAL,
    motivo TEXT,                  -- 'rf13_bayesiano' | 'manual_user'
    notas TEXT
);
```

Permite a Daniel auditar **por qué** RF-12 dejó de recomendar X (toast informativo opcional).

### 6.5 — Override manual

Si Daniel discrepa con el ajuste automático ("sé que esa sinergia funciona, no la registré bien"), puede editar `team_synergies.confianza` manualmente desde el panel; el sistema marca `congelado=1` y el job bayesiano deja de tocarla hasta que Daniel libere el flag.

---

## §7 — Carga inicial: scraping + seed

### 7.1 — Scraper de enemigos (Hakush.in + Prydwen)

- **Hakush.in** (`zzz3.hakush.in/boss`) — JSON estructurado, ideal para HP base, escalado, resistencias por elemento. Carga única + refresh cada patch (~6 sem).
- **Prydwen Shiyu Defense Analytics** — HTML, parser específico. Carga al detectar nuevo ciclo (cada 2 sem).
- **Game8 / IcyVeins** — fallback manual para mecánicas no datamined.

Implementación: `app/scripts/scrape_enemies.py` (standalone, no parte del runtime de la app). Rate limit: 1 req/2s, User-Agent identificable, respeta robots.txt.

### 7.2 — Seed de la tier list de Prydwen

`app/scripts/scrape_prydwen_tierlist.py`:
- Snapshot inicial: tier list general de Prydwen (~45 PJs × 3 contenidos: shiyu, da, general).
- Refresh: semanal, los lunes 06:00.
- Almacena en `prydwen_tier_snapshots`.
- Si Prydwen redefine sus tiers (ej. agrega SS+), parser_version se incrementa y el job loggea el cambio para revisión manual.

### 7.3 — Volumen estimado

| Tabla | Filas iniciales | Crecimiento |
|-------|----------------|-------------|
| `enemies` | ~80 (todos los notorious + bosses + elites únicos) | +5/patch |
| `enemy_resistances` | ~480 (80 × 6 elementos) | proporcional |
| `shiyu_cycles` | 1 (ciclo activo) | +1/2 sem |
| `da_cycles` | 1 | +1/2 sem |
| `lategame_runs` | 0 (Daniel los carga jugando) | ~5-15/sem |
| `lategame_run_damage` | 0 | 3 × runs |
| `tier_list_personal` | ~135 (45 PJs × 3 contenidos) | +135/snapshot |
| `prydwen_tier_snapshots` | 3 | +3/sem |

Tras 1 año: ~7K runs, ~21K damage rows, ~7K tier list rows. SQLite resuelve esto sin esfuerzo.

---

## §8 — UI integration (RF-11)

### 8.1 — Hotkey global nuevo

`F11` — captura run lategame. Reasignable. Documentado en RF-11 §Hotkeys.

### 8.2 — Nueva pestaña "Lategame"

Subpestañas:
1. **Runs recientes** — tabla cronológica con filtros por contenido/PJ/ciclo. Click en un run abre detalle (screenshots + breakdown + edición manual).
2. **Tier List Personal** — vista S+/S/A/B/C/D por columnas con cards de cada PJ. Cada card muestra: tier personal, tier Prydwen, delta con flecha de color, runs evaluados, justificación expandible.
3. **Comparativo Prydwen** — tabla side-by-side: PJ | tier Prydwen | tier personal | delta | causa probable.
4. **Histórico** — gráfico temporal (recharts vía PySide6 + QtCharts) de cómo evolucionó el tier de cada PJ.
5. **Ciclos** — vista de ciclos pasados/actual con lo que farmeaste y qué te falta.

### 8.3 — Toast tras registrar un run

Formato:
```
📊 Run registrado
Yanagi + Burnice + Soukaku · Shiyu C47 Frente 4
3★ · 1:47 · Yanagi 58% DMG
[Ver detalle]   [Recalcular tier list ahora]
```

### 8.4 — Indicador visual del retro-feedback

En el panel de RF-12 ("Equipos"), las sinergias cuyo `confianza` fue ajustado por RF-13 muestran un badge:
- 🟢 `+RF-13` — runs reales confirman la recomendación
- 🟠 `−RF-13` — runs reales bajaron la confianza
- 🔒 — congelado por override manual

---

## §9 — Output JSON de ejemplo

### 9.1 — Tier list personal vs Prydwen (un PJ)

```json
{
  "pj": "Yanagi",
  "pj_id": 12,
  "snapshot_id": "snap_2026-04-25_03-00-00",
  "fecha_calculado": "2026-04-25T03:00:12Z",
  "rankings": [
    {
      "contenido": "shiyu_critical",
      "tier_personal": "S+",
      "score_normalizado": 93.2,
      "metricas": {
        "runs_evaluados": 17,
        "win_rate": 1.00,
        "rate_3_estrellas": 0.94,
        "avg_dmg_share": 56.7,
        "avg_tiempo_normalizado": 0.78
      },
      "comparacion_prydwen": {
        "tier_prydwen": "S",
        "delta": "+1",
        "fecha_snapshot_prydwen": "2026-04-21",
        "justificacion": "Yanagi sube 1 tier (Prydwen: S → personal: S+). Atribuible a Mindscape M2 (M0 asumido en Prydwen): rate 3★ 94% vs típico 80%. Build con Tecno Pícido 4pc completo + substats CRIT 78% / DMG 250%."
      }
    },
    {
      "contenido": "da",
      "tier_personal": "S",
      "score_normalizado": 84.0,
      "metricas": { "runs_evaluados": 8, "win_rate": 1.00, "rate_3_estrellas": 0.62, "avg_dmg_share": 51.3 },
      "comparacion_prydwen": {
        "tier_prydwen": "S+",
        "delta": "-1",
        "justificacion": "Yanagi baja 1 tier en DA. Causa probable: bosses actuales del ciclo C18 tienen alta resistencia a Eléctrico (multiplicador 0.7); composición sin Stunner reduce ventanas de DMG."
      }
    }
  ]
}
```

### 9.2 — Ajuste de confianza retro-feedback

```json
{
  "synergy_id": 142,
  "par": ["Ellen", "Dialyn"],
  "set_recomendado_pj_a": "Puffer Electro",
  "ajuste": {
    "confianza_anterior": 0.85,
    "confianza_nueva": 0.50,
    "runs_evidencia": 5,
    "rate_3star_observado": 0.20,
    "motivo": "rf13_bayesiano",
    "fecha": "2026-04-25T03:00:14Z"
  },
  "consecuencia": "RF-12 deja de aplicar override de set automáticamente (threshold=0.70). Recomendación queda como sugerencia informativa.",
  "accion_recomendada": "Validar con 3 runs adicionales antes de descartar. Considerar revisar build de Ellen — nivel de discos en slot 4-6 puede estar limitando."
}
```

---

## §10 — Performance esperada

| Operación | Latencia objetivo | Frecuencia |
|-----------|------------------|------------|
| Captura + OCR de breakdown DMG | < 1.5 s | 5-15/sem (manual) |
| Inserción en lategame_runs/_damage | < 50 ms | tras OCR |
| Recálculo tier list completo (45 PJs × 3 contenidos) | < 3 s | tras N=3 runs o on-demand |
| Snapshot Prydwen (scrape + parse + insert) | < 5 s | semanal |
| Snapshot enemies/cycles | < 30 s | cada 2 sem |
| Lookup retro-feedback al insertar run | < 200 ms | tras cada insert |
| Ajuste bayesiano de confianza | < 100 ms | si hay sinergias afectadas |

Sin requerimientos de tiempo real estricto: este RF es de análisis y consulta, no de toast crítico durante juego.

---

## §11 — Status

🟦 **Diseño cerrado (abril 2026)**. Sub-tareas de implementación:

1. Migración `2026-04-XX_04_lategame_validation.sql` (8 tablas + índices + el ajuste a `team_synergies` para `congelado` flag).
2. `app/scripts/scrape_enemies.py` + carga inicial de ~80 enemigos.
3. `app/scripts/scrape_prydwen_tierlist.py` + snapshot inicial.
4. `app/core/lategame_capture.py` — pipeline OCR del breakdown DMG (reutiliza `ocr_backend.py`).
5. `app/core/tier_list_calculator.py` — algoritmo de §5.
6. `app/core/retro_feedback.py` — ajuste bayesiano de §6.
7. `app/ui/lategame_view.py` — pestaña con 5 subpestañas.
8. Hotkey global F11 + integración con RF-11.
9. Asistente "calibrar ROIs del breakdown DMG" (primer uso).
10. Tests E2E con runs sintéticos: validar que un equipo con `rate_3star=0.95` consistente sube 1-2 tiers vs Prydwen.
11. Validación cruzada: cargar 20 runs reales de Daniel, verificar que la tier list resultante "se siente correcta" (sanity check antes de soltar el retro-feedback automático).

---

## §12 — Decisiones cerradas (log)

| Fecha | Decisión | Justificación |
|-------|----------|---------------|
| 2026-04-25 | Granularidad de captura: **Resultado + breakdown DMG** | Mejor relación esfuerzo/insight. El breakdown desbloquea métricas por agente clave para el tier list (DMG share). El timeline completo de v2 escalaría mal manualmente. |
| 2026-04-25 | Modelo de enemigos: **Tabla rica + scraping** | Hakush.in y Prydwen tienen data cuantitativa accesible. Permite calcular DMG esperado, justificar tiers ("delta atribuible a resistencia X"), y futuro modelado predictivo. |
| 2026-04-25 | Tier list output: **Por contenido + delta vs Prydwen** | El valor de RF-13 está en explicar las diferencias con la fuente de meta más usada por la comunidad. Tier global perdería matiz; por equipo sería incomparable con Prydwen. |
| 2026-04-25 | Feedback loop: **Loop completo (bayesiano)** | RF-12 sin validación se queda especulativo; RF-13 solo informativo desperdicia su evidencia. El bayesiano con prior IA + likelihood empírica es la forma matemáticamente correcta de combinar ambas señales. |
| 2026-04-25 | Buckets de tier: **fijos (no cuartiles)** | Evita "deformación" del tier list cuando el meta sube globalmente. Permite ver progresión real ("hace 6 meses tenía 8 PJs en S; ahora tengo 14"). |
| 2026-04-25 | Trigger del recálculo: **N=3 runs nuevos + semanal + on-demand** | N=3 evita ruido de 1 run atípico; semanal incorpora drift sin que Daniel piense; on-demand para validación inmediata tras un cambio de build. |
| 2026-04-25 | Retro-feedback: **likelihood capada en 1.5** | Evita que un par de runs excepcionales (lucky 3★ con buen RNG) inflen la confianza de una sinergia que no es estable. |
| 2026-04-25 | Snapshots de tier list: **histórico atómico, no UPDATE** | Permite auditar evolución, comparar versiones del meta, y rollback sin pérdida. Costo de almacenamiento despreciable (tabla pequeña). |
| 2026-04-25 | Override manual: **flag `congelado`** | Daniel siempre tiene la última palabra. El sistema es asistente, no autoridad. Auditable vía `team_synergy_adjustments`. |
| 2026-04-25 | Alcance v1: **Shiyu Critical + DA, sin Hollow Zero** | HZ tiene métricas de éxito muy distintas (resilience, claves) que requieren modelo aparte. Diferir hasta tener evidencia de que RF-13 v1 funciona. |

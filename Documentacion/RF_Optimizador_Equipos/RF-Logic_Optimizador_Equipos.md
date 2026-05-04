# RF-12 — Optimizador de Build Sensible al Equipo + Sugerencia de Equipos

**Versión:** 1.0 (abril 2026)
**Autor:** Daniel (DaniBOD)
**Refs:**
- `README.md` §3.1 RF-12 (descripción corta)
- `Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md` (RF-06 base que se extiende)
- `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` §11 (scoring engine compartido)
- `README.md` §8 (descripción narrativa preexistente del optimizador de equipos — ahora formaliza este RF)

---

## 1. Origen y motivación

El RF-06 (optimizador de build) trata a cada PJ como una unidad aislada: dado Miyabi y su inventario, propone los 6 mejores discos. Pero en ZZZ los equipos son de 3 PJs y la build óptima de un PJ **cambia según con quién juegue**. Caso paradigmático que motiva este RF:

### 1.1 Caso Ellen Joe — set primario cambia con el compañero

| Equipo | Set 4pc óptimo de Ellen | Razón |
|---|---|---|
| Ellen sola / equipo neutro | **Polar Metal** o **Tecno Pícido** | Ice DMG / ATK + crit puros, escalado directo |
| Ellen + **Dialyn** | **Puffer Electro** | Dialyn gatillea Ultimate adicional por sus habilidades core; Ellen necesita más Energy Recharge para encadenar burst → Puffer (ATK% + ER) gana sobre Polar/Pícido |

Esto es más fuerte que ajustar pesos de substat: el **set primario recomendado se invierte** según el contexto. RF-06 no captura esto porque `disc_set_archetype` sólo conecta set ↔ arquetipo genérico.

### 1.2 Otros ejemplos representativos

- **Miyabi + Yanagi** (Section 6): Disorder Hielo+Eléctrico activo + Additional Ability de facción. Miyabi gana peso en Maestría de Anomalía (escalado de Disorder); ya no es "pure CRIT/Ice DMG".
- **Burnice + Lucy** (Sons of Calydon): Lucy bufféa ATK del equipo si supera 2,000 ATK. Burnice puede sacrificar algo de ATK% propio porque viene buff externo.
- **Equipo con/sin Stunner**: si el equipo no tiene Stun (Lycaon/Koleda/Qingyi/Pulchra/Anby), las ventanas de burst son más cortas → CRIT importa más vs estabilidad.
- **Equipo con Astra Yao ≥ 3,429 ATK**: bufféa +1,200 ATK al equipo → reduce el valor marginal del ATK% en los demás miembros.

Estos patrones son el tipo de conocimiento que vive disperso en Prydwen, comentarios de Reddit, guías de creators y experimentos comunitarios — exactamente lo que un LLM con buen contexto puede sintetizar sin que Daniel hardcodee 990+ pares manualmente.

---

## 2. Alcance v1 (decisiones cerradas — abril 2026)

### 2.1 Las 3 capas

| Capa | Qué hace | Output |
|---|---|---|
| **Capa 1 — Pesos** | Ajusta `peso_substat` del scoring engine según el equipo del PJ | Dict `{substat: peso_modificado}` aplicado encima del default del arquetipo |
| **Capa 2 — Set override** | Cambia el set 4pc/2pc recomendado según sinergias específicas | `set_id` override que reemplaza al primario del arquetipo |
| **Capa 3 — Sugerir equipo** | Dado un PJ, propone los 2 mejores compañeros de su roster | Top 3 composiciones de equipo con score y justificación |

### 2.2 Decisiones cerradas

| Pregunta | Respuesta v1 |
|---|---|
| **Alcance** | Las 3 capas (pesos + override de set + sugerir equipo). |
| **Rol IA** | Catalogadora — la IA rellena tablas `team_synergies` y `team_compositions`; el optimizador en runtime es 100% determinístico leyendo esas tablas. |
| **Refresh** | On-demand (botón "Refrescar sinergias" en config) + automático al detectar PJ/set nuevo no catalogado. |
| **Modelo IA** | Claude API (sonnet por default, opus para casos complejos) con prompt estructurado y RAG sobre Prydwen/HoYoLAB cargado en `data/sources/`. |

### 2.3 Diferenciación con otros RFs

| | RF-06 (build individual) | RF-10 (Additional Abilities) | RF-12 (este) |
|---|---|---|---|
| Pregunta | Mejor 6 discos para 1 PJ aislado | Catálogo de buffs por composición | Mejor build de 1 PJ EN UN EQUIPO + mejor equipo para 1 PJ |
| Input | PJ + inventario | Composición de 3 PJs | PJ + inventario + (opcional team_context) / PJ + roster |
| Output | Top 3 builds | Lista de Additional Abilities activas | Build con team_context + Top 3 equipos sugeridos |
| Determinismo | 100% | 100% (lookup tabla) | Runtime 100% deterministic; precómputo via IA |

---

## 3. Modelo de datos

### 3.1 Tabla nueva — `team_synergies`

Catálogo IA-poblado de sinergias entre pares de PJs.

```sql
CREATE TABLE IF NOT EXISTS team_synergies (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_a_id                         INTEGER NOT NULL REFERENCES agents(id),
    pj_b_id                         INTEGER NOT NULL REFERENCES agents(id),
    sinergia_existe                 INTEGER NOT NULL CHECK(sinergia_existe IN (0,1)),
    tipo                            TEXT,         -- 'disorder_elemento' | 'additional_ability_faccion' | 'set_override' | 'buff_pasivo' | 'rotation_specific' | 'ninguna'
    set_recomendado_pj_a            INTEGER REFERENCES disc_sets(id),  -- Capa 2: override del 4pc para PJ_A en este equipo
    set_recomendado_pj_b            INTEGER REFERENCES disc_sets(id),  -- idem para PJ_B
    pesos_substat_override_pj_a     TEXT,         -- Capa 1: JSON {"sub": peso_modif, ...}
    pesos_substat_override_pj_b     TEXT,
    buff_descripcion                TEXT,         -- texto resumido del buff/sinergia
    confianza                       REAL,         -- 0.0-1.0 reportada por la IA
    fuente                          TEXT NOT NULL DEFAULT 'ai_claude',  -- 'ai_claude' | 'ai_gpt' | 'manual_daniel' | 'prydwen_extract'
    modelo_version                  TEXT,         -- ej: 'claude-opus-4-7'
    fecha_generado                  DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas                           TEXT,
    UNIQUE(pj_a_id, pj_b_id)
);

-- Convención: pj_a_id < pj_b_id siempre (par ordenado, evita duplicados)
CREATE INDEX IF NOT EXISTS idx_ts_pj_a ON team_synergies(pj_a_id);
CREATE INDEX IF NOT EXISTS idx_ts_pj_b ON team_synergies(pj_b_id);
CREATE INDEX IF NOT EXISTS idx_ts_existe ON team_synergies(sinergia_existe) WHERE sinergia_existe = 1;
```

**Cardinalidad esperada:** 45 PJs → C(45,2) = **990 pares**. Asumiendo ~30% con sinergia real, ~300 filas activas. La pasada inicial al cargar el roster cuesta una llamada API por par (pueden batchear 10 pares por request → ~100 calls).

### 3.2 Tabla nueva — `team_compositions`

Composiciones de 3 PJs propuestas por la IA (Capa 3).

```sql
CREATE TABLE IF NOT EXISTS team_compositions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    pj_principal_id          INTEGER NOT NULL REFERENCES agents(id),    -- el PJ "core" del equipo
    pj_companion_1_id        INTEGER NOT NULL REFERENCES agents(id),
    pj_companion_2_id        INTEGER NOT NULL REFERENCES agents(id),
    score_composicion        REAL,                                       -- 0.0-1.0 normalizado
    rank_para_principal      INTEGER,                                    -- 1, 2, 3... orden dentro del PJ principal
    contenido_optimo         TEXT,                                       -- 'shiyu_general' | 'shiyu_elite' | 'deadly_assault' | 'exploracion'
    justificacion            TEXT,                                       -- síntesis IA: por qué este equipo
    sinergias_activadas      TEXT,                                       -- JSON [team_synergies.id, ...]
    requiere_stunner         INTEGER DEFAULT 0 CHECK(requiere_stunner IN (0,1)),
    flag_anti_shill          TEXT,                                       -- ej: 'no_apto_shiyu_frente_2_v2.6'
    fuente                   TEXT NOT NULL DEFAULT 'ai_claude',
    modelo_version           TEXT,
    fecha_generado           DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas                    TEXT,
    UNIQUE(pj_principal_id, pj_companion_1_id, pj_companion_2_id, contenido_optimo)
);

CREATE INDEX IF NOT EXISTS idx_tc_principal ON team_compositions(pj_principal_id, rank_para_principal);
CREATE INDEX IF NOT EXISTS idx_tc_score ON team_compositions(score_composicion DESC);
```

**Cardinalidad esperada:** Top 3 equipos × 45 PJs × 4 contenidos = **540 filas máx**. Real será menor porque muchos PJs no son DPS principal viable.

### 3.3 Tabla nueva — `ai_catalog_runs`

Audit log de cada llamada al modelo (para budget tracking y reproducibilidad).

```sql
CREATE TABLE IF NOT EXISTS ai_catalog_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           DATETIME DEFAULT CURRENT_TIMESTAMP,
    operacion       TEXT NOT NULL,    -- 'team_synergy_pair' | 'team_composition_topN' | 'pj_kit_extract' | 'set_classify'
    modelo          TEXT NOT NULL,    -- 'claude-opus-4-7' | 'claude-sonnet-4-6' | etc.
    pj_ids          TEXT,             -- JSON [id, id, ...] PJs involucrados
    prompt_hash     TEXT,             -- SHA1 del prompt para detectar duplicados
    tokens_input    INTEGER,
    tokens_output   INTEGER,
    costo_usd       REAL,
    duracion_ms     INTEGER,
    exito           INTEGER NOT NULL CHECK(exito IN (0,1)),
    error_msg       TEXT,
    response_json   TEXT
);

CREATE INDEX IF NOT EXISTS idx_acr_fecha ON ai_catalog_runs(fecha DESC);
CREATE INDEX IF NOT EXISTS idx_acr_operacion ON ai_catalog_runs(operacion);
```

### 3.4 Migración

Las 3 tablas se crean en migración separada `2026-04-XX_03_team_synergies_ai_catalog.sql` cuando se implemente RF-12. NO se incluyen en la migración 2026-04-24_01.

---

## 4. Algoritmo runtime

### 4.1 Capa 1 — Ajustar pesos del scoring

Extensión del scoring engine de RF-04 §11 / RF-06:

```python
def score_disco(disco, pj, team_context: list[int] = None):
    pesos_pos = get_pesos_positivos_arquetipo(pj)   # default
    pesos_neg = get_pesos_perjudiciales_arquetipo(pj)

    # Override Capa 1: aplica modificadores de cada compañero
    if team_context:
        for compañero_id in team_context:
            sinergia = get_team_synergy(pj.id, compañero_id)
            if sinergia and sinergia.pesos_substat_override:
                for sub, peso_mod in sinergia.pesos_substat_override.items():
                    pesos_pos[sub] = peso_mod  # merge: el override gana

    # Resto idéntico a RF-06 §5.1
    score = sum(...)
    return score
```

Si hay 2 compañeros y ambos tienen overrides para el mismo substat, gana el último aplicado por orden de `confianza` descendente (la IA reporta confianza → se respeta).

### 4.2 Capa 2 — Override del set primario

Extensión de la fase 2 (bonus pass) del optimizador:

```python
def get_set_recomendado(pj, team_context):
    sets_base = [s for s in disc_set_archetype if pertenece_a_arquetipo(s, pj.arquetipo)]

    if team_context:
        # Buscar overrides
        for compañero_id in team_context:
            sinergia = get_team_synergy(pj.id, compañero_id)
            if sinergia and sinergia.set_recomendado_pj_a:
                # PJ_A es siempre el menor id; ajustar perspectiva
                set_override = sinergia.set_recomendado_pj_a if pj.id < compañero_id else sinergia.set_recomendado_pj_b
                if set_override:
                    sets_base.insert(0, set_override)  # prioridad máxima
    return sets_base
```

El bonus pass de RF-06 ahora prueba el set override **primero**; si su score combinado supera al del set "neutral por arquetipo", se selecciona.

### 4.3 Capa 3 — Sugerir equipos para un PJ

Esta capa es **lookup directo** de `team_compositions`:

```python
def suggest_teams(pj_id, contenido='shiyu_general', top_n=3):
    return db.query("""
        SELECT pj_companion_1_id, pj_companion_2_id, score_composicion, justificacion,
               sinergias_activadas
        FROM team_compositions
        WHERE pj_principal_id = ? AND contenido_optimo = ?
        ORDER BY rank_para_principal
        LIMIT ?
    """, (pj_id, contenido, top_n)).fetchall()
```

Si la tabla está vacía o stale, dispara on-demand una llamada IA para poblar/refrescar.

### 4.4 Integración con RF-06

Cuando `app/core/optimizer.py` recibe un PJ + `team_context` opcional:

1. Si `team_context` está vacío → comportamiento RF-06 puro.
2. Si `team_context` viene → llama `get_team_synergy(pj_id, c_id)` para cada compañero antes de scorear discos. Aplica capas 1 y 2.
3. UI permite togglear: "Build neutra" vs "Build con equipo: [Yanagi, Astra Yao]".

---

## 5. Prompt template — Claude API catalogador

### 5.1 Operación `team_synergy_pair`

Sistema prompt fijo + user prompt parametrizado.

**System prompt** (carga ~2k tokens, cachéable con prompt caching de Claude API):

```
Eres un experto analista de Zenless Zone Zero (ZZZ). Tu tarea es catalogar
sinergias entre pares de personajes para un sistema interno que optimiza
builds de discos. Respondes SIEMPRE en JSON estricto que cumple el schema
provisto. NO razonas en texto libre fuera del JSON. Cuando no estés seguro,
reportas confianza < 0.5 y explicitas qué falta verificar.

Conocimiento base que asumes verificado:
- Disorder se gatillea entre 2 anomalías de elementos distintos.
- Additional Abilities requieren 2 PJs de misma facción O 2 del mismo elemento.
- Sets como Puffer Electro escalan ATK%+ER, Tecno Pícido escala ATK% +
  damage por anomaly trigger, Polar Metal es Ice DMG puro.
- Awakenings son buffs aditivos que pueden cambiar la build óptima.

Cuando proponés un set_recomendado override, justificás en buff_descripcion
con la mecánica concreta (no decís "es mejor", decís POR QUÉ).
```

**User prompt** (parametrizado):

```
Analiza la sinergia entre {PJ_A.nombre} y {PJ_B.nombre} en un equipo de 3
PJs (donde el tercero es flexible y no se considera).

═══ DATOS PJ_A: {PJ_A.nombre} ═══
- Elemento: {PJ_A.elemento}
- Rol: {PJ_A.rol}
- Facción: {PJ_A.faccion}
- Mindscape: {PJ_A.mindscape}
- Awakenings activos: {PJ_A.awakenings_resumen}
- Stats relevantes actuales: {PJ_A.stats_resumen}
- Build equipada actual: set_4p={...}, set_2p={...}, mains={...}

═══ DATOS PJ_B: {PJ_B.nombre} ═══
[idéntica estructura]

═══ SETS DISPONIBLES RELEVANTES ═══
{lista_filtrada_de_sets_con_bonus_2pc_y_4pc}

═══ ARQUETIPOS PJ_A ═══
{disc_set_archetype del rol de PJ_A: primario y secundario}

═══ ARQUETIPOS PJ_B ═══
[idem]

═══ FUENTES OPCIONALES (RAG) ═══
{snippets de Prydwen.gg para PJ_A y PJ_B, max 1500 tokens cada uno}

Responde con este JSON exactamente:

{
  "sinergia_existe": <bool>,
  "tipo": "<disorder_elemento | additional_ability_faccion | set_override | buff_pasivo | rotation_specific | ninguna>",
  "set_recomendado_pj_a": <int set_id | null>,
  "set_recomendado_pj_b": <int set_id | null>,
  "pesos_substat_override_pj_a": {<substat>: <peso 0.0-1.0 o negativo>, ...} | {},
  "pesos_substat_override_pj_b": {...} | {},
  "buff_descripcion": "<máx 200 chars, mecánica concreta>",
  "confianza": <0.0-1.0>,
  "fuentes_consultadas": ["prydwen_pj_a", "knowledge_base", ...],
  "verificacion_requerida": "<si confianza<0.7, qué dato falta validar>"
}
```

### 5.2 Operación `team_composition_topN`

Para Capa 3. Input: 1 PJ principal + roster completo + tipo de contenido. Output: top 3-5 composiciones con justificación.

```
Dado el PJ principal {PJ_X.nombre} ({elemento}/{rol}/{faccion}) y el roster
disponible {lista_44_PJs}, propón las 3 mejores composiciones de equipo
para contenido {contenido_optimo: shiyu_general | shiyu_elite | deadly_assault | exploracion}.

Restricciones:
- 1 DPS (PJ_X), 1 Stunner o Anomaly secundario, 1 Soporte/Defensa
- Considerar sinergias previamente catalogadas en tabla team_synergies (snippet adjunto)
- Reglas anti-shill conocidas: {snippet_anti_shill_v2.6}

Output JSON array de 3 entradas:
[
  {
    "rank": 1,
    "pj_companion_1": <id>,
    "pj_companion_2": <id>,
    "score": <0.0-1.0>,
    "justificacion": "<máx 300 chars>",
    "sinergias_activadas": [<team_synergies.id>, ...],
    "requiere_stunner": <bool>,
    "flag_anti_shill": "<string | null>",
    "confianza": <0.0-1.0>
  },
  ...
]
```

### 5.3 Validación post-IA

Cada response pasa por validador:

```python
def validate_synergy_response(json_str, pj_a_id, pj_b_id):
    data = json.loads(json_str)  # falla → reintento con temperature=0
    assert data['sinergia_existe'] in [True, False]
    assert data['tipo'] in VALID_TIPOS
    if data['set_recomendado_pj_a']:
        assert db.exists('disc_sets', id=data['set_recomendado_pj_a'])
    # ... más asserts
    return data
```

Si falla validación 2 veces → guardar en `ai_catalog_runs` con `exito=0` y dejar el par sin entrada en `team_synergies` (algoritmo runtime cae a comportamiento RF-06 puro).

---

## 6. Trigger y refresh

### 6.1 Refresh on-demand

UI: botón **"Refrescar sinergias del equipo"** en `app/ui/settings_view.py` → Avanzado. Acciones:

1. Re-corre `team_synergy_pair` para todos los pares con `fecha_generado < hoy − 30 días`.
2. Re-corre `team_composition_topN` para los 15 PJs DPS-core de Daniel.
3. Estimación de costo: ~50-100 calls × ~$0.015 cada = **$1-1.50 USD por refresh completo** (con sonnet, sin opus).

### 6.2 Refresh automático al cargar PJ/set nuevo

Trigger: detección de INSERT en `agents` o `disc_sets`.

```python
# en app/core/repositories.py
def on_agent_inserted(agent_id):
    # Disparar pasada IA para los 44 pares (agent_id, otro_id)
    queue.enqueue('catalog_synergies_for_agent', agent_id)

def on_set_inserted(set_id):
    # Re-evaluar set_override en pares donde aplique
    queue.enqueue('reevaluate_set_overrides', set_id)
```

Worker queue corre en background con rate limit (1 call/s para no saturar API). Daniel ve un toast "Catalogando sinergias para {PJ}: 12/44".

### 6.3 Refresh manual selectivo

UI permite seleccionar 1 par específico y re-correr la IA (útil si Daniel quiere revisar un caso específico tras un nerf/buff de patch).

---

## 7. UI integración (RF-11)

### 7.1 Nueva pestaña "Equipos" en el panel de detalle

Añadida al panel de detalle de RF-11 (entre "Roster" y "Catálogos"):

- **Lista de PJs DPS-core** del roster.
- Por PJ seleccionado: top 3 equipos con barra de score, miembros, justificación y sinergias activadas.
- Click en un equipo → abre vista de "build con team_context": muestra cómo cambia la build óptima de cada miembro vs neutro.
- Botón "Optimizar este equipo entero" → corre RF-06 con `team_context` para los 3 PJs simultáneamente.

### 7.2 Toggle en el optimizador del PJ

En `app/ui/build_optimizer_view.py` (RF-06), añadir selector arriba:

```
[ Sin equipo ▼ ] [ + Yanagi ▼ ] [ + Astra Yao ▼ ]    [Optimizar build]
```

Defaults: si el PJ tiene composición principal en `team_compositions` rank 1 → preselecciona esos 2 compañeros.

### 7.3 Indicador de cobertura del catálogo

Badge en config: "Cobertura sinergias: 487/990 pares catalogados (49%)". Click → lista de pares pendientes con botón "Catalogar ahora".

---

## 8. Performance y costos

### 8.1 Latencia runtime (consumo del catálogo)

| Operación | Latencia objetivo |
|---|---|
| Lookup de 1 sinergia (`team_synergies` por par) | < 5 ms (índice) |
| Build con team_context (RF-06 + Capa 1+2) | < 600 ms (vs <500 ms sin context) |
| Sugerir equipos (lookup `team_compositions`) | < 50 ms |
| Optimizar equipo entero (3× RF-06 con context) | < 2 s |

### 8.2 Costos IA

Asumiendo Claude sonnet-4-6 a ~$3/$15 por MTok (input/output):

| Operación | Tokens promedio | Costo unitario | Frecuencia esperada | Costo mensual |
|---|---|---|---|---|
| `team_synergy_pair` | 4k input + 0.5k output | ~$0.02 | ~10/mes (nuevos PJs/sets) | $0.20 |
| `team_composition_topN` | 6k input + 1k output | ~$0.03 | ~20/mes (refresh DPS-core) | $0.60 |
| Refresh completo (manual) | 990 pairs × $0.02 + 60 × $0.03 = | **~$21** | 1×/trimestre | **~$7/mes** |

Total esperado: **< $10 USD/mes** en uso normal. Cap configurable en config.toml: `ai_monthly_budget_usd = 15.0` → corta llamadas si se excede.

### 8.3 Caching estratégico

- **Prompt caching** de Claude API: el system prompt + datos seed del juego se cachean → ahorro ~50% input tokens.
- **Response cache local**: `ai_catalog_runs.prompt_hash` permite detectar prompts idénticos en una ventana de N días → reutiliza response sin llamar API.

---

## 9. Output de ejemplo

### 9.1 Sinergia individual catalogada

```json
{
  "pj_a_id": 4,    // Ellen
  "pj_b_id": 38,   // Dialyn
  "sinergia_existe": true,
  "tipo": "rotation_specific",
  "set_recomendado_pj_a": 40,   // Puffer Electro
  "set_recomendado_pj_b": null,
  "pesos_substat_override_pj_a": {
    "Recarga de Energía": 0.8,
    "ATK%": 1.0,
    "Bono Daño Hielo": 0.9
  },
  "pesos_substat_override_pj_b": {},
  "buff_descripcion": "Dialyn dispara Ultimate adicional via core passive; Ellen necesita ER >1.6 para encadenar burst secundario. Puffer Electro provee ATK% + ER simultáneamente, superando Polar Metal en este contexto específico.",
  "confianza": 0.85,
  "fuente": "ai_claude",
  "modelo_version": "claude-opus-4-7",
  "fuentes_consultadas": ["prydwen_ellen_v2.6", "prydwen_dialyn_v2.5", "knowledge_base"]
}
```

### 9.2 Composición de equipo propuesta

```json
{
  "pj_principal_id": 4,         // Ellen
  "pj_companion_1_id": 38,      // Dialyn
  "pj_companion_2_id": 6,       // Lycaon (Stunner Hielo)
  "score_composicion": 0.92,
  "rank_para_principal": 1,
  "contenido_optimo": "shiyu_general",
  "justificacion": "Doble Hielo (Ellen + Lycaon) para Polar Metal aplicable; Dialyn como subDPS con Ultimate adicional que extiende burst. Ellen swaps de set a Puffer Electro para optimizar rotación de ulti.",
  "sinergias_activadas": [127, 89],   // ids de team_synergies
  "requiere_stunner": false,           // Lycaon ya cumple ese rol
  "flag_anti_shill": null,
  "confianza": 0.88
}
```

---

## 10. Estado y dependencias

### 10.1 Diseño cerrado (abril 2026)
- ✅ Alcance las 3 capas
- ✅ Schema SQL diseñado (3 tablas nuevas)
- ✅ Prompt templates definidos
- ✅ Estimación de costos < $10/mes
- ✅ Ejemplo Ellen+Dialyn validado conceptualmente

### 10.2 Pendiente para implementación
- 📋 Migración `2026-04-XX_03_team_synergies_ai_catalog.sql`
- 📋 Cliente Claude API en `app/core/ai_catalog.py`
- 📋 Validador de responses en `app/core/ai_validators.py`
- 📋 Worker queue para catalogación background
- 📋 Extensión de `app/core/scoring.py` con team_context
- 📋 Extensión de `app/core/optimizer.py` con Capa 1+2
- 📋 UI nueva pestaña "Equipos" en `app/ui/team_view.py`
- 📋 Toggle de team_context en `app/ui/build_optimizer_view.py`
- 📋 Carga inicial: catalogar 990 pares (~$21 una vez)

### 10.3 Diferido a v2
- Composiciones de equipo de 4+ PJs (cuando ZZZ extienda team size, si lo hace).
- Análisis de rotaciones específicas asistido por IA (entra en sección 9 del README, que es visión a futuro).
- Auto-update del catálogo tras patches del juego detectados via web scraping de Prydwen.
- Multi-modelo: comparar respuestas de Claude vs GPT vs local y consensuar.

---

## 11. Decisiones cerradas — log

| Fecha | Decisión | Alternativas evaluadas |
|---|---|---|
| 2026-04-25 | Las 3 capas (pesos + set override + sugerir equipo) | Sólo capas 1+2; sólo capa 3 |
| 2026-04-25 | IA catalogadora (no asesora en runtime) | Asesora cada llamada; híbrido |
| 2026-04-25 | Refresh on-demand + auto al cargar PJ/set nuevo | Solo manual; programado periódico |
| 2026-04-25 | Claude API (sonnet/opus) con RAG sobre Prydwen | GPT-4o; modelo local Ollama; híbrido |
| 2026-04-25 | Schema con `team_synergies` + `team_compositions` + `ai_catalog_runs` | Schema único; tablas separadas por capa |
| 2026-04-25 | Convención `pj_a_id < pj_b_id` en `team_synergies` | Pares no ordenados |
| 2026-04-25 | Cap mensual de costo IA configurable ($15 default) | Sin cap; cap por operación |
| 2026-04-25 | Prompt caching activo (system prompt + seed) | Sin cache (cada request fresh) |

---

*Cierre de diseño RF-12 — abril 2026*

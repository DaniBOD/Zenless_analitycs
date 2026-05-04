# RF-06 — Lógica del Optimizador de Build

**Versión:** 1.0 (abril 2026)
**Autor:** Daniel (DaniBOD)
**Refs:**
- `README.md` §3.1 RF-06 (descripción corta)
- `db/migrations/2026-04-24_01_archetypes_and_scoring.sql` (schema base)
- `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` §11 (scoring engine compartido)

---

## 1. Objetivo

Dado un personaje del roster, responder con un score numérico cuál es la **mejor combinación de 6 discos** que el inventario actual permite armarle, considerando:

- Set bonus 2pc / 4pc / 2+2+2 / 3+3 (mix)
- Mainstat objetivo por slot según rol y arquetipo del PJ
- Substats positivos (ponderados por rolls) y substats perjudiciales (penalizan)
- Nivel actual de cada disco (boost de 0 a 15)
- Discos actualmente equipados en otros PJs (con la posibilidad de "swap entre PJs")

El optimizador es la pieza que cierra la cadena captura → evaluación → recomendación → **acción concreta de equipamiento**. Su output alimenta tanto el dashboard del RF-11 como las notificaciones automáticas cuando entra un disco que mueve la frontera de optimalidad.

---

## 2. Alcance de la versión 1

### 2.1 Decisiones cerradas (abril 2026)

| Pregunta | Respuesta v1 |
|---|---|
| **Alcance** | Build completa desde cero (los 6 slots). Swap individual se deriva como caso particular. |
| **Exclusividad** | Permite proponer discos equipados en otros PJs, etiquetados como "swap entre PJs", mostrando el delta para ambos PJs. |
| **Algoritmo** | Greedy por slot + bonus pass para optimizar set bonus (4pc / 2+2+2 / 3+3). |
| **Trigger** | Manual desde el panel del PJ + automático cuando RF-04 captura un disco con score muy alto que potencialmente cambia la mejor build. |

### 2.2 Diferenciación con RF-04 §11 (evaluación de disco individual)

| | RF-04 §11 (evaluación) | RF-06 (optimizador) |
|---|---|---|
| **Pregunta que responde** | "¿Este disco que acabo de capturar sirve para alguien?" | "¿Cuál es la mejor build que puedo armarle a este PJ con todo lo que tengo?" |
| **Input** | 1 disco recién capturado | 1 PJ + todo el inventario |
| **Output** | Recomendación 4-vías (Equipar / Mejorar / Reservar / Descartar) | Top N builds completas con score y desglose |
| **Frecuencia** | Cada captura (trigger automático) | Bajo demanda + auto-trigger condicional |
| **Latencia objetivo** | < 500 ms | < 1 s |

Ambos comparten el `scoring_engine` (sección 5) — la única diferencia es la unidad evaluada (disco vs build de 6).

---

## 3. Modelo de datos consumido

### 3.1 Tablas de entrada

| Tabla | Rol |
|---|---|
| `agents` | PJ objetivo: id, nombre, rol, elemento, faccion |
| `inventory_discs` | Universo de búsqueda: 332 discos al cierre de Fase 1.5, crecerá con farmeo |
| `disc_sets` | Catálogo: bonuses 2pc/4pc por set |
| `disc_archetypes` | 6 arquetipos con pesos JSON positivos/perjudiciales |
| `disc_set_archetype` | Set ↔ arquetipo (primario/secundario) — sirve para validar afinidad disco-PJ |
| `agent_substat_preferences` | Override de pesos por PJ (vacío al inicio, se llena con seed Prydwen) |
| `agent_score_thresholds` | Cortes `threshold_equip` / `threshold_upgrade` por PJ |
| `agent_thresholds` | Stats finales objetivo del PJ (CRIT, ATK, ER, etc.) — se usan para verificar viabilidad de build |
| `agent_discs` | Build actual del PJ (baseline para calcular delta) |
| `weapons` | W-Engine equipada del PJ — afecta stats finales proyectados |

### 3.2 Tabla de salida

`inventory_disc_evaluations` se reutiliza para registrar la build óptima propuesta:

```sql
INSERT INTO inventory_disc_evaluations (
    inventory_disc_id, fecha, trigger_evento, recomendacion, score, detalle_json
) VALUES (
    NULL,                  -- al ser build (6 discos), se inserta una fila por disco propuesto
    CURRENT_TIMESTAMP,
    'optimizar_build',     -- nuevo trigger
    'build_propuesta',
    <score_total_build>,
    '{"build_id": "...", "pj_id": ..., "rank": 1, "discos": [...], "set_bonus": "4pc Jazz", "swap_chain": [...]}'
);
```

Como una build son 6 discos, se inserta una fila por disco con un `build_id` UUID compartido en el JSON, permitiendo reconstruir la build completa por agrupación.

---

## 4. Algoritmo: Greedy por slot + bonus pass

### 4.1 Fase 1 — Greedy local por slot

Para cada uno de los 6 slots:

```
mejores_por_slot[slot] = ordenar_por_score(
    [d for d in inventory_discs
     if d.slot == slot
        and main_compatible(d.main_stat, pj.arquetipo, slot)],
    desc
)[:K]   # K = top 10 candidatos por slot
```

`main_compatible(main, arquetipo, slot)`:
- Slot 1, 2, 3 → main fijo en el juego (HP plana, ATK plana, DEF plana). Filtro trivial.
- Slot 4, 5, 6 → consultar `disc_archetypes.mains_4 / mains_5 / mains_6` del arquetipo primario del PJ. El main del disco debe estar en esa lista. Tolerancia: si el main está en la lista del arquetipo secundario del set, se acepta con factor 0.7.

`score(d, pj)`:

```
score = Σ(peso_substat[sub_i] × (1 + rolls_i × 0.25))    # positivos crecen con rolls
      − Σ(|peso_perjudicial[sub_j]| × (1 + rolls_j × 0.5))  # perjudiciales penalizan más con rolls
      + bonus_main_arquetipo(d.main_stat, pj.arquetipo, slot)
      + bonus_nivel(d.nivel)         # +0.1 por cada level/3 hasta +0.5 a nivel 15
```

`peso_substat` se obtiene de `agent_substat_preferences[pj.id, sub_i]` si existe; si no, cae al peso del `disc_archetypes.substats_positivos` del arquetipo primario del PJ.

### 4.2 Fase 2 — Bonus pass: optimizar set bonus

El greedy local no garantiza el mejor set bonus combinado. El bonus pass evalúa las opciones de set:

```
opciones_set = [
    "4pc puro (slots 1-2-3-4 mismo set X)",
    "4pc puro (slots 1-2-5-6 mismo set X)",
    ... todas las particiones de 4 slots ...
    "2+2+2 (3 sets distintos, 2 slots cada uno)",
    "3+3 (sin 4pc, dos sets con 2pc cada uno + 2 slots adicionales sin bono)"  # casos como Manato
]
```

Por cada opción de set:
1. Calcular el "mejor 4pc / mejor 2+2+2" combinando los top-K de cada slot.
2. Sumar al score de los discos: `bonus_set_4pc(set_id, pj.arquetipo)` (peso configurable, default +1.5 si el set es primario del arquetipo, +0.7 si secundario, 0 si no pertenece).
3. Para 2pc se suma `bonus_set_2pc(set_id, pj.arquetipo)` por cada par activo (típicamente +0.4 si primario, +0.2 si secundario).

La build ganadora es la de mayor `score_total = Σ(score_disco_i) + bonus_set_combinado`.

### 4.3 Fase 3 — Top N builds y swap chains

El optimizador devuelve **las top 3 builds** (configurable) con su desglose, no sólo la #1. Esto le permite a Daniel ver alternativas con tradeoffs distintos (ej. "build A es +5% score pero exige robar 2 discos a Burnice; build B es −3% score sin afectar a nadie").

Para cada disco propuesto que ya esté equipado en otro PJ, se calcula:

```
swap_delta = {
  "pj_origen": {"id": ..., "score_actual": S_old, "score_sin_disco": S_new, "perdida": S_old − S_new},
  "pj_destino": {"id": pj.id, "score_sin_disco": T_old, "score_con_disco": T_new, "ganancia": T_new − T_old}
}
swap_neto = swap_delta.pj_destino.ganancia − swap_delta.pj_origen.perdida
```

Sólo se proponen swaps con `swap_neto > 0`. Se respeta una flag `agents.protected_build` (configurable por PJ en `user_config.toml`) para builds "sagradas" que el optimizador no debe tocar.

### 4.4 Cadenas de swap simples

V1 soporta cadenas de longitud 1 (PJ A → PJ B). Cadenas más largas (A → B → C) quedan diferidas a v2 — su frecuencia esperada es baja y la complejidad combinatoria explota.

---

## 5. Scoring engine compartido

El cálculo de `score(d, pj)` vive en `app/core/scoring.py` y es invocado tanto por:

- **RF-04 §11** — al evaluar 1 disco recién capturado contra el roster.
- **RF-06** — al rankear top-K candidatos por slot dentro del greedy.

Esta unificación garantiza que un disco que el evaluador marca como "Equipar en Miyabi" sea efectivamente el que el optimizador elegiría para Miyabi en el slot correspondiente. Cualquier divergencia es bug.

### 5.1 Fórmula canónica

```python
def score_disco(disco, pj):
    # 1. Pesos del PJ (override) o del arquetipo primario
    pesos_pos = get_pesos_positivos(pj)   # dict {substat: peso_+}
    pesos_neg = get_pesos_perjudiciales(pj)  # dict {substat: peso_-}

    # 2. Acumular por substat
    score = 0.0
    for sub, val, rolls in disco.substats:
        if sub in pesos_pos:
            score += pesos_pos[sub] * (1 + rolls * 0.25)
        if sub in pesos_neg:
            score -= abs(pesos_neg[sub]) * (1 + rolls * 0.5)

    # 3. Main del slot (slot 4-6)
    if disco.slot >= 4:
        score += bonus_main(disco.main_stat, pj, disco.slot)

    # 4. Nivel del disco (favorece discos ya levanteados)
    score += min(0.5, disco.nivel / 30)   # 0.0 → +0.5 a nivel 15

    return round(score, 3)
```

### 5.2 Normalización para comparar con thresholds

El score crudo no es comparable directamente con `agent_score_thresholds.threshold_equip` (default 0.75) porque el rango depende del arquetipo. Se normaliza así:

```python
score_norm = score / score_maximo_teorico_arquetipo(pj)
# threshold_equip = 0.75 → score normalizado debe ≥ 0.75
```

`score_maximo_teorico_arquetipo` se calcula al inicializar la app y se cachea: simula un disco "perfecto" con todos los positivos al máximo de rolls (5) y ningún perjudicial.

---

## 6. Triggers en la app

### 6.1 Manual

UI: botón **"Optimizar build"** en la vista del PJ del dashboard (`app/ui/roster_view.py` → al click abrir `app/ui/build_optimizer_view.py`).

Flujo:
1. Usuario selecciona PJ → click "Optimizar build".
2. Loading spinner (esperado <1 s para inventarios <500 discos).
3. Modal con tabs: **Build #1**, **#2**, **#3**, cada una con:
   - Diagrama hexagonal de los 6 slots (visual idéntico al juego).
   - Score total normalizado + barras por categoría (set bonus, mains, substats).
   - Lista de cambios vs build actual: discos a equipar, discos a desequipar, swaps con otros PJs.
   - Botón "Marcar como TODO" → registra la build en una nueva tabla `optimizer_pending_actions` (ver §7) para que Daniel ejecute los cambios manualmente en el juego.

### 6.2 Automático (re-evaluación tras captura)

Cuando RF-04 §11 evalúa un disco recién capturado y le asigna `recomendacion = 'equipar_pj_X'` con `score >= threshold_equip`:

1. Se dispara `recompute_best_build(pj_X)` en background (worker thread Qt).
2. Si la mejor build cambió respecto a la cacheada anterior:
   - El toast del RF-11 muestra **"⚡ Nueva mejor build para PJ X disponible"** además de la recomendación de equipar.
   - Click en el toast → abre directamente la vista del optimizador en la build #1.
3. Si no cambió: silencioso, la recomendación normal del disco se mantiene.

Para evitar re-cálculos costosos por cada disco capturado, se usa un debounce de 2 s por PJ (si entran 5 discos en 2 s, sólo se recalcula una vez al final).

### 6.3 Manual masivo: "Optimizar todos los PJs"

Comando opcional en menú del dashboard. Itera por los 45 PJs y calcula la mejor build de cada uno. Útil cuando se carga inventario masivo (ej. tras una sesión de farmeo prolongada). Estimado: ~30-45 s para todo el roster con inventario actual.

---

## 7. Tabla nueva opcional: `optimizer_pending_actions`

Para soportar el flujo "marcar como TODO":

```sql
CREATE TABLE IF NOT EXISTS optimizer_pending_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_propuesta DATETIME DEFAULT CURRENT_TIMESTAMP,
    pj_id           INTEGER NOT NULL REFERENCES agents(id),
    build_id        TEXT NOT NULL,                    -- UUID compartido con inventory_disc_evaluations
    estado          TEXT NOT NULL DEFAULT 'pendiente', -- 'pendiente' | 'aplicada' | 'descartada'
    fecha_aplicada  DATETIME,
    score_propuesto REAL,
    score_actual_pj REAL,
    delta           REAL,
    notas           TEXT
);

CREATE INDEX IF NOT EXISTS idx_opa_pj_estado ON optimizer_pending_actions(pj_id, estado);
```

Cuando Daniel aplica la build en el juego, marca como `aplicada` desde el panel; el sistema espera la siguiente captura de RF-04 (cambio de equipamiento) para confirmar que efectivamente se realizó y limpia el TODO.

Esta tabla se crea en migración separada `2026-04-XX_02_optimizer_pending.sql` cuando se implemente RF-06 — no en la migración 2026-04-24_01.

---

## 8. Performance y caching

### 8.1 Estimaciones

| Inventario | Greedy fase 1 | Bonus pass fase 2 | Total |
|---|---|---|---|
| 332 discos (actual) | ~50 ms | ~80 ms | ~130 ms |
| 1000 discos | ~150 ms | ~250 ms | ~400 ms |
| 1500 discos (cap juego) | ~220 ms | ~380 ms | ~600 ms |

### 8.2 Cache estratégico

- **Por PJ**: `cache_best_build[pj_id] = {build, score, fecha_calculo, hash_inventario}`. Se invalida si `hash_inventario` cambia (cualquier UPSERT en `inventory_discs` de un disco compatible con el PJ).
- **Substats preferences**: cargadas a memoria al arrancar la app (~45 PJs × ~10 substats = 450 entradas, despreciable).
- **Score máximo teórico por arquetipo**: cacheado al arranque, recalculado sólo si cambia `disc_archetypes`.

### 8.3 Concurrencia

El optimizador corre en `QThread` separado del UI principal para no bloquear el dashboard. Resultado se entrega vía `Signal` Qt al hilo UI.

---

## 9. Output de ejemplo

```json
{
  "pj_id": 5,
  "pj_nombre": "Miyabi",
  "fecha": "2026-04-25T01:23:45",
  "score_actual_pj": 0.68,
  "builds": [
    {
      "rank": 1,
      "build_id": "b3f2a1...",
      "score_total": 0.91,
      "set_bonus_aplicado": "4pc Balada rama/espada + 2pc Tecno Pícido",
      "discos": [
        {"slot": 1, "disc_id": 145, "set": "Balada rama/espada", "main": "HP", "score_disco": 0.78,
         "swap_origen": null},
        {"slot": 2, "disc_id": 222, "set": "Balada rama/espada", "main": "ATK", "score_disco": 0.82,
         "swap_origen": null},
        {"slot": 3, "disc_id": 89,  "set": "Balada rama/espada", "main": "DEF", "score_disco": 0.65,
         "swap_origen": {"pj_id": 12, "pj_nombre": "Yanagi", "delta_origen": -0.08}},
        {"slot": 4, "disc_id": 301, "set": "Balada rama/espada", "main": "Prob. Crítica", "score_disco": 0.95,
         "swap_origen": null},
        {"slot": 5, "disc_id": 178, "set": "Tecno Pícido",       "main": "Bono Daño Hielo", "score_disco": 0.88,
         "swap_origen": null},
        {"slot": 6, "disc_id": 256, "set": "Tecno Pícido",       "main": "ATK%", "score_disco": 0.74,
         "swap_origen": null}
      ],
      "swaps_requeridos": [
        {"pj_origen_id": 12, "disc_id": 89, "delta_origen": -0.08, "delta_destino": +0.18, "neto": +0.10}
      ],
      "delta_vs_actual": +0.23
    },
    { "rank": 2, "...": "..." },
    { "rank": 3, "...": "..." }
  ]
}
```

---

## 10. Estado y dependencias

### 10.1 Cumplido
- ✅ Schema base: migración `2026-04-24_01_archetypes_and_scoring.sql` aplicada (6 arquetipos, 26 sets clasificados, 45 thresholds default).
- ✅ Inventario completo: 332 discos cargados (RF-02).
- ✅ Diseño cerrado: este documento.

### 10.2 Pendiente para implementación
- 📋 Seed de `agent_substat_preferences` desde Prydwen.gg (45 PJs × ~5 substats relevantes = ~225 filas).
- 📋 Migración `2026-04-XX_02_optimizer_pending.sql` (tabla `optimizer_pending_actions`).
- 📋 Código `app/core/scoring.py` (engine compartido con RF-04 §11).
- 📋 Código `app/core/optimizer.py` (greedy + bonus pass).
- 📋 UI `app/ui/build_optimizer_view.py` (modal con tabs por build).
- 📋 Integración con RF-04 (auto-trigger tras captura).

### 10.3 Diferido a v2
- Cadenas de swap longitud > 1.
- Optimizador multi-PJ (resolver conflictos cuando 2 PJs quieren el mismo disco).
- Algoritmo MILP para validación de optimalidad (sólo si el greedy da resultados subóptimos en práctica).
- Predicción de discos a farmear: "qué slot/set más te conviene rollear esta semana".

---

## 11. Decisiones cerradas — log

| Fecha | Decisión | Alternativas evaluadas |
|---|---|---|
| 2026-04-25 | Build completa desde cero como modo principal | Sólo swap individual; ambos toggle |
| 2026-04-25 | Swap entre PJs habilitado con delta dual | Solo discos libres; configurable por PJ |
| 2026-04-25 | Greedy + bonus pass v1 | Exhaustivo; MILP; SA/genético |
| 2026-04-25 | Trigger manual + auto post-captura con debounce 2s | Solo manual; programado diario |
| 2026-04-25 | Top 3 builds en output (no sólo #1) | Top 1; top 5; configurable |
| 2026-04-25 | Cadenas de swap longitud 1 en v1 | Longitud arbitraria |
| 2026-04-25 | Tabla `optimizer_pending_actions` separada en nueva migración | Reutilizar `inventory_disc_evaluations` con trigger especial |

---

*Cierre de diseño RF-06 — abril 2026*

# Roadmap — Motor de Captura + Scoring (Fase 2)

> **Alcance:** RF-04 (sync captura discos) · RF-05 (sync upgrade) · RF-06 (optimizador build) · RF-09 (OCR híbrido). Cierra el "primer hito de codeo del .exe" (project-context-IA §10).
>
> **Precondición arquitectónica:** Fase 1 cerrada — DB con 31 tablas, 5 migraciones aplicadas, integrity OK, 332 discos cargados, 45 PJs, 6 arquetipos, 26 sets clasificados. Lo que falta es el **motor**.
>
> **Documento canónico de referencia para cada decisión técnica:** `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` + `Documentacion/RF_Optimizador/RF-Logic_Optimizador_Build.md`. Si este roadmap discrepa con esos docs, **mandan los docs RF**.
>
> **Última actualización:** 2026-05-03

---

## 0. Objetivo y filosofía del roadmap

Llevar el sistema desde "DB completa, 0 código del .exe" hasta:

1. **Re-estandarización** del inventario actual (saneamiento ETL — bloquea todo lo demás).
2. **Onboarding del PJ nuevo** que el usuario obtuvo (extender roster a 46).
3. **Scoring engine puro determinista** corriendo sobre la DB ya saneada (sin OCR, sin UI).
4. **Primer pase de scoring batch** sobre los 332 discos del inventario → poblar `inventory_disc_evaluations` y `inventory_discs.score_evaluacion`.
5. **Capa OCR + detector** activa sobre la ventana del juego.
6. **Sync RF-04/05** persistiendo capturas en vivo + invocando scoring.
7. **Optimizador RF-06** (greedy + bonus pass + top-3 builds).

**Principio rector:** cada fase entrega valor verificable de forma aislada. No se empieza la siguiente sin cerrar los criterios de aceptación de la anterior. Cualquier hallazgo que requiera revisar diseño se eleva al doc RF correspondiente, no se parchea en código.

**Reglas no negociables que aplican a todas las fases:**

- **RNF-01 ETL sin fallas** — toda manipulación de DB con backup previo + transacción + `PRAGMA foreign_key_check` + `PRAGMA integrity_check`. Logs en `audit/`.
- **RNF-02 Análisis minucioso** — cero shortcuts. Dato no confirmado ⇒ NULL + flag tentativo. Fuentes autorizadas: Prydwen, HoYoLAB, Game8, IcyVeins, 141store, Fandom.
- **RNF-03 ToS HoYoverse** — solo pixels en pantalla. Cero lectura de memoria, cero inyección.
- **RNF-06 Latencia** — pipeline disco → toast < 500 ms (P95).

---

## 1. Estado actual verificado (snapshot 2026-05-03)

### 1.1 Lo que está listo

| Capa | Estado | Detalle |
|------|--------|---------|
| Schema DB | ✅ | 31 tablas, 5 migraciones, 0 FK violations |
| Roster | ✅ | 45 PJs cargados con stats efectivos |
| Inventario discos | ✅ estructural | 332 discos (257 equipados + 75 sueltos) — pero con inconsistencias de tipo (§1.2) |
| Inventario armas | ✅ | 50 (40 equipadas + 10 sueltas) |
| Catálogo arquetipos | ✅ | 6 arquetipos con pesos JSON |
| Mapeo set ↔ arquetipo | ✅ | 34 filas (26 sets, primario/secundario) — cobertura 100% |
| Score thresholds | ✅ | 45/45 PJs con defaults 0.75/0.50 |
| Awakenings | 🟡 | 5 filas (1 verificado + 4 placeholder, 2 PJs sin insertar) |
| Diseño RF-04/05/06/09 | ✅ | Cerrado — docs canónicos referenciados arriba |
| App scaffold (`app/`) | ❌ | No existe |

### 1.2 Hallazgos críticos detectados al inspeccionar la DB (2026-05-03)

**Estos hallazgos justifican que la Fase 2.0 sea ETL de saneamiento, no implementación directa.**

1. **`inventory_discs.val1-val4` con tipos mixtos** — 149 filas guardan el valor como TEXT (`'7.2%'`), 183 como REAL. La columna está declarada `REAL` pero SQLite acepta tipos dinámicos, así que pasaron strings sin error. Esto **rompe el scoring** en cuanto se intente sumar pesos numéricos.
2. **Nomenclatura inconsistente entre tablas:**
   - `inventory_discs` usa: `'PV'`, `'Ataque'`, `'Defensa'`, `'Prob Crítico'`, `'Maestría Anomalía'`, `'Perforación'`.
   - `disc_archetypes.substats_positivos` (canon RF-04 §7.2.1) usa: `'HP'`, `'ATK'`, `'DEF'`, `'Prob. Crítica'` (con punto), `'Daño Crítico'`, `'Maestría de Anomalía'`, `'Perforación'`.
   - **Bloquea el JOIN funcional entre disco y peso de arquetipo.** El scoring va a fallar silenciosamente.
3. **`agent_substat_preferences` vacío** (0 filas). El scoring puede usar el fallback al arquetipo del PJ, pero sin overrides per-PJ los rankings van a ser homogéneos por rol.
4. **332 discos con `score_evaluacion = NULL`** — esperable (el motor todavía no corrió), pero queda como criterio de aceptación de la Fase 2.3.
5. **Sin distinguir % de flat en main/sub:** `'ATK 38'` (flat) vs `'ATK% 3%'` (porcentaje) hoy se diferencian solo por sufijo en el nombre. El scoring necesita columnas o convención clara.

---

## 2. Fase 2.0 — ETL de saneamiento (BLOQUEA TODAS LAS DEMÁS)

> **Por qué primero:** sin DB consistente cualquier scoring va a dar números mentirosos y el bug va a quedar enterrado en lógica de Python. Saneamos en SQL primero, validamos con assertions, después implementamos.

### Hito 2.0.1 · Auditoría completa de `inventory_discs`

**Output:** `audit/inventory_discs_audit_YYYYMMDD.md` con:
- Distribución de tipos por columna `val1-4`.
- Inventario de strings únicos en `main_stat`, `sub1-4` (nomenclatura observada vs canónica).
- Filas con valores fuera de rangos válidos (ej. `rolls > 5`, `nivel > 15`).
- Filas con FK rota a `disc_sets` o `agents`.
- Filas con `main_stat` no permitido por slot (ej. `'HP%'` en slot 1 que es flat fijo).

**Archivo:** `app/scripts/audit_inventory_discs.py`. Solo lectura. No modifica nada.

**Aceptación:** reporte generado, revisado por usuario, firmado.

### Hito 2.0.2 · Vocabulario canónico de stats

**Archivo:** `app/core/stats_vocab.py`. Define:

```python
# Substats válidos (los 10 reales en ZZZ — RF-04 §7.2.1)
CANONICAL_SUBSTATS = {
    "HP", "HP%",
    "ATK", "ATK%",
    "DEF", "DEF%",
    "Prob. Crítica", "Daño Crítico",
    "Perforación",            # flat
    "Maestría de Anomalía",
}

# Mains válidos por slot (slots 1-3 fijos, 4-6 variables)
CANONICAL_MAINS_FIXED = {1: "HP", 2: "ATK", 3: "DEF"}
CANONICAL_MAINS_VARIABLE = {
    4: {"Prob. Crítica", "Daño Crítico", "Maestría de Anomalía",
        "HP%", "ATK%", "DEF%", "Tasa de Perforación"},
    5: {"Bono Daño Físico", "Bono Daño Fuego", "Bono Daño Hielo",
        "Bono Daño Eléctrico", "Bono Daño Éter",
        "HP%", "ATK%", "DEF%", "Tasa de Perforación"},
    6: {"HP%", "ATK%", "DEF%", "Maestría de Anomalía",
        "Impacto", "Recarga de Energía"},
}

# Mapa de aliases observados → canónico
ALIASES = {
    "PV": "HP", "Pv": "HP", "Hp": "HP",
    "Ataque": "ATK", "Atk": "ATK", "ataque": "ATK",
    "Defensa": "DEF", "Def": "DEF",
    "Prob Crítico": "Prob. Crítica", "Prob Crítica": "Prob. Crítica",
    "CRIT Rate": "Prob. Crítica", "CR": "Prob. Crítica",
    "Crit DMG": "Daño Crítico", "Daño Crítico ": "Daño Crítico",
    "Maestría Anomalía": "Maestría de Anomalía",
    "Maestría Anom": "Maestría de Anomalía",
    "Anom": "Maestría de Anomalía",
    "ER": "Recarga de Energía",
    "Impact": "Impacto",
    # … completar con el catálogo del audit 2.0.1
}

def normalize_stat_name(raw: str) -> str | None:
    """Devuelve el nombre canónico, o None si es desconocido."""
    raw = (raw or "").strip()
    if raw in CANONICAL_SUBSTATS or raw in {m for s in CANONICAL_MAINS_VARIABLE.values() for m in s}:
        return raw
    return ALIASES.get(raw)

def parse_value(raw: str | float | int) -> tuple[float, str]:
    """
    'ATK%' → ('Prob. Crítica', '7.2%') → (7.2, '%').
    'ATK'  → ('ATK', 38)              → (38.0, 'flat').
    """
    if isinstance(raw, (int, float)):
        return float(raw), "flat"
    s = str(raw).strip().replace(" ", "")
    if s.endswith("%"):
        return float(s[:-1]), "%"
    return float(s), "flat"
```

**Cobertura mínima:** todos los strings observados en el audit 2.0.1 deben mapear a un canónico o quedar listados explícitamente como "no-stat" (ej. ruido OCR).

**Aceptación:** test unitario en `app/tests/unit/test_stats_vocab.py` que tome los 332 discos y muestre `0 unknowns`.

### Hito 2.0.3 · Migración 06 — normalizar `inventory_discs`

**Archivo:** `db/migrations/2026-05-XX_06_normalize_inventory_discs.sql`.

```sql
-- Backup explícito antes de aplicar
-- (script wrapper hace el cp del .db a backup_premig_TIMESTAMP)

BEGIN TRANSACTION;

-- 1. Agregar columna `unidad` por substat para distinguir % vs flat
ALTER TABLE inventory_discs ADD COLUMN unidad1 TEXT CHECK(unidad1 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad2 TEXT CHECK(unidad2 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad3 TEXT CHECK(unidad3 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad4 TEXT CHECK(unidad4 IN ('flat','%'));
ALTER TABLE inventory_discs ADD COLUMN unidad_main TEXT CHECK(unidad_main IN ('flat','%'));

-- 2. (En script Python siguiente) limpiar val1-4 y poblar unidad*

-- 3. Crear índices recomendados RF-04 §11.3 (si no existen)
CREATE INDEX IF NOT EXISTS idx_inv_set_slot       ON inventory_discs(set_id, slot);
CREATE INDEX IF NOT EXISTS idx_inv_agente         ON inventory_discs(agente_asignado);
CREATE INDEX IF NOT EXISTS idx_inv_pending        ON inventory_discs(descartado, equipado) WHERE descartado = 0;
CREATE INDEX IF NOT EXISTS idx_agent_discs_lookup ON agent_discs(set_id, slot, main_stat);

COMMIT;

-- Validación
PRAGMA foreign_key_check;
PRAGMA integrity_check;
```

**Decisión técnica:** SQLite no permite cambiar el tipo de columna. Mantenemos `val1-4` (acepta TEXT y REAL) pero en la **siguiente migración 07** los rebakeamos como REAL después de normalizar todos los valores en el script 2.0.4.

### Hito 2.0.4 · Re-estandarización de los 332 discos (más los nuevos capturados)

**Archivo:** `app/scripts/restandarize_inventory_discs.py`. Idempotente (correr varias veces no rompe nada).

Pseudo-código:

```python
import sqlite3, shutil, datetime
from app.core.stats_vocab import normalize_stat_name, parse_value

# 1. Backup
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy("db/danibod_zzz_v2.db", f"db/danibod_zzz_v2.backup_premig_{ts}.db")

# 2. Cargar todos los discos a memoria
con = sqlite3.connect("db/danibod_zzz_v2.db")
con.row_factory = sqlite3.Row
discs = list(con.execute("SELECT * FROM inventory_discs"))

# 3. Normalizar fila por fila
rejected = []
for d in discs:
    payload = {"id": d["id"]}
    valid = True
    # Main
    if d["main_stat"]:
        canon = normalize_stat_name(d["main_stat"])
        if canon is None:
            rejected.append((d["id"], "main_stat", d["main_stat"]))
            continue
        payload["main_stat"] = canon
        if d["main_valor"] is not None:
            v, u = parse_value(d["main_valor"])
            payload["main_valor"] = v
            payload["unidad_main"] = u
    # Subs
    for i in (1, 2, 3, 4):
        if d[f"sub{i}"]:
            canon = normalize_stat_name(d[f"sub{i}"])
            if canon is None:
                rejected.append((d["id"], f"sub{i}", d[f"sub{i}"]))
                continue
            payload[f"sub{i}"] = canon
            if d[f"val{i}"] is not None:
                v, u = parse_value(d[f"val{i}"])
                payload[f"val{i}"] = v
                payload[f"unidad{i}"] = u
    # Update
    cols = [k for k in payload if k != "id"]
    sql = f"UPDATE inventory_discs SET {', '.join(c+'=?' for c in cols)} WHERE id=?"
    con.execute(sql, [payload[c] for c in cols] + [payload["id"]])

con.commit()

# 4. Reportar y validar
print(f"Total discos procesados: {len(discs)}")
print(f"Filas con stats no canónicos: {len(rejected)}")
for r in rejected: print(r)

con.execute("PRAGMA foreign_key_check;")
con.execute("PRAGMA integrity_check;")
con.close()
```

**Aceptación:**
- 0 filas rechazadas (todos los stats mapean al canon).
- 332 filas con `unidad*` poblada donde corresponde.
- Backup `db/danibod_zzz_v2.backup_premig_YYYYMMDD_HHMMSS.db` archivado.
- Reporte `audit/restandarization_report_YYYYMMDD.md` firmado.

### Hito 2.0.5 · Seed `agent_substat_preferences` desde Prydwen

**Estrategia:** cargar primero los **5 PJs canónicos** del brief de Diseño (Yanagi, Ellen, Yixuan, Burnice, Caesar) + los **3 stunners principales** (Lycaon, Qingyi, Pulchra) + el **PJ nuevo** del usuario (cuando esté onboardeado en 2.0.6). Total inicial: **9 PJs × ~6 substats = ~54 filas**. El resto (45−9 = 36 PJs × 6 = 216 filas) cae al fallback de arquetipo, queda como deuda explícita resuelta en 2.0.5b.

**Archivo:** `app/scripts/seed_substat_preferences.py`.

Datos iniciales hardcodeados (subset; resto migrar después de scrapear Prydwen):

```python
PRYDWEN_SEED_INITIAL = {
    "Yanagi":  {"Maestría de Anomalía": 1.0, "ATK%": 0.8, "Prob. Crítica": 0.5,
                "ATK": 0.4, "Daño Crítico": -0.3, "DEF%": -0.6},
    "Ellen":   {"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.8,
                "ATK": 0.4, "Perforación": 0.5, "HP%": -0.4, "DEF%": -0.6},
    "Yixuan":  {"Daño Crítico": 1.0, "Prob. Crítica": 1.0, "HP%": 0.8, "HP": 0.4,
                "ATK%": -0.2, "DEF%": -0.5},
    "Burnice": {"Maestría de Anomalía": 1.0, "ATK%": 0.7, "Recarga de Energía": 0.6,
                "ATK": 0.4, "Prob. Crítica": -0.2, "Daño Crítico": -0.3, "DEF%": -0.6},
    "Caesar":  {"DEF%": 1.0, "DEF": 0.7, "HP%": 0.6, "HP": 0.3,
                "Impacto": 0.8, "Maestría de Anomalía": -0.5},
    # … resto se carga después
}
```

**Aceptación:**
- 9 PJs con preferencias cargadas con `fuente='prydwen'`.
- Test L1: `SELECT COUNT(*) FROM agent_substat_preferences WHERE fuente='prydwen' >= 54`.
- 36 PJs sin preferencias quedan listados como deuda en `audit/preferences_pendientes.md`.

#### Hito 2.0.5b — deuda explícita: cargar el resto de Prydwen

Diferida fuera del camino crítico. Puede ejecutarse en paralelo durante 2.2/2.3. Scraper en `app/scripts/scrape_prydwen_substat_priorities.py`. Output va a la misma tabla. Si el scraper falla por cambios de DOM, se cae a transcripción manual con plantilla CSV.

### Hito 2.0.6 · Onboarding del agente nuevo (8 pasos canónicos)

> Sigue **íntegramente** `Documentacion/Onboarding_Nuevo_PJ.md` §3-§12. Recapitulo el checklist mínimo:

1. INSERT en `agents` con stats efectivos del nuevo PJ (HoYoLAB screenshot ideal). Si no está aún equipado, usar M0 standard de Prydwen con flag `notas='M0 standard — actualizar'`.
2. `agent_thresholds` con thresholds del rol (default por arquetipo del rol).
3. `agent_score_thresholds` con defaults (0.75 / 0.50, `fuente='default'`).
4. `agent_awakenings` con placeholder `tipo_efecto='placeholder'`, `activo=0`, hasta tener texto in-game.
5. Determinar arquetipo (regla por rol con override manual si escala con HP).
6. Seed 6 filas en `pj_weapon_synergy` (matriz por rol).
7. Scrape Prydwen para weapons del PJ — `scrape_prydwen_weapons.py --pj <slug>`.
8. Splash art: agregar a `descargar_splash_arts.py` y re-ejecutar (idempotente).

**Más en este roadmap:**
- **Si el PJ nuevo ya tiene discos equipados in-game**, capturar su build manualmente (in-game screenshot + transcripción a `agent_discs`) hasta que la captura automática esté lista (Fase 2.5).
- **Catalogación IA de los 44 pares nuevos** (RF-12) queda **fuera del alcance de Fase 2** — diferida a Fase 3. En el ínterin el PJ no participa en optimizador de equipos.

**Aceptación:** ejecutar checklist post-onboarding del Onboarding §12:

```sql
SELECT COUNT(*) = 1 FROM agents WHERE nombre = ?;
SELECT COUNT(*) >= 1 FROM agent_thresholds WHERE agente_id = ?;
SELECT COUNT(*) = 1 FROM agent_score_thresholds WHERE agente_id = ?;
SELECT COUNT(*) = 6 FROM pj_weapon_synergy WHERE pj_id = ?;
PRAGMA foreign_key_check;
PRAGMA integrity_check;
```

**Pregunta abierta para el usuario antes de ejecutar 2.0.6:**

| # | Pregunta |
|---|----------|
| Q1 | ¿Quién es el agente nuevo? (nombre, elemento, rol, facción, M actual) |
| Q2 | ¿Ya lo tenés equipado? (afecta si cargamos stats reales o M0 standard) |
| Q3 | ¿Tenés screenshot HoYoLAB con sus stats efectivos? |
| Q4 | ¿En qué patch salió? (afecta `version_juego` en awakenings) |

### Hito 2.0.7 · Re-estandarización **incremental** de los discos capturados manualmente estos días

> El usuario mencionó que capturó algunos discos manualmente. La normalización 2.0.4 los toca igual, pero hay que verificar que estén en `inventory_discs` (no en otra tabla, no en archivo suelto).

**Tarea:** confirmar con el usuario dónde están esos discos:
- ¿Insertados directamente en `inventory_discs`? → 2.0.4 los normaliza.
- ¿En CSV / nota / spreadsheet aparte? → ETL ad-hoc de carga + 2.0.4.
- ¿En screenshots sin transcribir aún? → carga manual o esperar a Fase 2.5.

**Output:** `audit/discos_capturados_manualmente_session_<fecha>.md` con el inventario y su origen.

### Cierre Fase 2.0 — Criterios de aceptación

- [ ] Audit `inventory_discs` revisado y firmado.
- [ ] Vocabulario canónico publicado en `app/core/stats_vocab.py` con tests.
- [ ] Migración 06 aplicada con backup.
- [ ] 332+N discos normalizados sin filas rechazadas.
- [ ] 9 PJs con `agent_substat_preferences` cargados (5 brief + 3 stunners + 1 nuevo).
- [ ] PJ nuevo onboardeado con checklist §12 verde.
- [ ] `PRAGMA integrity_check` y `foreign_key_check` OK.
- [ ] `project-context-IA.md` §3 actualizado con nuevos counts.
- [ ] Commit en git con tag `phase-2.0-saneamiento-completo`.

---

## 3. Fase 2.1 — Scaffold `app/`

> Solo después de cerrar Fase 2.0. Aquí no se toca DB; solo estructura de proyecto + dependencias.

### Hito 2.1.1 · Estructura de carpetas

```
app/
├── __init__.py
├── main.py                            # entrypoint del .exe (placeholder por ahora)
├── config/
│   ├── defaults.toml                  # thresholds, paths, polling intervals
│   └── user_config.toml               # overrides del usuario (gitignored)
├── core/
│   ├── __init__.py
│   ├── stats_vocab.py                 # canon + aliases (creado en 2.0.2)
│   ├── scoring.py                     # 2.2
│   ├── recommender.py                 # 2.2
│   ├── score_normalizer.py            # 2.2
│   ├── ocr_backend.py                 # 2.4 — interfaz abstracta
│   ├── ocr_tesseract.py               # 2.4
│   ├── ocr_paddle.py                  # 2.4
│   ├── capturer.py                    # 2.4 — mss + crop ROI
│   ├── detector.py                    # 2.4 — clasificador estado pantalla
│   ├── parser_disc.py                 # 2.4 — texto OCR → DiscParsed
│   ├── monitor.py                     # 2.4 — polling adaptativo
│   ├── sync_equip.py                  # 2.5
│   ├── sync_upgrade.py                # 2.5
│   └── optimizer.py                   # 2.6
├── db/
│   ├── __init__.py
│   ├── connection.py                  # connection pool, foreign_keys ON
│   └── repositories.py                # repos read-only para core
├── scripts/
│   ├── audit_inventory_discs.py       # ya creado en 2.0.1
│   ├── restandarize_inventory_discs.py # ya creado en 2.0.4
│   ├── seed_substat_preferences.py    # ya creado en 2.0.5
│   └── score_existing_inventory.py    # 2.3
├── resources/
│   ├── templates/                     # anchors PNG para detector (S2, S5, S9, S10, S11)
│   └── icon.ico
└── tests/
    ├── __init__.py
    ├── conftest.py                    # fixture DB en memoria
    ├── fixtures/
    │   ├── golden_cases.json
    │   └── ocr_golden_set/            # 50 capturas con expected JSON
    ├── unit/
    │   ├── test_stats_vocab.py
    │   ├── test_scoring.py
    │   └── test_parser_disc.py
    ├── integration/
    │   ├── test_sync_equip.py
    │   └── test_optimizer.py
    └── regressions/
        └── test_golden_cases.py
```

### Hito 2.1.2 · `pyproject.toml` + dependencias

```toml
[project]
name = "danibod-zzz-analytics"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.7",        # UI (Fase 3)
    "mss>=9.0",            # screenshot
    "opencv-python>=4.10", # template matching
    "pytesseract>=0.3.13", # OCR texto
    "paddleocr>=2.8",      # OCR números (lazy load)
    "pynput>=1.7",         # hotkeys F8/F9/F10/F11
    "pywin32>=308",        # SetWinEventHook (foreground change)
    "anthropic>=0.34",     # IA RF-12 (Fase 3)
    "tomli>=2.0; python_version<'3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov",
    "pytest-benchmark",
    "ruff",
    "mypy",
]
```

### Hito 2.1.3 · `app/db/repositories.py` (read-only para core)

Patrón: una clase por tabla, métodos puros sobre `sqlite3.Connection` inyectada. Sin caching todavía. Sin escritura desde repos (los writes los hace `sync_*.py` con su propia transacción).

```python
# Esqueleto
class AgentRepo:
    def __init__(self, con): self.con = con
    def get_by_id(self, id: int) -> Agent | None: ...
    def get_by_nombre(self, nombre: str) -> Agent | None: ...
    def get_all(self) -> list[Agent]: ...
    def get_score_thresholds(self, id: int) -> tuple[float, float]: ...
    def get_substat_preferences(self, id: int) -> dict[str, float]: ...

class DiscArchetypeRepo: ...
class DiscSetRepo:
    def get_archetypes_for_set(self, set_id: int) -> list[(int, int)]: ...   # (arch_id, prioridad)
class InventoryDiscRepo:
    def get_pending(self) -> list[Disc]: ...
    def update_score(self, disc_id, score, agentes_compatibles, notas): ...
class EvaluationRepo:
    def insert_evaluation(self, disc_id, trigger, recomendacion, score, detalle_json): ...
```

### Hito 2.1.4 · `app/config/defaults.toml`

```toml
[paths]
db = "db/danibod_zzz_v2.db"

[scoring]
threshold_equip_default = 0.75
threshold_upgrade_default = 0.50
threshold_stock_default = 0.7
peso_main_arquetipo = 1.0
peso_set_4pc_primario = 1.5
peso_set_4pc_secundario = 0.7
peso_set_2pc_primario = 0.4
peso_set_2pc_secundario = 0.2
roll_multiplier_positivo = 0.25
roll_multiplier_perjudicial = 0.5
nivel_bonus_max = 0.5

[ocr]
backend_texto = "tesseract"        # tesseract | paddle
backend_numeros = "paddle"
confianza_minima = 0.7

[monitor]
polling_reposo_ms = 4000
polling_inventario_ms = 2000
polling_resultado_ms = 1000
polling_modal_ms = 500

[hotkeys]
captura_manual = "f8"
toggle_panel = "f9"
toggle_pausa = "f10"
registrar_run = "f11"
salir = "ctrl+shift+z"
```

### Cierre Fase 2.1 — Aceptación

- [ ] Estructura completa de carpetas creada.
- [ ] `pip install -e ".[dev]"` instala sin errores.
- [ ] `pytest` corre con 0 tests pero detecta la suite (sanity check).
- [ ] `defaults.toml` cargable desde Python.
- [ ] Commit con tag `phase-2.1-scaffold`.

---

## 4. Fase 2.2 — Scoring Engine puro

> Sin OCR ni UI. Función pura: `(disco, pj) → score, desglose`. Determinista. 100% testeable con DB en memoria.

### Hito 2.2.1 · `app/core/scoring.py`

Implementa la fórmula RF-04 §7.2.3 + RF-06 §5.1:

```python
def score_disco(disco: Disc, pj: Agent, ctx: ScoringContext) -> ScoreBreakdown:
    """
    Devuelve un objeto con score crudo + desglose para auditoría.

    ScoreBreakdown:
      score_raw: float
      score_norm: float           # crudo / score_max_arquetipo[pj.arquetipo]
      desglose: {
        set_match: 'primario' | 'secundario' | 'no_pertenece',
        set_match_score: float,
        main_match: 'exacta' | 'arquetipo' | 'no_match',
        main_match_score: float,
        substats_positivos: [{stat, val, rolls, peso, contribucion}],
        substats_perjudiciales: [{stat, val, rolls, peso, contribucion}],
        nivel_bonus: float,
        score_disco_disco: float,      # sin set bonus aplicado
      }
    """
    pesos_pos = pj.substat_preferences_positivos or arquetipo.substats_positivos
    pesos_neg = pj.substat_preferences_perjudiciales or arquetipo.substats_perjudiciales

    score = 0.0
    desg = ScoreBreakdown(...)

    # 1. Substats — usar nombres CANÓNICOS (ya garantizados por Fase 2.0)
    for sub_canon, val, unidad, rolls in disco.iter_substats():
        if sub_canon in pesos_pos:
            contrib = pesos_pos[sub_canon] * (1 + rolls * ctx.roll_mult_pos)
            score += contrib
        if sub_canon in pesos_neg:
            contrib = -abs(pesos_neg[sub_canon]) * (1 + rolls * ctx.roll_mult_neg)
            score += contrib

    # 2. Main (slot 4-6)
    if disco.slot >= 4 and disco.main_canon in pj.mains_validos_para_slot(disco.slot):
        score += ctx.peso_main_arquetipo

    # 3. Nivel
    score += min(ctx.nivel_bonus_max, disco.nivel / 30)

    # 4. Normalizar
    score_max = ctx.score_maximo_teorico(pj.arquetipo_primario)
    score_norm = score / score_max if score_max > 0 else 0

    return ScoreBreakdown(score_raw=score, score_norm=score_norm, desglose=desg)


def score_disco_arquetipo(disco: Disc, arquetipo: Archetype, ctx) -> float:
    """Mismo algoritmo pero usando los pesos del arquetipo (cuando ningún PJ alcanza threshold)."""
    ...
```

### Hito 2.2.2 · `app/core/score_normalizer.py`

Cachea `score_maximo_teorico_arquetipo[arq.code]` simulando un disco "perfecto":

```python
def calcular_score_maximo_teorico(arquetipo: Archetype) -> float:
    """
    Disco perfecto: 4 substats, todos con peso máximo del arquetipo, 5 rolls cada uno,
    main exacta, nivel 15.
    """
    top4 = sorted(arquetipo.substats_positivos.values(), reverse=True)[:4]
    score_subs = sum(p * (1 + 5 * 0.25) for p in top4)
    score_main = 1.0
    score_nivel = 0.5
    return score_subs + score_main + score_nivel
```

Cargar al arrancar la app, recalcular solo si cambia `disc_archetypes`.

### Hito 2.2.3 · `app/core/recommender.py`

Implementa la decisión RF-04 §7.3:

```python
def recomendar(disco: Disc, agent_repo, ctx) -> Recommendation:
    """
    Itera sobre los 45 PJs, calcula score_norm, ordena.
    Aplica thresholds por PJ.
    Si nadie alcanza, fallback al arquetipo.
    """
    candidatos = []
    for pj in agent_repo.get_all():
        sb = score_disco(disco, pj, ctx)
        candidatos.append((pj, sb))

    candidatos.sort(key=lambda x: x[1].score_norm, reverse=True)
    top_pj, top_sb = candidatos[0]

    if top_sb.score_norm >= top_pj.threshold_equip:
        return Recommendation("equipar", top_pj.id, top_sb.score_norm,
                              candidatos[:5], top_sb.desglose)
    if top_sb.score_norm >= top_pj.threshold_upgrade:
        return Recommendation("mejorar", top_pj.id, top_sb.score_norm,
                              candidatos[:5], top_sb.desglose)
    # Fallback arquetipo
    arq_scores = [(arq, score_disco_arquetipo(disco, arq, ctx))
                  for arq in arquetipo_repo.get_all()]
    arq_scores.sort(key=lambda x: x[1], reverse=True)
    top_arq, top_arq_score = arq_scores[0]
    if top_arq_score >= ctx.threshold_stock:
        return Recommendation("reserva", arquetipo_id=top_arq.id, score=top_arq_score, ...)
    return Recommendation("descartar", score=top_sb.score_norm, ...)
```

### Hito 2.2.4 · Golden cases QA-02

**Archivo:** `app/tests/fixtures/golden_cases.json`. **Casos canónicos del project-context-IA §11:**

```json
{
  "scoring_disco_perfecto_yanagi": {
    "input": {
      "disco": {"set": "Jazz Caótico", "slot": 4, "main": "Maestría de Anomalía",
                "subs": [["Maestría de Anomalía", 36, "flat", 3],
                          ["ATK%", 9, "%", 1],
                          ["Prob. Crítica", 2.4, "%", 1],
                          ["ATK", 19, "flat", 0]],
                "nivel": 15},
      "pj": "Yanagi"
    },
    "expected": {"score_norm": 0.92, "recomendacion": "equipar", "tolerance": 0.02}
  },
  "scoring_disco_set_main_perfectos_subs_basura": {
    "input": {
      "disco": {"set": "Tecno Pícido", "slot": 5, "main": "Bono Daño Físico",
                "subs": [["DEF%", 4.8, "%", 2],
                          ["HP%", 3, "%", 1],
                          ["Maestría de Anomalía", 9, "flat", 1],
                          ["Prob. Crítica", 2.4, "%", 1]],
                "nivel": 15},
      "pj_arquetipo": "ATK_DPS"
    },
    "expected": {"score_arq_norm_lt": 0.30, "recomendacion": "descartar"}
  },
  "scoring_determinismo_1000": {
    "description": "Mismo input 1000 veces debe dar mismo output",
    "input": {"disco_id": 482, "pj": "Yanagi"},
    "expected": {"score_variance": 0.0}
  }
  // … más casos del QA-02
}
```

**Test:** `app/tests/regressions/test_golden_cases.py` itera el JSON y hace `assert score_norm pytest.approx(expected, abs=tolerance)`.

### Cierre Fase 2.2 — Aceptación

- [ ] `pytest app/tests/unit/test_scoring.py` → 100% pass.
- [ ] `pytest app/tests/regressions/test_golden_cases.py` → 100% pass (mínimo 7 casos QA-02).
- [ ] Test de determinismo: 1000 iteraciones, varianza == 0.
- [ ] Performance: P95 de `score_disco` < 5 ms con DB warm.
- [ ] Commit con tag `phase-2.2-scoring-engine`.

---

## 5. Fase 2.3 — Primer pase batch sobre los 332+N discos

> Es el primer "uso real" del scoring engine. Output: `inventory_disc_evaluations` poblada + `inventory_discs.score_evaluacion` actualizado.

### Hito 2.3.1 · `app/scripts/score_existing_inventory.py`

```python
def main():
    con = sqlite3.connect("db/danibod_zzz_v2.db")
    backup_db()
    discs = list(con.execute("SELECT * FROM inventory_discs WHERE descartado=0"))
    ctx = build_scoring_context(con)
    
    rows_eval = []
    for d in discs:
        rec = recomendar(parse_disc(d), agent_repo=AgentRepo(con), ctx=ctx)
        rows_eval.append((d["id"], "captura_inicial", rec.tipo, rec.score, rec.detalle_json))
        con.execute("""UPDATE inventory_discs
                         SET score_evaluacion=?, agentes_compatibles=?, notas=?
                       WHERE id=?""",
                    (rec.score, rec.candidatos_json, rec.notas, d["id"]))
    
    con.executemany("""INSERT INTO inventory_disc_evaluations
                       (inventory_disc_id, trigger_evento, recomendacion, score, detalle_json)
                       VALUES (?,?,?,?,?)""", rows_eval)
    con.commit()
    
    generar_reporte_md(discs, rows_eval)
```

### Hito 2.3.2 · Reporte de salida

**Archivo:** `audit/scoring_first_pass_YYYYMMDD.md`. Incluye:

- Distribución de recomendaciones (`equipar` / `mejorar` / `reserva` / `descartar`).
- Top 10 discos por PJ.
- Discos `equipados` actualmente cuyo score < threshold_equip (señales de mala build).
- Discos `sueltos` cuyo score > threshold_equip (oportunidades de equipar).
- PJs sin discos `equipar`-tier en su inventario (señal de farmeo necesario).
- Lista de discos con score = NULL (deben ser cero al final).

### Cierre Fase 2.3 — Aceptación

- [ ] `inventory_discs.score_evaluacion IS NOT NULL` para 332+N filas.
- [ ] `inventory_disc_evaluations` con N filas (1 por disco activo).
- [ ] Reporte revisado por usuario.
- [ ] Backup pre-pase archivado.
- [ ] Commit con tag `phase-2.3-first-batch-scored`.

---

## 6. Fase 2.4 — Capa OCR + Detector

> Aquí entra el "motor de captura" propiamente dicho. Implementa RF-09 (OCR híbrido) y la máquina de estados de RF-04 §4. **Ningún hito aquí toca DB**; el sync se cierra en Fase 2.5.

### Hito 2.4.1 · `app/core/ocr_backend.py` — interfaz abstracta

```python
from abc import ABC, abstractmethod

class OcrBackend(ABC):
    @abstractmethod
    def text(self, img, psm: int = 6, lang: str = "spa") -> tuple[str, float]: ...
    @abstractmethod
    def number(self, img) -> tuple[float, float]: ...   # (valor, confianza)
```

### Hito 2.4.2 · `ocr_tesseract.py`

`pytesseract` adapter. Pre-procesado: grayscale + denoise + binarize.

### Hito 2.4.3 · `ocr_paddle.py`

PaddleOCR para números densos (substats con muchos dígitos). Lazy-load: solo se inicializa la primera vez que se invoca.

### Hito 2.4.4 · `app/core/detector.py` — máquina de estados de pantalla

Implementa RF-04 §4 — clasifica el frame en uno de los 12 estados S1-S12. Anclas en `app/resources/templates/`:

```
template_s2_resultado_desafio.png          # título "RESULTADOS DEL DESAFÍO"
template_s5_resultado_afinacion.png        # header "Resultado de afinación:"
template_s9_personalizacion_pistas.png     # header "Personalización de pistas de disco"
template_s10_modal_upgrade.png             # X roja + barra EXP verde
template_s11_desmontaje.png                # header "Desmontaje"
template_s8_hexagono_driver.png            # hexágono central con "DRIVER"
```

Algoritmo: `cv2.matchTemplate` con `TM_CCOEFF_NORMED`, threshold 0.85, devuelve el match más fuerte. Si todos < 0.85 → S12 (negativo).

### Hito 2.4.5 · `capturer.py`

```python
def capture_window(window_title: str = "ZenlessZoneZero") -> np.ndarray: ...
def crop_roi(img, roi: tuple[int, int, int, int]) -> np.ndarray: ...
```

ROIs por estado en `app/config/rois.toml` (calibrables vía wizard de Fase 3 RF-11).

### Hito 2.4.6 · `parser_disc.py`

Convierte la salida de OCR en un struct `DiscParsed`:

```python
@dataclass
class DiscParsed:
    set_canon: str
    slot: int
    main_canon: str
    main_valor: float
    main_unidad: str  # 'flat' | '%'
    subs: list[tuple[str, float, str, int]]   # (canon, val, unidad, rolls)
    nivel: int
    rareza: str  # 'S' | 'A' | 'B'
    confianza_global: float

def parse_modal_detalle(img, ocr: OcrBackend) -> DiscParsed:
    title_text, c1 = ocr.text(crop_roi(img, ROI_TITULO), psm=7)
    set_, slot = re.match(r"^(.+) \((\d)\)$", title_text).groups()
    set_canon = normalize_set_name(set_)
    # …
    return DiscParsed(...)
```

Reusa `app/core/stats_vocab.py` para nombre canónico de stats.

### Hito 2.4.7 · `monitor.py`

Loop principal con polling adaptativo (RF-04 §5):

```python
class Monitor:
    def run(self):
        last_state = None
        while not self.stop_event.is_set():
            img = capture_window()
            state = self.detector.classify(img)
            if state == 'S3' or state == 'S6' or state == 'S7':   # modal detalle
                parsed = parse_modal_detalle(img, self.ocr)
                if parsed.confianza_global >= 0.7:
                    self.on_disc_detected(parsed)
            # …polling cadence según state…
            time.sleep(self.cadence_for(state))
```

Hook con `pywin32` para `EVENT_SYSTEM_FOREGROUND` → forzar scan al volver al juego.

### Hito 2.4.8 · Golden set OCR

50 capturas reales del juego con expected JSON. Test `test_ocr_golden_set.py` itera y mide accuracy (≥ 90% objetivo).

### Cierre Fase 2.4 — Aceptación

- [ ] Detector clasifica correctamente las 12 anclas (test L4 con 20 capturas reales etiquetadas).
- [ ] Parser sobre golden set OCR ≥ 90% campos correctos (set, slot, main, subs).
- [ ] Latencia P95 pipeline `screenshot → DiscParsed`: < 500 ms.
- [ ] Commit con tag `phase-2.4-ocr-detector`.

---

## 7. Fase 2.5 — Sync RF-04/05

> Pega la capa OCR (Fase 2.4) con el scoring (Fase 2.2) y la persistencia. Aquí se cierra el flujo "disco capturado en pantalla → registro en DB → recomendación lista".

### Hito 2.5.1 · `sync_equip.py` (RF-04)

```python
def on_disc_detected(parsed: DiscParsed):
    with transaction(con):
        # UPSERT por hash (fecha_obtencion truncada al día + set + slot + main + main_valor)
        existing = repo.find_by_hash(parsed)
        if existing:
            disc_id = existing.id
            repo.update_from_parsed(disc_id, parsed)
            trigger = "re_eval_threshold"
        else:
            disc_id = repo.insert(parsed)
            trigger = "captura_inicial"
        rec = recomendar(parsed, agent_repo, ctx)
        eval_repo.insert(disc_id, trigger, rec)
        repo.update_score(disc_id, rec.score, rec.candidatos_json, rec.notas)
        notify_user(rec, parsed)   # toast (Fase 3) por ahora solo log
```

### Hito 2.5.2 · `sync_upgrade.py` (RF-05)

Captura PRE/POST del modal S10:
- PRE: snapshot al detectar el modal de upgrade.
- POST: cuando el nivel cambia y se cierra la animación, snapshot del estado nuevo.
- Diff: detectar qué subs subieron de rolls.
- Re-eval: dispara `re_eval_upgrade` en `inventory_disc_evaluations`.

### Hito 2.5.3 · Hotkey F8 — captura manual fallback

Hook con `pynput`. Al detectar F8, dispara un scan inmediato del frame actual. Útil cuando el detector falla en estado ambiguo.

### Hito 2.5.4 · Hotkey F10 — pausar / reanudar monitor

Toggle del `stop_event` del thread del monitor.

### Cierre Fase 2.5 — Aceptación

- [ ] L4 (Daniel): farmear 5 discos en juego con app activa → 5 filas nuevas en `inventory_discs` + 5 en `inventory_disc_evaluations`.
- [ ] L4: subir un disco de nivel 0 a 15 → 5 capturas (PRE + 4 POST) registradas con `re_eval_upgrade`.
- [ ] Latencia P95 pipeline `disco en pantalla → DB updated`: < 700 ms.
- [ ] 0 duplicados en inventario tras sesión de farmeo.
- [ ] Commit con tag `phase-2.5-sync-rf04-rf05`.

---

## 8. Fase 2.6 — Optimizador RF-06

> Última pieza del motor. Greedy + bonus pass + top-3 builds. Sin UI todavía (la UI llega en Fase 3 con RF-11).

### Hito 2.6.1 · Migración 07 — `optimizer_pending_actions`

Ya documentada en RF-06 §7. Nueva migración:

```sql
CREATE TABLE IF NOT EXISTS optimizer_pending_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_propuesta DATETIME DEFAULT CURRENT_TIMESTAMP,
    pj_id           INTEGER NOT NULL REFERENCES agents(id),
    build_id        TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'pendiente',
    fecha_aplicada  DATETIME,
    score_propuesto REAL,
    score_actual_pj REAL,
    delta           REAL,
    notas           TEXT
);
CREATE INDEX IF NOT EXISTS idx_opa_pj_estado ON optimizer_pending_actions(pj_id, estado);
```

### Hito 2.6.2 · `app/core/optimizer.py`

Implementa RF-06 §4. Pseudo:

```python
def best_build(pj_id: int, k: int = 3) -> list[Build]:
    pj = agent_repo.get_by_id(pj_id)
    inventory = disc_repo.get_pending_for(pj.arquetipo_primario)
    
    # Fase 1 — greedy por slot
    top_k_per_slot = {}
    for slot in range(1, 7):
        candidates = [d for d in inventory if d.slot == slot
                      and main_compatible(d, pj, slot)]
        top_k_per_slot[slot] = sorted(
            candidates, key=lambda d: score_disco(d, pj, ctx).score_raw, reverse=True)[:K_PER_SLOT]
    
    # Fase 2 — bonus pass: enumerar particiones y calcular set bonus
    builds = []
    for partition in enumerate_set_partitions(top_k_per_slot, pj):
        score_total = sum(d.score for d in partition.discos) + partition.set_bonus
        partition.score_total = score_total
        builds.append(partition)
    
    # Top K
    builds.sort(key=lambda b: b.score_total, reverse=True)
    return builds[:k]
```

### Hito 2.6.3 · Swap chains length 1

Por cada disco propuesto que esté equipado en otro PJ, calcular `swap_neto = ganancia_destino - perdida_origen`. Solo proponer si `swap_neto > 0`. Respetar flag `protected_build`.

### Hito 2.6.4 · Auto-trigger desde RF-04

Cuando `recomendar()` devuelve `recomendacion='equipar'` con `score >= threshold_equip`, agendar `recompute_best_build(pj_id)` con debounce 2s.

### Hito 2.6.5 · Caso canónico: Miyabi

Reproducir el output de RF-06 §9 (build con 4pc Balada rama + 2pc Tecno Pícido, score_total 0.91, swap chain de 1 disco a Yanagi). Test L3 (integración con DB fixture).

### Cierre Fase 2.6 — Aceptación

- [ ] Migración 07 aplicada.
- [ ] Caso canónico Miyabi devuelve build #1 con score ±2% del documentado.
- [ ] Top 3 builds devueltas por cada llamada.
- [ ] Latencia P95 con 332 discos < 500 ms (objetivo RF-06 §8.1: 130 ms).
- [ ] Commit con tag `phase-2.6-optimizer-rf06`.

---

## 9. Criterios de aceptación globales (RNF)

| Criterio | Cómo se mide | Cuándo se valida |
|----------|--------------|------------------|
| RNF-01 ETL sin fallas | `PRAGMA integrity_check` + `foreign_key_check` post-cada migración | Al final de cada fase |
| RNF-02 Cero shortcuts | Code review: cualquier dato hardcodeado lleva fuente; cualquier NULL lleva flag | Al cierre de cada hito |
| RNF-03 ToS HoYoverse | Code review: solo `mss` para captura, cero `pymem` / `keyboard.send` / etc. | Al cierre de Fase 2.4 |
| RNF-06 Latencia | `pytest-benchmark` sobre pipeline completo | Cierre Fase 2.5 |

---

## 10. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| OCR falla con resoluciones no estándar | Media | Alto | Calibración de ROIs vía wizard (Fase 3 RF-11). Mientras: hardcoded para 2560×1440. |
| Nomenclatura de stats con typos no observados | Baja | Medio | Audit 2.0.1 más amplio. Lista negra de "rejected" en script idempotente. |
| Greedy + bonus pass da builds subóptimas | Media | Medio | Guardado todo el top-K por slot → fácil de comparar contra MILP en Fase 2 (no v1). |
| Performance P95 sube > 500ms con inventario > 1000 discos | Media | Medio | Benchmark al cierre de cada fase con datasets sintéticos x2/x4 del actual. |
| Awakenings sin texto in-game bloquean alguna lógica | Baja | Bajo | Placeholder con `activo=0` ya manejado en queries; el scoring no los usa. |
| El PJ nuevo no tiene preferencias en Prydwen aún | Media | Bajo | Fallback a arquetipo del rol (ya cubierto por scoring engine). Onboarding §11 lo tiene previsto. |

---

## 11. Rituales operativos (aplicables a todas las fases)

1. **Antes de empezar un hito:** `git checkout -b feature/<hito>` desde `main`.
2. **Antes de cualquier write a DB:** `cp db/danibod_zzz_v2.db db/danibod_zzz_v2.backup_premig_$(date +%Y%m%d_%H%M%S).db`.
3. **Después de migrar / cargar datos:** `PRAGMA foreign_key_check; PRAGMA integrity_check;` + commit con la salida en mensaje.
4. **Al cerrar un hito:** actualizar `project-context-IA.md` §3 (counts) y §4 (estado del RF).
5. **Al cerrar una fase:** tag `phase-2.X-<nombre>`, push a remote, abrir PR de merge a `main`.
6. **Tras patch de ZZZ:** ejecutar `Documentacion/QA/QA-07_Regresion_Patches.md`.
7. **Si un hallazgo invalida diseño:** abrir issue, actualizar el doc RF correspondiente, no parchear código.

---

## 12. Diagrama de fases (resumen)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.0 — SANEAMIENTO (BLOQUEANTE)                                           │
│ audit → vocab → mig_06 → restandarize → seed prefs → ONBOARDING PJ NUEVO     │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.1 — SCAFFOLD app/                                                      │
│ estructura → pyproject → repos → defaults.toml → tests/                       │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.2 — SCORING ENGINE (puro, sin OCR ni UI)                              │
│ scoring.py → score_normalizer.py → recommender.py → golden cases             │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.3 — PRIMER PASE BATCH                                                  │
│ score_existing_inventory.py → 332+N discos evaluados → reporte               │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.4 — OCR + DETECTOR                                                     │
│ ocr_backend → tesseract/paddle → detector estado → parser_disc → monitor     │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.5 — SYNC RF-04/05                                                      │
│ sync_equip → sync_upgrade → hotkeys F8/F10                                    │
└──────────────────────────────────┬────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FASE 2.6 — OPTIMIZADOR RF-06                                                  │
│ migración 07 → optimizer.py → swap chains → caso canónico Miyabi             │
└───────────────────────────────────────────────────────────────────────────────┘
                                   ▼
                   FIN FASE 2 — Motor de captura/scoring listo.
                   Siguiente: FASE 3 — UI .exe (RF-11) + IA RF-12.
```

---

## 13. Estimación de esfuerzo (para planificación)

| Fase | Esfuerzo estimado | Camino crítico |
|------|------------------|----------------|
| 2.0 Saneamiento | 4-6 horas | Audit + script restandarización + onboarding PJ |
| 2.1 Scaffold | 2 horas | Estructura + tests vacíos |
| 2.2 Scoring engine | 6-8 horas | Implementación + 7 golden cases pasando |
| 2.3 Primer batch | 2-3 horas | Script + reporte |
| 2.4 OCR + detector | 8-12 horas | Templates + 50 capturas anotadas + parser |
| 2.5 Sync | 4-6 horas | Hooks + transacciones + UPSERT por hash |
| 2.6 Optimizador | 6-8 horas | Greedy + bonus pass + swap chains + tests |
| **Total Fase 2** | **32-45 horas** | Distribuido en sprints según disponibilidad |

> Estimación es de "trabajo de codeo + tests" — no incluye tiempo de captura de screenshots para el golden set OCR (otra hora aparte) ni tiempo de validación L4 in-game (incluido en Fase 2.5).

---

## 14. Próximos pasos inmediatos

**Lo que toca decidir antes de empezar Fase 2.0:**

1. **Confirmar el agente nuevo** — responder Q1-Q4 del Hito 2.0.6.
2. **Confirmar dónde están los discos capturados manualmente estos días** — Hito 2.0.7.
3. **Inicializar git en local** — connectar al remoto `https://github.com/DaniBOD/Zenless_analitycs.git`, commit del estado actual + este roadmap, push.

**Una vez confirmados 1-3, arrancamos con Hito 2.0.1 (audit `inventory_discs`).**

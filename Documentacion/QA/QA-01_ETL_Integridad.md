# QA-01 — ETL e Integridad de la base

**Capa:** L1 (validación de schema y datos) + L5 (cruzada con fuentes)
**RFs cubiertos:** RF-01, RF-02, RF-03 + cualquier migración futura
**Cuándo consultar:** al aplicar migración, al cargar datos en lote, al hacer merge de IDs, después de un patch ZZZ.

> **Regla suprema:** RNF-01 (ETL sin fallas) prohíbe pérdida de información, violación de integridad referencial y operaciones no idempotentes silenciosas. Este doc traduce esa regla en chequeos concretos.

---

## 1. Smoke test universal post-cualquier-cambio

Cualquier operación que toque DB **debe** terminar con este script de 4 líneas, ejecutado dentro del mismo proceso (no en una sesión nueva, para que se vea el efecto de transacciones abiertas):

```bash
sqlite3 db/danibod_zzz_v2.db <<'SQL'
PRAGMA integrity_check;
PRAGMA foreign_key_check;
PRAGMA quick_check;
SELECT 'OK' WHERE (SELECT COUNT(*) FROM sqlite_master WHERE type='table') >= 31;
SQL
```

Salida esperada (todas las líneas):
```
ok
(sin filas)
ok
OK
```

**Si cualquier línea diverge, abortar el cambio y restaurar backup.**

---

## 2. Estado actual de referencia (2026-05-01)

Snapshot de filas validado contra `db/danibod_zzz_v2.db`. Sirve de baseline; cualquier desviación negativa post-migración es una regresión.

| Tabla | Filas baseline | Comentario |
|-------|---------------:|------------|
| `agents` | 45 | 45/45 roster cerrado |
| `weapons` | 53 | 49 base + 4 nuevas (Street Superstar / Florescencia / Wild Gastronome / Hertz Transit) |
| `disc_sets` | 26 | post-merge id 47→40, 50→35 |
| `agent_awakenings` | 5 | 1 verificado + 4 placeholder `pending_capture` |
| `agent_thresholds` | 103 | 93 base + 10 gaps abril 2026 |
| `agent_score_thresholds` | 45 | defaults equip 0.75 / stock 0.50 |
| `agent_substat_preferences` | 0 | vacía hasta seed Prydwen |
| `agent_discs` | 270 | 45 × 6 incluyendo EMPTY |
| `inventory_discs` | 332 | 257 equipados + 75 sueltos |
| `inventory_weapons` | 50 | 40 equipadas + 10 sueltas |
| `disc_archetypes` | 6 | seed cerrado |
| `disc_set_archetype` | 34 | 26 sets + 8 dobles |
| `inventory_disc_evaluations` | 0 | crece con uso |
| `optimizer_pending_actions` | 0 | crece con uso |
| `team_synergies` | 0 | esperando seed RF-12 |
| `team_compositions` | 0 | esperando seed RF-12 |
| `ai_catalog_runs` | 0 | crece con uso |
| `enemies` | 12 | seed manual |
| `enemy_resistances` | 72 | 12 × 6 elementos |
| `shiyu_cycles` / `da_cycles` | 0 / 0 | esperando scrapers RF-13 |
| `lategame_runs` / `lategame_run_damage` | 0 / 0 | esperando captura F11 |
| `tier_list_personal` | 0 | esperando recálculo RF-13 |
| `prydwen_tier_snapshots` | 0 | esperando scraper RF-13 |
| `team_synergy_adjustments` | 0 | crece con retro-feedback |
| `weapon_passives_structured` | 0 | esperando seed RF-14 |
| `content_profiles` | 4 | shiyu_critical / da / hollow_zero / general |
| `weapon_evaluations` | 0 | crece por snapshot |
| `prydwen_weapon_recommendations_snapshots` | 0 | esperando scraper |
| `pj_weapon_synergy` | 270 | 45 × 6 categorías |

Script de verificación (Python, ejecutar para regenerar snapshot tras cambios):

```python
# app/scripts/qa/snapshot_counts.py
import sqlite3, json, sys
from datetime import datetime

con = sqlite3.connect('db/danibod_zzz_v2.db')
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
)]
snapshot = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
out = {'fecha': datetime.now().isoformat(timespec='seconds'), 'tablas': snapshot}
print(json.dumps(out, indent=2, ensure_ascii=False))
```

Comparar contra `Documentacion/QA/evidencia/baseline_2026-05-01.json` antes y después de cada operación masiva.

---

## 3. Constraints estructurales que NO deben fallar

Lista de violaciones que producen `foreign_key_check ≠ 0` o CHECK violation. Cada bullet es un test L1 ejecutable.

### 3.1 FKs equipados-vs-asignaciones
```sql
-- equipados en inventory_discs deben tener agente_asignado válido
SELECT id FROM inventory_discs
WHERE equipado = 1 AND (agente_asignado IS NULL
   OR agente_asignado NOT IN (SELECT id FROM agents));
-- Esperado: 0 filas
```

```sql
-- count equipados debe coincidir con slots no-EMPTY de agent_discs
SELECT
  (SELECT COUNT(*) FROM inventory_discs WHERE equipado=1) AS inv_eq,
  (SELECT COUNT(*) FROM agent_discs WHERE main_stat <> 'EMPTY' AND main_stat IS NOT NULL) AS slots;
-- Esperado: inv_eq = slots = 257 al baseline
```

```sql
-- inventory_weapons equipadas: máximo 1 arma por agente
SELECT agente_asignado, COUNT(*) c FROM inventory_weapons
WHERE equipado=1 GROUP BY agente_asignado HAVING c > 1;
-- Esperado: 0 filas
```

```sql
-- inventory_weapons.refinamiento entre 1 y 5
SELECT id, refinamiento FROM inventory_weapons
WHERE refinamiento NOT BETWEEN 1 AND 5;
-- Esperado: 0 filas
```

### 3.2 CHECKs declarados en migraciones
```sql
-- team_synergies: pj_a < pj_b siempre
SELECT id FROM team_synergies WHERE pj_a_id >= pj_b_id;
-- Esperado: 0 filas

-- team_synergies.confianza dentro de [0,1]
SELECT id FROM team_synergies WHERE confianza < 0 OR confianza > 1;
-- Esperado: 0 filas

-- weapon_passives_structured.trigger_tipo en enum cerrado
SELECT id FROM weapon_passives_structured
WHERE trigger_tipo NOT IN (
  'always','on_skill_use','on_ex_use','on_ult_use','on_chain_attack',
  'on_basic','on_hit','enemy_hp_above','enemy_hp_below','team_has_element',
  'team_has_faccion','self_anomaly_active','self_stun_active',
  'self_buff_active','combat_time_above'
);
-- Esperado: 0 filas

-- tier_list_personal.tier en buckets fijos
SELECT id FROM tier_list_personal WHERE tier NOT IN ('S+','S','A','B','C','D');

-- lategame_runs.estrellas entre 0 y 3
SELECT id FROM lategame_runs WHERE estrellas NOT BETWEEN 0 AND 3;

-- optimizer_pending_actions.estado enum
SELECT id FROM optimizer_pending_actions
WHERE estado NOT IN ('TODO','APLICADO','DESCARTADO','OBSOLETO');
```

### 3.3 Reglas de negocio implícitas (no son CHECK pero son invariantes)
```sql
-- ningún PJ tiene 2 armas equipadas
SELECT agente_id, COUNT(*) c FROM inventory_weapons
WHERE equipado=1 AND agente_asignado IS NOT NULL
GROUP BY agente_asignado HAVING c > 1;

-- ningún disco aparece duplicado entre equipado=1 e inventory equipados de 2 agentes
-- (salvo que sea correcto: cada inventory_discs.id es único por construcción)
SELECT id FROM inventory_discs i1
WHERE equipado=1 AND EXISTS (
  SELECT 1 FROM inventory_discs i2
  WHERE i2.id <> i1.id AND i2.set_id=i1.set_id AND i2.slot=i1.slot
    AND i2.main_stat=i1.main_stat AND i2.main_valor=i1.main_valor
    AND i2.agente_asignado=i1.agente_asignado AND i2.equipado=1
);
-- Esperado: 0 (alerta: duplicación lógica del mismo disco contado dos veces)

-- agent_discs.set_id debe existir en disc_sets (FK ya lo asegura, pero validamos casos NULL para EMPTY)
SELECT id FROM agent_discs WHERE main_stat<>'EMPTY' AND set_id IS NULL;
-- Esperado: 0 filas

-- disc_set_archetype con prioridad fuera de {1,2}
SELECT * FROM disc_set_archetype WHERE prioridad NOT IN (1,2);
```

---

## 4. Procedimiento de migración con backup

Toda migración nueva sigue este patrón obligatorio:

```bash
# 1) Backup con timestamp
TS=$(date +%Y%m%d_%H%M%S)
cp db/danibod_zzz_v2.db "db/danibod_zzz_v2.backup_premig_${TS}.db"

# 2) Aplicar migración dentro de transacción explícita
sqlite3 db/danibod_zzz_v2.db <<SQL
BEGIN TRANSACTION;
.read db/migrations/2026-XX-XX_NN_descripcion.sql
COMMIT;
SQL

# 3) Smoke test post-migración
sqlite3 db/danibod_zzz_v2.db <<'SQL'
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SQL

# 4) Snapshot de filas
python app/scripts/qa/snapshot_counts.py > "Documentacion/QA/evidencia/snapshot_postmig_${TS}.json"

# 5) Diff con baseline anterior
diff Documentacion/QA/evidencia/baseline_*.json \
     Documentacion/QA/evidencia/snapshot_postmig_${TS}.json
```

**Si cualquier paso falla:**
```bash
cp "db/danibod_zzz_v2.backup_premig_${TS}.db" db/danibod_zzz_v2.db
```

**Si la migración pasa pero el resultado no es lo esperado:** documentar la discrepancia en el README principal §2 (Estado actual) **antes** de avanzar.

---

## 5. Idempotencia

Una migración es **idempotente** si correrla dos veces sobre la misma DB no produce diferencia respecto a correrla una sola vez. Esto es deseable pero no siempre posible (un `INSERT` simple no lo es).

Patrones idempotentes:
- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `INSERT OR IGNORE INTO ... VALUES`
- `INSERT INTO ... ON CONFLICT(...) DO NOTHING`
- `UPDATE` con condición que ya está cubierta queda noop

Patrones NO idempotentes (requieren guardia explícita):
- `ALTER TABLE ADD COLUMN` — usar `PRAGMA table_info(t)` para chequear antes
- `INSERT` simple sin ON CONFLICT — duplica filas
- Merge de IDs — el script debe detectar si ya se hizo (SELECT COUNT del ID destino)

**Test de idempotencia para una migración nueva:**
```bash
TS=$(date +%Y%m%d_%H%M%S)
cp db/danibod_zzz_v2.db "/tmp/test_idem_${TS}.db"
sqlite3 "/tmp/test_idem_${TS}.db" < db/migrations/NN_nueva.sql
md5_a=$(sqlite3 "/tmp/test_idem_${TS}.db" .dump | md5sum)
sqlite3 "/tmp/test_idem_${TS}.db" < db/migrations/NN_nueva.sql 2>/dev/null
md5_b=$(sqlite3 "/tmp/test_idem_${TS}.db" .dump | md5sum)
[ "$md5_a" = "$md5_b" ] && echo "IDEMPOTENTE" || echo "NO IDEMPOTENTE — investigar"
```

---

## 6. Carga en lote: anti-patterns y golden cases

### 6.1 Anti-pattern detectado en historia del proyecto
Cuando se cargaron los 75 discos sueltos en `inventory_discs`, hubo un bloqueo por virtiofs que se resolvió escribiendo en scratch local + raw write. **Lección:** no asumir que el filesystem soporta locking de SQLite cuando se monta vía red/virtiofs.

**Test L1 derivado:** antes de cualquier carga >50 filas en lote, ejecutar:
```python
import sqlite3
con = sqlite3.connect('db/danibod_zzz_v2.db', timeout=5)
con.execute("BEGIN IMMEDIATE")
con.execute("ROLLBACK")
print("Locking funciona")
```
Si falla con `database is locked`, copiar la DB a scratch local, operar ahí y volver a copiar.

### 6.2 Golden cases — cargas verificables

Cada carga histórica deja una huella reproducible:

| Operación | Pre | Post | Test L1 |
|-----------|----:|-----:|---------|
| Merge id 47→40 (Tecno tetraodóntido → Puffer Electro) | 27 sets | 26 sets | `SELECT COUNT(*)=26 FROM disc_sets` + `SELECT COUNT(*)=0 FROM agent_discs WHERE set_id=47` |
| Merge id 50→35 (Moonlight Lullaby → Nana luz cenicienta) | 27 sets | 26 sets | mismo patrón con set_id=50 |
| Carga 75 discos sueltos | 257 filas | 332 filas | `SELECT COUNT(*) FROM inventory_discs WHERE equipado=0` = 75 |
| Carga 10 W-Engines sueltas | 40 filas | 50 filas | `SELECT COUNT(*) FROM inventory_weapons WHERE equipado=0` = 10 |
| Migración 01 archetypes | 13 tablas | 18 tablas | `disc_archetypes`=6, `disc_set_archetype`≥26 |
| Migración 04 enemies seed | 0 enemies | 12 enemies | `enemies`=12, `enemy_resistances`=72 |

---

## 7. Awakenings: caso especial RNF-02

Los awakenings son el ejemplo paradigmático de "no inventar valores". Estado actual:

| Agente | Estado | Acción L4 pendiente |
|--------|--------|---------------------|
| Burnice | ✅ nv6 verificado, texto cargado | — |
| Lycaon | placeholder `pending_capture` | Daniel captura screenshot in-game de niveles 1-6 |
| N.°0:Anby | placeholder | idem |
| Ellen | placeholder | idem |
| Grace | placeholder | idem |
| Asaba Harumasa | sin fila insertada | Daniel confirma nivel exacto antes de insertar |
| N.°11 | sin fila insertada | idem |

**Test L1 que protege esto:**
```sql
-- Detectar awakenings con placeholder vivos por más de 30 días (señal de olvido)
SELECT id, agente_id FROM agent_awakenings
WHERE descripcion = 'pending_capture'
  AND fecha_creacion < datetime('now', '-30 days');
-- Resultado debe revisarse en el QA-07 por patch
```

Si Daniel actualiza el texto de un awakening, el `UPDATE` debe correr así:
```sql
BEGIN;
UPDATE agent_awakenings
   SET descripcion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
 WHERE agente_id = ? AND nivel = ?;
COMMIT;
-- Verificar
SELECT * FROM agent_awakenings WHERE agente_id = ? AND nivel = ?;
```

---

## 8. Backups: política de retención

| Backup | Cuándo | Retención |
|--------|--------|-----------|
| `db/danibod_zzz_v2.backup_premig_*.db` | Antes de cada migración | Permanente hasta confirmación de éxito + 30 días |
| `db/danibod_zzz_v2.backup_*.db` | Manual antes de merge de IDs o operación riesgosa | 90 días |
| `db/danibod_zzz_v2.backup_diaria_*.db` | Cron diario (a definir en RF-11) | 7 días rotativos |
| `db/danibod_zzz_v2.backup_premerge_*.db` | Antes de merge | Permanente |

**Test de restauración** (debe correr trimestralmente):
```bash
cp db/danibod_zzz_v2.backup_*.db /tmp/restore_test.db
sqlite3 /tmp/restore_test.db "PRAGMA integrity_check;"
sqlite3 /tmp/restore_test.db "SELECT COUNT(*) FROM agents;"  # esperado 45
rm /tmp/restore_test.db
```

---

## 9. Resumen de checks por frecuencia

| Frecuencia | Checks |
|------------|--------|
| Tras cada operación DB | §1 smoke test, §3 constraints relevantes al cambio |
| Tras cada migración | §1 + §4 protocolo completo + §6.2 golden case del cambio |
| Diario (cron RF-11) | §1 smoke + comparar `agents`/`weapons`/`disc_sets` contra baseline |
| Semanal | §3 todos los CHECKs + §7 awakenings stale |
| Trimestral | §8 test de restauración + auditoría completa de FKs |
| Por patch ZZZ | Ver [QA-07_Regresion_Patches.md](./QA-07_Regresion_Patches.md) |

---

*Cualquier hallazgo L1 que requiera fix se documenta en `audit/discrepancy_report_<fecha>.md` siguiendo el patrón ya existente en `audit/discrepancy_report_20260422.md`.*

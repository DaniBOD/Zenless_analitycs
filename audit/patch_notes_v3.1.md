# Patch v3.1 — notas de regresión

**Fecha publicación:** 2026-07-28
**Fecha aplicado a DaniBOD:** 2026-07-28 (parcial — ver §Estado)
**Backup pre-patch:** `db/danibod_zzz_v2.backup_prepatch_20260728_213414.db`
**Baseline pre-patch:** `Documentacion/QA/evidencia/baseline_prepatch_20260728_213414.json`
**Rama:** `claude/quizzical-tereshkova-ebe07e`

---

## Estado

| Fase QA-07 | Estado |
|------------|--------|
| A — preparación (backup + baseline + smoke L1) | ✅ cerrada |
| B — lectura del patch | 🟡 parcial (este doc) |
| C — onboarding de assets nuevos | ⛔ **bloqueada**: falta saber qué PJs consiguió Daniel |
| D — UPDATE stats existentes | ⏸ sin cambios reportados |
| E — re-scrape | ⏸ pendiente |
| F — recálculos derivados | ⏸ pendiente |
| G — validación L1 final | 🟡 parcial (post-migración 14: ✅) |
| H — validación L4 con frames | ⛔ pendiente (requiere sesión en vivo) |
| I — docs | 🟡 este doc + `project-context-IA.md` pendiente |
| J — auto-encolado RF-12/RF-13 | ⏸ pendiente |

---

## Cambios identificados

### Atributo de daño nuevo: **Lumen**

Primer elemento nuevo desde Viento (v3.0). Impacta el schema porque
`enemy_resistances.elemento` tenía un `CHECK` cerrado.

**Hallazgo colateral:** ese mismo `CHECK` **ya estaba desactualizado antes de
Lumen** — nunca se le agregó `'viento'`, pese a que Velina (`agents.id=48`,
Viento) entró al roster el 2026-06-19 y el parser de agentes ya conocía el
elemento (`app/core/parser_agent_stats.py::_ELEMENTOS_DB`). Era imposible cargar
la resistencia a Viento de cualquier enemigo. Se arreglaron los dos de una.

### PJs nuevos

| PJ | En `agents` hoy | Notas |
|----|-----------------|-------|
| Remielle | ❌ no | pendiente de confirmación de obtención |
| Sigrid | ❌ no | segunda fase del banner |
| Aria | ❌ no | Daniel va a intentar sacarla |

Ninguno tiene fila. Roster actual: **49 agentes** (ids 1–49, último = Pyrois).

### W-Engines nuevas

Sin relevar. `weapons` = 59 filas (catálogo saneado el 2026-07-27/28).

### Sets nuevos

Sin relevar. `disc_sets` = 28 filas.

---

## Acciones ejecutadas

### ✅ Migración 14 — `enemy_resistances` admite `viento` y `lumen`

Archivo: `db/migrations/2026-07-28_14_enemy_resistances_lumen_viento.sql`
Backup previo: `db/danibod_zzz_v2.backup_premig_20260728_213542.db`

En SQLite un `CHECK` no se puede alterar → reconstrucción de tabla
(crear nueva → copiar preservando `id` → drop → rename → recrear los 2 índices),
todo dentro de una transacción única.

```
CHECK(elemento IN ('fisico','fuego','hielo','electrico','eter','frost'))
                 ↓
CHECK(elemento IN ('fisico','fuego','hielo','electrico','eter','frost','viento','lumen'))
```

**Alcance: solo schema.** No se insertó ninguna fila de resistencia para
viento/lumen — los multiplicadores por enemigo son datos a observar/scrapear
(Hakush.in) y por RNF-02 no se inventan. La tabla sigue con 72 filas
(12 enemigos × 6 elementos viejos).

**Convención preservada:** esta columna usa minúscula sin tilde
(`fisico`, `electrico`); `agents.elemento` usa capitalizado con tilde
(`Físico`, `Eléctrico`). Son vocabularios de consumidores distintos y se
mantienen separados a propósito. `'frost'` se conserva (12 filas en uso).

#### Verificación

| Check | Resultado |
|-------|-----------|
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | 0 filas |
| Filas preservadas | 72 / 72 |
| Enemigos con resistencias | 12 / 12 |
| Índices recreados (`idx_enemy_res_enemy`, `idx_enemy_res_elem`) | 2 / 2 |
| `MAX(id)` preservado | 72 |
| `sqlite_sequence` (AUTOINCREMENT) | 72 |
| Diff de counts pre vs post | **cero cambios** (solo el timestamp) |

Prueba funcional del `CHECK` (insert + rollback, sin persistir):

| Valor probado | Resultado | Interpretación |
|---------------|-----------|----------------|
| `'lumen'` | ACEPTADO | ✅ objetivo del patch |
| `'viento'` | ACEPTADO | ✅ atraso saldado |
| `'plasma'` | RECHAZADO por CHECK | ✅ el CHECK sigue cerrado, no se abrió a texto libre |
| `'Lumen'` | RECHAZADO por CHECK | ✅ la convención minúscula sigue en pie |
| `'fisico'` (dup) | RECHAZADO por UNIQUE | ✅ el índice UNIQUE sobrevivió al rebuild |

Baseline post: `Documentacion/QA/evidencia/baseline_postmig14_20260728_213542.json`

### ✅ Herramientas QA que faltaban

QA-07 §3 Fase A/G referenciaba `app/scripts/qa/snapshot_counts.py`, que **no
existía**. Además, `CLAUDE.md` §3.1 asume un CLI `sqlite3` que **no está
instalado** en la máquina. Se crearon las dos piezas:

- `app/scripts/qa/snapshot_counts.py` — snapshot JSON de `COUNT(*)` de las 31
  tablas + `integrity_check` + `foreign_key_check`. Abre la DB en modo `ro`.
- `app/scripts/qa/apply_migration.py` — runner de migraciones que hace cumplir
  RNF-01 por construcción: backup automático, ejecución sentencia por sentencia,
  impresión de los smoke checks `expected_N`, y mensaje de restauración si falla.

---

## Bloqueado / pendiente

### ⛔ B1 — Onboarding de PJs: falta saber qué consiguió Daniel

No se insertó ninguna fila en `agents`. Precedente del proyecto (Velina, Pyrois):
se puede hacer **onboarding parcial** con rareza/elemento/rol/facción confirmados
in-game y stats en NULL (`pending_capture`), lo que ya habilita el
reconocimiento por S18 y la cosecha del badge.

### ⛔ B2 — Vocabulario de código para Lumen (requiere UNA captura in-game)

La migración deja la DB lista, pero el **código todavía no conoce Lumen**. Dos
lugares, y ninguno se puede completar sin ver la pantalla (RNF-02):

| Archivo | Qué falta | Por qué no se puede inventar |
|---------|-----------|------------------------------|
| `app/core/parser_agent_stats.py` | `_ELEMENTOS_DB` + `_ELEMENTO_SCREEN_MAP` | El cliente ES rotula los elementos con nombres propios, no traducciones literales: Fuego se muestra **"Ígneo"**, Hielo **"Gélido"**, Éter de Yixuan **"Tinta áurica"**. No sabemos con qué palabra rotula Lumen. |
| `app/core/stats_vocab.py` | `CANONICAL_MAINS_VARIABLE[5]` + un alias en `ALIASES` | Precedente directo: el main de Viento **no** se llama "Bono Daño Viento" en el cliente ES sino **"Bono de daño aéreo"**. El de Lumen es igual de impredecible. |

**Lo que se necesita:** un screenshot de S18 (perfil de un agente Lumen, pestaña
Atributos base) y, si aparece, un disco con main de daño Lumen.

Mientras tanto, un agente Lumen sería reconocido por nombre pero su elemento
caería a `None` en el parser.

### ⏸ B3 — Resistencias a viento/lumen de los 12 enemigos

El `CHECK` ya las admite; las filas entran cuando haya datos de Hakush.in.
Hoy `enemy_resistances` tiene 72 filas = 12 × 6; el completo sería 12 × 8 = 96.

### ⏸ B4 — Splash arts sin trackear

En el working dir principal hay splash arts **untracked** de PJs que no están en
`agents`: `Aria_extend.webp`, `Aria_ico.webp`, `Banyue`, `Hugo`,
`Lichter`/`Lighter`, `Promeia`, `Yidhari`. También `app/resources/avatar_refs/Aria.png`.
Decidir si entran al repo (ver `feedback_capturas_full_res_locales`: al `.gitignore`
en el mismo commit que las introduce, salvo que sean assets chicos de UI).

---

## Validación

- [x] Smoke test L1 pre-patch ok (`integrity_check=ok`, `foreign_key_check=0`)
- [x] Smoke test L1 post-migración 14 ok
- [x] Diff de counts pre vs post = sin cambios de filas
- [x] Suite de tests (ver §Cierre)
- [ ] Casos canónicos QA-07 §5 (8/8) — pendiente
- [ ] L4 toast disparado correctamente — pendiente sesión en vivo

## Cierre

- DB post-migración: `db/danibod_zzz_v2.db`
- Tag git: pendiente (`patch-v3.1-validated` cuando cierre la Fase C→H)
- ⚠️ **La DB vive versionada.** Esta migración se aplicó a la copia del worktree.
  El working dir principal (`D:\Proyectos\Zenless_analitycs`) tiene todavía la
  versión vieja: hay que `git pull` ahí después del merge, con la app cerrada.

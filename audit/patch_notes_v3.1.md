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
| C — onboarding de assets nuevos | ✅ Remielle Dan cargada (PARCIAL). Sigrid y Aria: Daniel no las sacó |
| D — UPDATE stats existentes | ⏸ sin cambios reportados |
| E — re-scrape | ⏸ pendiente |
| F — recálculos derivados | ⏸ pendiente |
| G — validación L1 final | ✅ post-mig 14 y 15: `integrity_check ok`, `foreign_key_check` 0, diff de counts explicado fila por fila |
| H — validación L4 con frames | 🟡 parcial: el frame de S18 del PJ nuevo parsea perfecto (ver §Vocabulario). Falta la sesión en vivo (toasts, F11) |
| I — docs | ✅ este doc + `project-context-IA.md` + `Modelo_Relacional/README.md` |
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

| PJ | En `agents` | Notas |
|----|-------------|-------|
| **Remielle Dan** | ✅ id 50 | Obtenida. Onboarding PARCIAL — ver §Acciones |
| Sigrid | ❌ no | Daniel no la sacó |
| Aria | ❌ no | Daniel no la sacó |

Roster: **49 → 50 agentes**.

**Nombre completo:** la pantalla dice **"Remielle Dan"**, no "Remielle". Se guarda
entero, como `Jane Doe` / `Zhu Yuan` / `Ju Fufu` / `Pan Yinhu`.

### Facción nueva: Covenant of Dayat

El texto ES en pantalla dice **"Alianza de Dayat"**; el logo dorado dice
**"COVENANT OF DAYAT"**. Se guardó el nombre del logo (decisión DaniBOD): 13 de
las 15 facciones de la tabla están en inglés, así que manda la convención
mayoritaria. Falta el asset del logo en `Documentacion/Interfaz/Facciones_Logos/`.

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

### ✅ Migración 15 — onboarding PARCIAL de Remielle Dan

Archivo: `db/migrations/2026-07-28_15_onboarding_remielle_dan.sql`
Backup previo: `db/danibod_zzz_v2.backup_premig_20260729_021703.db`
Fuente única (RNF-02): `Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_15.png`

**S · Lumen · Anomalía · Covenant of Dayat · M0 (CINEMA 0/6) · Nivel 01.**
El rango sale del badge dorado del header — verificado contra el mismo badge de
Pyrois, que muestra `∞` y coincide con su `agents.rango`.

Stats cargados (Nivel 01, **sin discos equipados** → base puros; más limpios que
los de Pyrois, que tenía discos al azar):

| | | | |
|---|---|---|---|
| PV 602 | Ataque 124 | Defensa 48 | Impacto 83 |
| Prob. Crítico 5 % | Daño Crítico 50 % | Tasa de Anomalía 115 | Maestría de Anomalía 116 |
| Tasa de Perforación 0 % | Recup. Energía 1.2 | | |

`perforacion` plana y `bono_dano_elemento` no se exponen en pantalla → NULL.
`agent_thresholds` no se cargan: son objetivos de build y Prydwen todavía no
publicó a Remielle a <24 h del release (RNF-02).

Se cargaron además: `agent_score_thresholds` (0.75/0.50 default),
`agent_awakenings` (placeholder v3.1) y las 6 filas de `pj_weapon_synergy` con la
BONUS_MATRIX del rol Anomalía (bonus y razones espejo de los PJs Anomalía ya
cargados, modelo Burnice).

**Verificación:** 9/9 smoke checks, `integrity_check ok`, `foreign_key_check` 0.
Diff de counts pre-patch → post-patch, exactamente 4 deltas y nada más:

```
agents                 49 -> 50  (+1)
agent_score_thresholds 49 -> 50  (+1)
agent_awakenings        9 -> 10  (+1)
pj_weapon_synergy     282 -> 288 (+6)
```

### ✅ Vocabulario de código para Lumen — la pantalla dice "Lumiflujo"

El riesgo marcado en la sesión anterior se confirmó: **el elemento NO se rotula
"Lumen" en pantalla, se rotula "Lumiflujo"**. Adivinarlo habría fallado, y en
silencio.

`app/core/parser_agent_stats.py`:
- `_ELEMENTOS_DB` += `"lumen"`
- `_ELEMENTO_SCREEN_MAP` += `"lumiflujo" → "Lumen"`, igual que Ígneo→Fuego y
  Etéreo→Éter.

Tests nuevos en `test_parser_agent_stats.py` (escritos primero, en rojo):
`test_canon_elemento_lumiflujo_es_lumen` y
`test_lumiflujo_no_le_roba_el_match_a_otro_elemento` (blinda el orden del dict,
que es significativo porque `_canon_elemento` corta en el primer substring).

**Prueba end-to-end sobre el frame real** (no solo unit test) — `parse_agent_stats`
+ PaddleOCR sobre `atributos_base_ejemplo_15.png` devuelve:

```
agente_nombre        = 'Remielle Dan'
elemento             = 'Lumen'
rol                  = 'Anomalía'
pv/ataque/defensa/impacto = 602 / 124 / 48 / 83
prob_crit/dano_crit  = 0.05 / 0.5
tasa_anomalia/maestria = 115 / 116
tasa_perforacion/rec_energia = 0.0 / 1.2
confianza_global     = 0.977
notas                = ['identificado_por_stats_Remielle Dan', 'agente_Remielle Dan_rol_Anomalía']
```

Los 10 stats coinciden con lo cargado en DB, y el `identificado_por_stats` cierra
el lazo: el reconocimiento en S18 ya funciona contra la fila nueva.

### 🐛 Corrección de un docstring que mentía

`parser_agent_stats.py` decía que el slot bottom-left de S18 muestra *Fuerza
Bruta* para **Anomalía/Disruptivos**. Remielle es Anomalía y muestra **"Tasa de
Perforación 0 %"**. El código siempre estuvo bien (`_STATS_DISRUPTIVO` aplica solo
a Disruptivos; `_STATS_RESTO` cubre a Anomalía); era el docstring el que estaba
mal. Corregido.

---

## Bloqueado / pendiente

### ✅ B2 — CERRADO: el main de daño Lumen **no existe**

Confirmado in-game por DaniBOD el 2026-07-29: **no hay disco con main "Bono Daño
Lumen"** ni equivalente. Lumen es el **único de los 7 elementos sin bono de daño
elemental en slot 5**.

No es un no-hallazgo, es un dato con consecuencia: un agente Lumen (hoy Remielle
Dan) no puede sacar bono de daño elemental del slot 5 — sus mains posibles ahí
son solo HP% / ATK% / DEF% / Tasa de Perforación. Cuando RF-06 puntúe discos para
ella, no hay que buscarle un main que no existe.

Y como en la lista de slot 5 la ausencia *parece* un hueco a completar, quedó
fijada en dos lados para que nadie la "arregle" adivinando:

- Comentario explícito en `CANONICAL_MAINS_VARIABLE[5]` (`app/core/stats_vocab.py`).
- Contrato en test: `test_slot5_no_tiene_bono_de_dano_lumen`
  (`app/tests/unit/test_stats_vocab.py`) — 22 passed.

Si algún día ZZZ lo agrega, hace falta una **captura** del disco para saber el
rótulo: el del elemento resultó ser "Lumiflujo" y el main de Viento es "Bono de
daño aéreo", así que el nombre no se deduce.

### ✅ B7b — Niveles de despertar confirmados (migración 17)

DaniBOD confirmó in-game el 2026-07-29 el estado de su tienda Silueta Potencial,
lo que cerró los 5 `nivel IS NULL` de la migración 16:

| Nivel | PJs |
|-------|-----|
| **6/6** | Burnice · Ellen · Grace · Jane · Lycaon · N.º 0: Anby · Rina (7) |
| **1/6** | N.º 11 (1) — ⚠️ parcial |
| **0/6** | Billy Estelar · Cissia · Harumasa · Nekomata · Pyrois · Remielle Dan · Velina (7) |

Mapeo de nombres — los del reporte no son los de la DB: "Jane Doe" → `Jane`,
"Ellen Joe" → `Ellen`, "N°0 Anby" → `N.º 0: Anby`. **No se renombró nada**: el
resolver de assets y el latch de identidad keyean por `agents.nombre` (hay
overrides tipo `Jane` → `Jane-Doe-*.webp`), así que tocarlo rompería la cosecha
de badges.

Nekomata y Harumasa pasaron a `placeholder` (no a `pending_capture`): con 0
niveles comprados no hay texto que capturar. La diferencia con los otros
placeholder —que para estos dos el despertar **sí existe y es comprable** desde
v3.1— quedó en `descripcion`.

Solo UPDATEs: el diff de counts no movió una sola fila. Invariante nuevo
verificado: `activo=1` ⟺ `nivel>0` (0 filas incoherentes).

**Ellen quedó explicada:** estaba en DB y no en la lista de "nuevos" porque su
despertar es de una tanda anterior; el reporte la confirma en 6/6.

### ⏸ B7c — La deuda que queda: 7 textos de efecto

Los niveles ya están. Lo que falta es el **efecto**: de las 15 filas, **una sola
(Burnice) tiene texto real**. Las otras 7 con nivel > 0 están en
`pending_capture` — la tabla hoy inventaria la deuda, no alimenta scoring.

⚠️ **Al capturar N.º 11 hay que anotar a qué nivel corresponde el texto.** Está
en 1/6 y el despertar es progresivo: si se carga el texto sin el nivel, el
scoring va a asumir el efecto completo.

### ✅ B7a — Despertares v3.1: las 5 filas que faltaban

Migración 16 (`db/migrations/2026-07-29_16_awakenings_v31_pendientes.sql`).
DaniBOD reportó despertares nuevos para 8 PJs; **3 ya tenían fila** (Lycaon,
N.º 0: Anby, Grace, en nv6 `pending_capture`) y **no se tocaron** — sobrescribir
datos confirmados a partir de un "creo que" es lo que prohíbe RNF-02. Se
insertaron las 5 que faltaban: N.º 11, Harumasa, Nekomata, Rina, Jane.

**`nivel` va en NULL a propósito.** El modelo venía usando dos estados
(`nivel=6/activo=1/pending_capture` = lo tiene full; `nivel=0/activo=0/placeholder`
= no tiene) y ninguno describe la situación real: el despertar **existe en el
juego**, pero no está confirmado si Daniel lo compró ni a qué nivel. Poner 0 o 6
sería afirmar algo que no sabemos. `activo=0` por conservador — el scoring no
debe asumir un buff que puede no existir.

Precedente: estas dos ya se habían dejado deliberadamente sin insertar por lo
mismo (la nota vieja decía *"Harumasa y N.°11 sin insertar hasta confirmar nivel"*).

`agent_awakenings`: 10 → 15. **Deuda real: 9 filas en `pending_capture`** — de las
15, solo **una** (Burnice) tiene texto de efecto de verdad. Sin ese texto la tabla
sirve para inventariar la deuda, no para alimentar scoring.

**Lo que se necesita:** capturas de la tienda Silueta Potencial por PJ. El nivel
se lee ahí mismo ("Agotado" = nv6, "Límite ×N" = parcial). Ojo: el sistema de
despertares **no tiene captura implementada** (cero referencias a
`awakening`/`silueta`/`despertar` en `app/core`), así que la carga es manual.

Sin verificar: la lista vino con un *"creo que esos eran los nuevos"*. Además
**Ellen** tiene despertar en DB y no estaba en la lista.

### ⏸ B3 — Resistencias a viento/lumen de los 12 enemigos

El `CHECK` ya las admite; las filas entran cuando haya datos de Hakush.in.
Hoy `enemy_resistances` tiene 72 filas = 12 × 6; el completo sería 12 × 8 = 96.

### 🔴 B5 — Assets de Remielle Dan: **hay un test en rojo por esto**

`test_asset_resolver.py::test_full_coverage_against_db` falla desde que entró la
fila 50:

```
AssertionError: Agentes sin -extend.webp: ['Remielle Dan']
```

**El test tiene razón y no se tocó.** Es el guard que exige que todo agente de la
DB tenga sus splash; el comentario del propio test dice que `-extend`/`-ico`
nunca se difieren (a diferencia de `Pj_stats`, que sí tiene su
`_PJ_STATS_DEFERIDO` para onboardings parciales). Ese guard ya atajó un bug real
antes — sin él, a Jane se le disimulaba el faltante cayendo al JPEG de Pj_stats.
Meter a Remielle en una lista de excepción lo dejaría mudo, así que se prefirió
dejar la falla visible.

**Se destraba dejando dos archivos** en `Documentacion/Interfaz/splash_arts/`,
con estos nombres exactos (los deriva `_normalize_for_splash('Remielle Dan')`):

- `Remielle-Dan-extend.webp`
- `Remielle-Dan-ico.webp`

Sin código de por medio: en cuanto estén, el test pasa solo.

También faltan, sin test que los exija todavía:
- `app/resources/avatar_refs/Remielle Dan.png` — **sin esto no se la reconoce
  como dueña de discos** (hoy hay 54 refs y ninguna es suya).
- El logo de Covenant of Dayat en `Documentacion/Interfaz/Facciones_Logos/`
  (Faetón, de Pyrois, arrastra el mismo faltante).

### ⏸ B6 — Catalogación IA: 49 pares nuevos

Remielle Dan agrega 49 pares a `team_synergies` (1 contra cada PJ del roster).
`team_synergies` está en 0 filas — el sistema RF-12 todavía no corrió nunca, así
que esto no es deuda específica del patch.

### ⏸ B4 — Splash arts sin trackear

En el working dir principal hay splash arts **untracked** de PJs que no están en
`agents`: `Aria_extend.webp`, `Aria_ico.webp`, `Banyue`, `Hugo`,
`Lichter`/`Lighter`, `Promeia`, `Yidhari`. También `app/resources/avatar_refs/Aria.png`.
Decidir si entran al repo (ver `feedback_capturas_full_res_locales`: al `.gitignore`
en el mismo commit que las introduce, salvo que sean assets chicos de UI).

---

## Validación

- [x] Smoke test L1 pre-patch ok (`integrity_check=ok`, `foreign_key_check=0`)
- [x] Smoke test L1 post-migración 14 y post-migración 15 ok
- [x] Diff de counts: mig 14 sin cambios de filas; mig 15 con exactamente los 4 deltas esperados
- [x] Prueba funcional del CHECK ampliado (insert + rollback)
- [x] Prueba end-to-end del parser sobre el frame real del PJ nuevo
- [x] Suite de tests (ver §Cierre)
- [ ] Casos canónicos QA-07 §5 (8/8) — pendiente
- [ ] L4 toast disparado correctamente — pendiente sesión en vivo

## Suite de tests

| Corrida | Resultado |
|---------|-----------|
| Pre-patch (baseline) | 1141 passed · 21 failed |
| Post-mig 14 y 15 | **1178 passed · 22 failed** |
| `test_parser_agent_stats.py` (archivo tocado, corrida aparte con el fixture nuevo) | **78 passed** |

De los 22 rojos, **21 son preexistentes**: `FileNotFoundError` de las fixtures de
desmontaje (`12_Desmontaje/Ejemplo_2/3/4/6.png`), que están *untracked* en el
working dir principal y por eso no existen en el worktree. No son regresión.

El rojo **nº 22 es nuevo y es mío**: `test_asset_resolver::test_full_coverage_against_db`,
por los splash de Remielle Dan que faltan. Ver §B5 — se resuelve dejando dos
`.webp`, sin tocar código.

## Cierre

- DB post-migración: `db/danibod_zzz_v2.db`
- Tag git: pendiente (`patch-v3.1-validated` cuando cierre la Fase C→H)
- ⚠️ **La DB vive versionada.** Esta migración se aplicó a la copia del worktree.
  El working dir principal (`D:\Proyectos\Zenless_analitycs`) tiene todavía la
  versión vieja: hay que `git pull` ahí después del merge, con la app cerrada.

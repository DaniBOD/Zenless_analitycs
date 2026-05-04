# QA-07 — Regresión por patches de ZZZ

**Capa:** L1 (integridad post-cambio) + L4 (real con frames del nuevo patch) + L5 (cruzada con Prydwen/Hakush actualizados).
**Frecuencia:** cada patch del juego (~6 semanas).
**Cuándo consultar:** el día que HoYoverse publica una versión nueva, ANTES de tocar nada del proyecto.

> **Principio:** un patch de ZZZ puede romper sutilmente cualquier capa: cambia stats de un PJ, agrega un set, renombra un W-Engine, mueve un texto en la UI, ajusta enemigos en Shiyu. Sin checklist, los bugs llegan al toast como recomendaciones desactualizadas. Esta lista es el sello de calidad post-patch.

---

## 1. Workflow general por patch

```
[Patch ZZZ publicado]
      ↓
[Snapshot DB pre-patch]    ← backup obligatorio
      ↓
[Leer patch notes oficiales + Prydwen + Game8]
      ↓
[Clasificar cambios por capa afectada]   ← §2 matriz de impacto
      ↓
[Aplicar onboarding por cada asset nuevo]   ← Documentacion/Onboarding_*
      ↓
[Re-scrapear Prydwen + Hakush.in]
      ↓
[Re-evaluar tier list personal]
      ↓
[Re-catalogación IA delta]   ← solo pares afectados, no todo
      ↓
[Validación L4 con frames reales del patch]
      ↓
[Cerrar checklist + actualizar README + project-context-IA]
```

---

## 2. Matriz de impacto por tipo de cambio

Mapeo "patch dice X → afecta tabla Y → ejecutar paso Z":

| Cambio en patch | Tablas afectadas | Acción QA |
|-----------------|------------------|-----------|
| **PJ nuevo** (S/A) | `agents`, `agent_thresholds`, `agent_score_thresholds`, `pj_weapon_synergy`, `team_synergies` (44 pares nuevos), `team_compositions` | Onboarding_Nuevo_PJ.md (8 pasos) + RF-12 batch para los 44 pares |
| **W-Engine nueva** | `weapons`, `weapon_passives_structured`, `weapon_evaluations`, `prydwen_weapon_recommendations_snapshots` | Onboarding_Nuevos_Assets.md §W-Engine + recálculo `weapon_evaluations` |
| **Set de discos nuevo** | `disc_sets`, `disc_set_archetype`, re-evaluación `inventory_discs` | Onboarding_Nuevos_Assets.md §Set + re-scoring de inventario |
| **Stats efectivos cambian** (rebalance de PJ) | `agents`, `agent_thresholds` | Re-capturar HoYoLAB del PJ + UPDATE stats |
| **Awakening nuevo desbloqueado** | `agent_awakenings` | Manual: capturar texto in-game (RNF-02) |
| **Set bonus rebalanceado** | `disc_sets.bonus_4p_desc`, scoring engine pesos | UPDATE bonus + revisar arquetipo asignado |
| **Pasiva de W-Engine cambiada** | `weapons.pasiva_*`, `weapon_passives_structured` | UPDATE + recalcular `weapon_evaluations` |
| **Enemigos / boss nuevos en Shiyu/DA** | `enemies`, `enemy_resistances`, `shiyu_cycles`/`da_cycles` | `scrape_enemies.py` + insert |
| **Ciclos rotativos cambian** | `shiyu_cycles`, `da_cycles` | `scrape_prydwen_*` |
| **Texto UI in-game cambia** (afecta OCR triggers) | templates en `app/resources/templates/` | Re-capturar templates + re-tunear thresholds detector |
| **Tier list de Prydwen cambia significativamente** | `prydwen_tier_snapshots` | scraper semanal recoge automáticamente |
| **Translation strings ajustadas** (set/W-Engine renombrado) | `disc_sets.nombre`, `weapons.nombre` | Migración tipo merge id (con backup) |

---

## 3. Checklist por patch (paso a paso)

### Fase A — preparación (antes de tocar nada)

- [ ] **Backup completo de DB:**
  ```bash
  TS=$(date +%Y%m%d_%H%M%S)
  cp db/danibod_zzz_v2.db "db/danibod_zzz_v2.backup_prepatch_${TS}.db"
  ```
- [ ] **Snapshot de filas:** `python app/scripts/qa/snapshot_counts.py > Documentacion/QA/evidencia/baseline_prepatch_${TS}.json`.
- [ ] **Ejecutar smoke test L1** (ver QA-01 §1) — debe pasar antes de empezar.
- [ ] **Tag git** opcional: `git tag patch-vX.X-prebackup`.

### Fase B — lectura del patch

- [ ] Patch notes oficiales (HoYoLAB / sitio del juego).
- [ ] Cobertura Prydwen ("Whats new in vX.X").
- [ ] Hakush.in datamine para enemigos/HP.
- [ ] Game8 para sinergias detectadas por la comunidad.
- [ ] **Anotar en `audit/patch_notes_vX.X.md`** una lista de cambios clasificados por matriz §2.

### Fase C — onboarding de assets nuevos

Por cada asset nuevo identificado:

- [ ] PJ nuevo → seguir `Documentacion/Onboarding_Nuevo_PJ.md` completo (8 pasos).
  - Verificar cierre con: `SELECT COUNT(*) FROM agents` + 1 por cada PJ nuevo.
- [ ] W-Engine nueva → `Documentacion/Onboarding_Nuevos_Assets.md` §W-Engine.
  - Verificar: `SELECT COUNT(*) FROM weapons` + N nuevas.
- [ ] Set nuevo → `Onboarding_Nuevos_Assets.md` §Set.
  - Verificar: `SELECT COUNT(*) FROM disc_sets` + 1.
  - Re-scorear inventario afectado: tras seed `disc_set_archetype`, recorrer `inventory_discs.set_id=N` y recalcular `score_evaluacion`.
- [ ] Facción nueva → `Onboarding_Nuevos_Assets.md` §Facción + actualizar logos en `Documentacion/Interfaz/Facciones_Logos/`.

### Fase D — actualizaciones de stats existentes

- [ ] Re-capturar screenshots HoYoLAB para cada PJ con cambios de stats.
- [ ] UPDATE en `agents` (campo a campo, dentro de transacción).
- [ ] Validar que thresholds vigentes siguen siendo coherentes (ver QA-01 §3).
- [ ] Documentar en README §6 cualquier stat que cruzó el umbral mín/óptimo.

### Fase E — re-scrape

- [ ] **Hakush.in enemies** (si hay enemigos nuevos):
  ```bash
  python app/scripts/scrape_enemies.py --refresh-all
  ```
  Validar: `SELECT COUNT(*) FROM enemies` ≥ 80; `enemy_resistances` = 6×enemies.
- [ ] **Prydwen tier list:**
  ```bash
  python app/scripts/scrape_prydwen_tierlist.py --force
  ```
  Validar: nuevo `prydwen_tier_snapshots` con timestamp del scrape.
- [ ] **Prydwen weapons (si hubo armas nuevas o ajustes):**
  ```bash
  python app/scripts/scrape_prydwen_weapons.py --force
  ```

### Fase F — recálculos derivados

- [ ] **`tier_list_personal`:**
  ```python
  tier_list_calculator.recalculate_all()
  ```
  Si no hay runs nuevos suficientes, los PJs nuevos quedan `insufficient_data` (esperado).
- [ ] **`weapon_evaluations`:**
  ```python
  weapon_optimizer.recalc_all_evaluations()
  ```
  Latencia esperada <8s.
- [ ] **`team_synergies` delta** — solo pares que involucran a los nuevos assets:
  ```python
  ai_catalog.refresh_for_new_pj(new_pj_id)   # 44 pares nuevos
  ai_catalog.refresh_for_new_set(new_set_id) # solo pares con cambios visibles
  ```
  Cap respetado (QA-04 §5.1). NO refresh trimestral completo en cada patch — solo cuando hay rebalance grande.
- [ ] **Re-scoring de `inventory_discs`** afectados por sets nuevos / pesos cambiados:
  ```python
  for d in inventory_discs:
      if d.set_id in sets_changed or d.agente_asignado in pjs_changed:
          rescore(d)
  ```

### Fase G — validación L1 final

- [ ] Smoke test (QA-01 §1) — `integrity_check ok`, `foreign_key_check 0`.
- [ ] Snapshot de filas:
  ```bash
  python app/scripts/qa/snapshot_counts.py > Documentacion/QA/evidencia/baseline_postpatch_${TS}.json
  ```
- [ ] Diff vs baseline pre-patch — entender cada cambio:
  ```bash
  diff Documentacion/QA/evidencia/baseline_prepatch_${TS}.json \
       Documentacion/QA/evidencia/baseline_postpatch_${TS}.json
  ```

### Fase H — validación L4 con frames del patch

- [ ] Capturar nuevos frames si la UI cambió:
  - Pantalla de resultado de disco.
  - Pantalla de upgrade (PRE/POST).
  - Pantalla de Battle Stats lategame.
- [ ] Verificar templates en `app/resources/templates/` — actualizar si hay drift.
- [ ] **Test de detector** (QA-03 §2.2) sin falsos positivos.
- [ ] **Test OCR** (QA-03 §3) sobre fixtures actualizadas — precisión ≥ 0.95.
- [ ] **Sesión real con ZZZ del nuevo patch:**
  - 5 toasts de discos disparados sin error.
  - 3 runs lategame capturados con F11.
  - 1 cambio de equipo via RF-04.

### Fase I — actualización de documentación

- [ ] **README.md §2 Estado Actual** — agregar línea "Cerrado (Fase patch vX.X, fecha)".
- [ ] **README.md §5 Roster** — actualizar tabla si hubo PJs nuevos o cambios.
- [ ] **project-context-IA.md §3** — actualizar conteos de filas.
- [ ] **`audit/patch_notes_vX.X.md`** — cerrar con resumen y validar checklist completo.
- [ ] Tag git: `git tag patch-vX.X-validated`.

### Fase J — comunicación al sistema (RF-12 / RF-13 auto-encolado)

- [ ] **RF-04 detecta PJ nuevo** durante próxima sesión → encola refresh RF-12 (44 pares) automáticamente.
  - Validar: panel "Equipos" muestra "Catalogación pendiente: 44 pares" para el PJ nuevo.
- [ ] **RF-13** vuelve a calibrar tras 3 runs nuevos → notificación "Tier list recalculado tras patch vX.X".

---

## 4. Tiempos esperados por fase

Para un patch típico (1 PJ S-rank + 1 W-Engine S-rank + 1 set nuevo):

| Fase | Tiempo estimado | Bloqueante |
|------|----------------|------------|
| A — preparación | 5 min | sí |
| B — lectura patch | 30-60 min | parcial |
| C — onboarding nuevos | 60-90 min | sí (RNF-02 manual) |
| D — UPDATE stats | 30 min | sí |
| E — re-scrape | 5-10 min (background) | no |
| F — recálculos | 10-20 min | parcial |
| G — validación L1 | 5 min | sí |
| H — validación L4 | 30 min en juego | sí |
| I — docs | 15 min | sí |
| J — auto-encolado | runtime | no |
| **Total** | **3-4 horas** | — |

Si el patch trae rebalance masivo (ej. el v2.5 con awakenings introducidos), sumar tiempo para revisar arquetipos.

---

## 5. Casos canónicos a re-validar tras CADA patch

Estos golden cases deben seguir pasando — son la red de seguridad anti-regresión:

| Test | Criterio |
|------|----------|
| QA-01 §3.1 — equipados consistentes | inv_eq = slots no-EMPTY |
| QA-02 §2 — scoring determinista | mismo input → mismo score |
| QA-02 §4.1 — caso "la roca" | S+ DA / B HZ |
| QA-04 §3.1 — Ellen+Dialyn → Puffer Electro | confianza ≥ 0.85 |
| QA-04 §3.4 — Antón+Zhao sin sinergia | sinergia_existe=False |
| QA-05 §3.2 — buckets fijos | S+ ≥90, S 80-89, etc. |
| QA-05 §5.2 — bayesiano Ellen+Dialyn 5 runs | confianza_post ∈ [0.40, 0.55] |
| QA-06 §3 — pipeline disco→toast | p99 < 500 ms |

Si alguno falla post-patch, **no cerrar la regresión** hasta entender la causa:
- ¿Es porque el juego cambió y la expectativa antigua quedó obsoleta? → Actualizar el caso canónico, **documentar** el cambio.
- ¿Es bug introducido? → Fix antes de cerrar.

---

## 6. Patches que requieren más cuidado

| Tipo de patch | Por qué | Atención extra |
|---------------|---------|----------------|
| Patch X.0 (mayor) | Rebalance global, mecánicas nuevas | Refresh trimestral completo de RF-12 (~$21) en lugar de delta |
| Patch con awakening masivo | Pueden cambiar ER thresholds del roster | Re-validar §6 thresholds del README |
| Patch con sistema completamente nuevo (tipo Hollow Zero v2) | Puede requerir tabla nueva o `content_profiles` extra | Migración SQL formal con su QA-01 |
| Patch que renombra sets/armas | Rompe joins por nombre si hubieran | Validar que todo está por ID, no por nombre |
| Patch que cambia formato de Battle Stats | Rompe OCR breakdown DMG (RF-13) | Re-capturar fixtures + re-tunear |

---

## 7. Plantilla `audit/patch_notes_vX.X.md`

```markdown
# Patch vX.X — notas de regresión

**Fecha publicación:** YYYY-MM-DD
**Fecha aplicado a DaniBOD:** YYYY-MM-DD
**Backup pre-patch:** db/danibod_zzz_v2.backup_prepatch_<TS>.db

## Cambios identificados

### PJs nuevos
- Nombre, rango, elemento, rol, facción.

### W-Engines nuevas
- Nombre, rareza, especialidad, pasiva resumida.

### Sets nuevos
- Nombre, bonus 2pc, bonus 4pc.

### Stats / pasivas cambiadas
- PJ: cambio.

### UI / OCR drift
- Pantalla / qué cambió.

## Acciones ejecutadas

- [ ] Onboarding PJs (referencias commits)
- [ ] Onboarding W-Engines
- [ ] ...

## Validación

- [ ] Smoke test L1 ok
- [ ] Casos canónicos QA-07 §5 pasan
- [ ] L4 toast disparado correctamente

## Cierre

- DB post-patch: `db/danibod_zzz_v2.db`
- Snapshot rows: `Documentacion/QA/evidencia/baseline_postpatch_<TS>.json`
- Tag git: `patch-vX.X-validated`
```

---

## 8. Frecuencia de regresiones más livianas (sin patch del juego)

Aunque no haya patch nuevo, hay rutinas semanales/mensuales:

| Frecuencia | Acción | Doc |
|------------|--------|-----|
| Semanal (domingo 03:00) | scrape Prydwen tier list + recálculo `tier_list_personal` | RF-13 + QA-05 |
| Semanal | scrape Prydwen weapons (45 PJs, <90 s) | RF-14 |
| Mensual | revisar `agent_awakenings.descripcion='pending_capture'` con >30 días sin actualizar | QA-01 §7 |
| Mensual | revisar costo IA acumulado (`SUM(costo_usd) FROM ai_catalog_runs WHERE ts >= mes`) | QA-04 §5 |
| Trimestral | test de restauración de backups | QA-01 §8 |
| Trimestral | refresh completo `weapon_evaluations` | RF-14 |

---

## 9. Cobertura mínima para considerar el sistema "estable post-patch"

- [ ] Checklist §3 completado de Fase A a Fase J.
- [ ] Casos canónicos §5 pasan (8/8).
- [ ] Audit `patch_notes_vX.X.md` archivado.
- [ ] Tag git puesto.
- [ ] README §2 actualizado.
- [ ] L4 Daniel: 1 sesión jugada con la app activa sin error percibido.

---

*Cada patch es una mini-implementación. Tratarlo como tal evita que la deuda técnica acumule lentamente hasta que un día el sistema deja de ser confiable.*

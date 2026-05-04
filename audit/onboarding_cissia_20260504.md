# Onboarding Cissia — 2026-05-04

**Trigger:** Daniel obtuvo y equipó a Cissia. Subió `Pj_stats/Cissia.jpeg` (HoYoLAB) y capturó 2 discos nuevos (slots 4 y 6); slots 1, 2, 3, 5 ya estaban en el inventario.

**Estado:** ✅ SQL listo con todos los datos confirmados. Pendiente solo backup + ejecución desde Windows.

---

## 1. Datos extraídos del screenshot HoYoLAB (`Pj_stats/Cissia.jpeg`)

### Identidad
| Campo | Valor | Fuente |
|-------|-------|--------|
| Nombre | Cissia | screenshot |
| Rango | S | screenshot (badge S+ es del build, no del rango) |
| Nivel | 60 | screenshot |
| Elemento | Eléctrico | screenshot (icono ⚡ + Bono Daño Eléctrico 30%) |
| UID validado | 1000860143 | coincide con `project-context-IA.md §1` |

### Stats efectivos (con W-Engine + 6 discos lvl 15 equipados)
| Stat | Valor | Notas |
|------|------:|-------|
| PV | **10 788** | base 7 673 + 3 115 de discos |
| Ataque | **2 178** | base 1 562 + 616 |
| Defensa | **849** | base 606 + 243 |
| Impacto | 93 | bajo → no es Aturdidor |
| Probabilidad Crítica | **48.2 %** | alto → build crit-heavy |
| Daño Crítico | **126.8 %** | alto |
| Tasa de Anomalía | 94 | medio |
| Maestría de Anomalía | **147** | medio (ANOMALY puro tendría > 250) |
| Tasa de Perforación | 0.0 % | sin perforación % |
| Perforación | 36 | flat — chico |
| Recuperación de Energía | **3.58** | base 1.56 + 2.02 (boost del 4pc Floración?) |
| Bono Daño Eléctrico | **30.0 %** | confirmación de elemento |

### W-Engine equipada
- **Taladradora giratoria - Eje** (`weapon_id=41`, rareza A)
- Nivel 60, refinamiento R5 (P5)
- En inglés: "Drill Rig - Red Axis" — A-rank, ATK% scaler

### Build de discos (4pc + 2pc)
| Slot | Set | Main stat | Match en DB |
|------|-----|-----------|-------------|
| 1 | Floración del alba (29) | PV 2200 | `inventory_discs.id=261` (suelto → asignar) |
| 2 | Floración del alba (29) | Ataque 316 | `inventory_discs.id=263` (suelto → asignar) |
| 3 | Nana a la luz cenicienta (35) | Defensa 184 | `inventory_discs.id=259` (suelto → asignar) |
| **4** | **Floración del alba (29)** | **Prob. Crítica 24%** | **NUEVO — INSERT** |
| 5 | Floración del alba (29) | Bono Daño Eléctrico 30% | `inventory_discs.id=268` (suelto → asignar) |
| **6** | **Nana a la luz cenicienta (35)** | **Recuperación de Energía 60%** | **NUEVO — INSERT** |

### Skill levels (no se persisten en v1 — `agents` no tiene columnas)
12 / 09 / 10 / 12 / 12 / 07 (Skill básico / Esquive / Asistencia / Especial / Cadena / Núcleo)

> Si más adelante la app necesita skill levels, agregar columnas en migración futura. No bloqueante.

---

## 2. Validación cruzada con sets en DB

### Mapeo set → arquetipo
- **Floración del alba (29)** → primario `ATK_DPS` (Atacante ATK-scaler)
- **Nana a la luz cenicienta (35)** → primario `SUPPORT_ER` (Soporte de energía)

**Lectura:** Cissia corre build de **Crit-DPS con 2pc de boost ER**. Eso, sumado a:
- W-Engine Drill Rig - Red Axis (ATK%-scaler)
- Crit Rate 48 / Crit DMG 127 (alto)
- MA solo 147 (no es Anomaly puro)

→ **Probabilidad alta de que Cissia sea rol "Ataque" y arquetipo `ATK_DPS`** (no `ANOMALY` aunque sea eléctrica).

⚠️ **Hipótesis a confirmar por el usuario** (RNF-02 prohibe inferir rol oficial sin fuente).

---

## 3. Datos confirmados por usuario (2026-05-04)

| # | Campo | Valor confirmado | Decisión de modelado |
|---|-------|------------------|---------------------|
| Q1 | `mindscape` | **0** | M0, sin nodos desbloqueados |
| Q2 | `rol` | **Ataque** | Confirma la hipótesis del build crit-DPS. Arquetipo `ATK_DPS` por regla por rol (Onboarding §5). |
| Q3 | `faccion` | **CRIT** (`Criminal Investigation Special Response Team`) — misma facción que Seth, Qingyi, Zhu Yuan, Jane Doe | Caso especial: tiene logo propio "Metropolitan Order Division" (sub-división dentro de N.E.P.S.), patrón análogo a Jane Doe. La columna `agents.faccion` mantiene la facción paraguas (consistencia de filtros); la variante visual queda registrada en `agents.notas` + en el README de `Facciones_Logos/`. |
| Q4 | `version_juego` | **v2.7** | Patch de la primera mitad de mayo 2026 (cycle Shiyu C12 actual). |

**Awakening:** Cissia v2.7 **no tiene awakening desbloqueado** (placeholder `activo=0`).

### Logo nuevo agregado al proyecto
- Archivo: `Documentacion/Interfaz/Facciones_Logos/Faction_Metropolitan_Order_Division_Icon.webp` (17 KB)
- Diseño visual: estrella azul/dorada con cabeza de león/fiera, texto "Metropolitan Order Division" + "N.E.P.S." (New Eridu Public Security)
- Asociación: Cissia (en `agents.notas`)
- Documentación: README de `Facciones_Logos/` actualizado §"Logos variante / extras"

### Hallazgo colateral: Sporos NO es Cissia (corrección histórica)
Una nota anterior en `Documentacion/Interfaz/Facciones_Logos/README.md` asumía tentativamente que "Sporos" era la traducción/alias en español de "Cissia". Tras verificar `Pj_stats/Sporos.jpeg`, se confirma que son PJs **distintos**:

| | Cissia | Sporos |
|--|--------|--------|
| Rango | S | S |
| Elemento | Eléctrico | Eléctrico (?? Bono = 0.0%) |
| Crit Rate / CDmg | 48.2 / 126.8 | 66.6 / 184.4 |
| Maestría Anomalía | 147 | 147 |
| ER | 3.58 | 1.20 |
| Bono Eléctrico | 30.0% | 0.0% |
| W-Engine | Taladradora giratoria - Eje (A) R5 | Rotor de cañón (A) R-? |
| Build | 4pc Floración + 2pc Nana | 4pc Floración + 2pc Tecno Pícido |
| Facción (DB actual) | CRIT (post-onboarding) | Obol Squad |

El README de Facciones_Logos fue corregido para eliminar la confusión.

---

## 4. Operación SQL planeada

Archivo: [`db/migrations_pendientes/2026-05-04_onboarding_cissia.sql`](../db/migrations_pendientes/2026-05-04_onboarding_cissia.sql) — **listo para ejecutar**.

Estructura:
```
BEGIN TRANSACTION;
  1. INSERT agents (Cissia · S · Eléctrico · Ataque · M0 · CRIT · v2.7)
  2. INSERT agent_thresholds (5 stats — perfil Crit-DPS Eléctrico)
  3. INSERT agent_score_thresholds (defaults 0.75 / 0.50)
  4. INSERT agent_awakenings (placeholder, activo=0, version_juego='v2.7')
  5. INSERT pj_weapon_synergy (6 filas — BONUS_MATRIX["Ataque"])
  6. UPDATE 4 discos sueltos (id 261, 263, 259, 268) → asignar a Cissia
  7. INSERT 2 discos nuevos (slot 4 + slot 6)
COMMIT;
PRAGMA foreign_key_check;
PRAGMA integrity_check;
+ 8 smoke checks (SELECT COUNT con expected_*)
```

### BONUS_MATRIX aplicada (rol Ataque, Onboarding §6)

| weapon_pasiva_tipo | bonus | Razón |
|--------------------|------:|-------|
| dmg_boost | 1.0 | DPS escala con multiplicadores de daño |
| crit | 1.5 | CR/CDmg es el pilar principal |
| atk_boost | 1.0 | ATK% escala el daño base |
| anomaly_proficiency | 0.3 | Cobertura mínima, no es su pilar |
| energy_regen | 0.4 | ER solo para uptime de skill |
| pen_ratio | 0.8 | Perforación útil contra enemigos lategame |

### Inconsistencias dejadas a propósito (las absorbe Fase 2.0.4)

Los 2 discos nuevos se insertan con la convención **mixta** actual (`%` como TEXT con sufijo, flat como REAL) — la misma que ya tienen los 332 discos preexistentes. La migración 06 + script de re-estandarización (Fase 2.0 del roadmap) los normaliza junto con los demás.

**No es deuda nueva**: simplemente no anticipamos el saneamiento al onboarding del PJ.

---

## 5. Cómo aplicar

```powershell
# 1. Backup obligatorio
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item db\danibod_zzz_v2.db db\danibod_zzz_v2.backup_premig_$ts.db

# 2. Aplicar (sqlite3 en PATH; si no, ajustar ruta)
sqlite3 db\danibod_zzz_v2.db ".read db/migrations_pendientes/2026-05-04_onboarding_cissia.sql"

# 3. Validar smoke checks — los 8 SELECT al final deben mostrar valores que coincidan
#    con los sufijos 'expected_*' de los nombres de columna.
#    Si alguno falla → restaurar desde backup y revisar.

# 4. Si todo OK:
Move-Item db\migrations_pendientes\2026-05-04_onboarding_cissia.sql `
          db\migrations\2026-05-04_06_onboarding_cissia.sql
```

Si todo OK:
- Mover el SQL aplicado a `db/migrations/2026-05-04_onboarding_cissia.sql`.
- Actualizar `project-context-IA.md §3`: `agents` 45 → 46, `inventory_discs` 332 → 334, `agent_thresholds` 103 → 108, `agent_score_thresholds` 45 → 46.
- Hacer commit en git con tag `onboarding-cissia` (post-init del repo).

---

## 6. Hallazgos colaterales (auditoría informal mientras armaba el SQL)

Mientras buscaba los 4 discos del screenshot en la DB, detecté inconsistencias adicionales que **refuerzan la necesidad de Fase 2.0**. Las dejo loggueadas acá para que el audit 2.0.1 las confirme:

1. **Substats imposibles ya cargados**: discos `id=54` (Nana s6, Yuzuha) y `id=185` (Nana s6, Nicole) tienen main `'Tasa Anomalía 30%'`. Pero según RF-04 §7.2.1, slot 6 NO permite Tasa de Anomalía como main (mains válidos: HP%, ATK%, DEF%, Maestría de Anomalía, Impacto, Recarga de Energía). Probable confusión OCR/transcripción entre "Tasa de Anomalía" y "Maestría de Anomalía".
2. **Nomenclatura inconsistente entre filas del mismo set**: en set 35 conviven `'Ataque %'` (con espacio), `'Ataque%'` (sin espacio), `'Defensa %'`, `'Defensa%'`, `'Prob Crítico'` (sin punto). Coherente con el hallazgo del roadmap §1.2.
3. **Algunos rolls=0 con valor distinto a base**: ej. `id=174` sub `'Ataque%=9.0/2'` significa rolls=2 → +9% de boost, pero el formato "9.0" sin sufijo parece flat. Es tema de parser cuando se aplique `parse_value()` en Fase 2.0.4.

Todo esto entra en el reporte de Hito 2.0.1 (`audit/inventory_discs_audit_*.md`). No bloquea el onboarding — la migración 06 + re-estandarización los corrige.

---

## 7. Próximos pasos inmediatos

1. ✅ ~~Confirmar los 4 valores Q1-Q4~~ — hecho.
2. ✅ ~~Rellenar el SQL + bloque `pj_weapon_synergy`~~ — hecho.
3. ✅ ~~Actualizar README de Facciones_Logos con Cissia + variante MOD~~ — hecho.
4. **Pendiente vos:** ejecutar el SQL desde Windows (backup → aplicar → validar smoke checks → mover a `db/migrations/`).
5. **Pendiente vos:** actualizar `project-context-IA.md §3` (counts post-aplicación):
   - `agents` 45 → **46**
   - `inventory_discs` 332 → **334**
   - `agent_thresholds` 103 → **108**
   - `agent_score_thresholds` 45 → **46**
   - `agent_awakenings` 5 → **6** (placeholder de Cissia)
   - `pj_weapon_synergy` 270 → **276** (6 nuevas filas)
6. **Después:** inicializar git con `tools\init_repo.ps1` (si todavía no lo hiciste) y commitear todo este conjunto.
7. **Después:** arrancar Hito 2.0.1 del roadmap (audit completo de `inventory_discs`).

---

*Cierre del onboarding parcial — DaniBOD ZZZ Analytics · 2026-05-04*

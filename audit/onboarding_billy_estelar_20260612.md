# Onboarding Billy Estelar — auditoría · 2026-06-12

**PJ:** Billy Estelar (display in-game "Billy Kid Estelar" / subtítulo "Billy Estelar", comunidad EN "Billy Starlight"). Banner actual v2.x, conseguido M0 por el usuario.
**Migración:** `db/migrations/2026-06-12_10_onboarding_billy_estelar.sql`
**Backup RNF-01:** `db/danibod_zzz_v2.backup_premig_20260612_140051.db`

## Motivación

Billy Estelar es S · Físico · **Disruptivos** (escala con HP/Fuerza Bruta, no ATK — patrón Manato). NO debe confundirse con **Billy** (id 12, A · Físico · Ataque). Antes del onboarding el sistema lo identificaba como "Billy" (único match de roster), corrompiendo refs de badge + ground truth.

## Datos cargados (confirmados — screenshot del usuario, build M0)

| Campo | Valor |
|---|---|
| id / nombre | 47 / `Billy Estelar` |
| rango · elemento · rol | S · Físico · Disruptivos |
| facción | Cunning Hares (banner "Liebres Astutas"; logo "Gentle House" — **a verificar**) |
| mindscape | 0 (Cinema 0/6) |
| PV · ATK · DEF · Impacto | 20573 · 2043 · 689 · 95 |
| CR · CDmg | 72.2% · 118.8% |
| Tasa/Maestría Anomalía | 90 · 89 |
| (sin columna) | Fuerza Bruta 2669 · Acumulación Adrenalina 2 |

PV 20573 es **distintivo** en el roster (2º más cercano, Yixuan, a >13% de distancia) → identificación por vector de stats (Capa 4) inequívoca.

## Verificación de identidad (3 vías → "Billy Estelar", separado de "Billy")

- **Vector de stats** (primaria): dist 0.0000, gap 0.13 al 2º. Cross-check rol/elem: `_canon_rol("Disruptivo")→"Disruptivos"` ✓, `_canon_elemento("Físico")→"Físico"` ✓ → aceptado.
- **Badge/-ico**: `ICO_ALIAS["Billy-starlight"]="Billy Estelar"` (asset `Billy-starlight.png`).
- **OCR-nombre** (fallback): da "Billy", pero nunca decide cuando hay stats.

QA en vivo (2026-06-12 15:09): `Stats agente Billy Estelar (Disruptivos/Físico) PV=20573` · `badge aprendido para 'Billy Estelar'` · `[S17] asignado a 'Billy Estelar'` · 6/6 slots en equip_map. ✅

## Bug colateral encontrado y corregido

`parser_agent_stats._get_roster()` usaba un `_DB_PATH` hardcodeado (relativo al fuente) con sqlite3 crudo, **ignorando `DANIBOD_DB_PATH`**. En el `.exe` frozen leía la DB bundleada/vieja (46 agentes) → Billy Estelar (solo en repo db) no se identificaba por stats. **Fix:** `_get_roster()` resuelve con `connection._resolve_db_path()` (misma DB que el resto de la app). + test de regresión `test_get_roster_honra_db_path_override`.

## PENDIENTE (RNF-02 — no inventar)

- `pj_weapon_synergy` (6 filas): rol Disruptivos/Rupture sin BONUS_MATRIX confirmada → diferido a fuente Prydwen.
- Thresholds HP/Fuerza Bruta finos, splash art `{id}_{nombre}.png`, catalogación IA (44 pares).
- Verificar facción ("Gentle House" vs Cunning Hares).
- Build de discos (set 4+2, weapon) → se captura in-game (su comp logueó "sin discos equipados capturados" por set_4p/2p NULL).

## Counts DB (post-onboarding)

agents 46→**47** · agent_thresholds 108→**110** · agent_score_thresholds 46→**47** · agent_awakenings 6→**7** · pj_weapon_synergy **276** (sin cambio). `integrity_check` ok · `foreign_key_check` ok.

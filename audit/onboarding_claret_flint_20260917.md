# Onboarding Claret Flint — 2026-09-17 · migración 35

**Migración:** `db/migrations/2026-09-17_35_onboarding_claret_flint.sql`
**Backup RNF-01:** `db/danibod_zzz_v2.backup_premig_20260917_124914.db` (lo hizo el runner; gitignoreado)
**Runner:** `app/scripts/qa/apply_migration.py`, ensayado antes sobre una copia de la DB.

## Qué es Claret

| | |
|---|---|
| identidad | Claret Flint · **S** · Eléctrico · **Armero** (rol nuevo, EN "Armorer") · **Flint Workshop** (facción nueva; pantalla ES "Taller Flint de Roscaelifer") · Nivel 60/60 · M0 · v3.2 (09-09-2026) |
| id asignado | **52** |
| stats efectivos | PV 8360 · DEF 927 · Impacto 93 · CR 95,2 % · CD 93,2 % · TA 86 · MA 79 · TP 32 % · **Daño de laceración 150 %** · **Acumulación Automática de afiladura 1,5** · ATK **NULL** (la ficha del Armero no lo muestra) |

## Fuentes (RNF-02)

- **Captura del juego** `Perfil_agente/atributos_base_ejemplo_17.png` para identidad y stats.
  **Cruzada contra `parse_agent_stats`** antes de escribir: los 10 stats que el parser ya lee
  coinciden exactamente (conf 0.972). El parser metió la afiladura (1,5) en `recuperacion_energia`
  por el rescate de ROI de esa celda: es el defecto que corrige la entrega 3.
- **Prydwen**, guía de Claret actualizada el 2026-09-09 (patch 3.2), leída el 2026-09-17: kit
  (multiplicadores sobre DEF; el crit del Sharp DMG usa Laceration DMG; CD → CR a 0,35), discos,
  mains, orden de substats y objetivos endgame.
- **Game8**: rareza, atributo, especialidad, facción y fecha de release (coinciden con Prydwen y la captura).

## Qué escribió

| tabla | antes | después | qué |
|---|---|---|---|
| `agents` | 51 | **52** | Claret + **2 columnas nuevas** `dano_laceracion`, `acumulacion_afiladura` (NULL en los otros 51) |
| `disc_archetypes` | 6 | **7** | `ARMORER_DEF` "Armero DEF-scaler" |
| `disc_set_archetype` | 39 | **45** | Thorned Rose primario; Puffer Electro, Woodpecker Electro, Soul Rock, Thunder Metal, Branch & Blade Song secundarios |
| `agent_score_thresholds` | 51 | 52 | defaults 0.75 / 0.50 |
| `agent_awakenings` | 16 | 17 | placeholder, `v3.2` |
| `agent_thresholds` | 111 | 114 | DEF 2300/2600 · PV 9500 · CR 128,9 / 200 (Prydwen) |
| `agent_substat_preferences` | 60 | 68 | CR 1.0 · DEF% 0.9 · CD 0.7 · Perforación 0.6 · DEF 0.4 · ATK% −1.0 · ATK −0.8 · MA −0.8 |
| `pj_weapon_synergy` | 294 | 300 | crit 1.5 · dmg 1.0 · pen 0.8 · atk 0.0 · anomalía 0.0 · **ER 0.4 sin fuente** |

`snapshot_counts.py` antes/después: **ninguna otra tabla cambió**. `foreign_key_check` y
`integrity_check` ok; los 19 smoke checks `expected_N` valen exactamente N.

## Decisiones de modelado

- **Arquetipo propio y no uno existente.** Ninguno describía a un PJ que escala con DEF + crit:
  `ATK_DPS` penaliza DEF% con −1,0 y `DEFENSE` no pide crit. Y un rol sin arquetipo caía **en
  silencio** a `ATK_DPS` (`AgentRepo`): el mismo commit lo mapea y hace que un rol desconocido avise.
- `mains_4` admite Daño Crítico además de Prob. Crítica: el kit convierte CD en CR. `mains_5`
  admite los 6 bonos elementales + Tasa de Perforación (contrato `test_disc_archetypes_contrato`).
- **Lo que queda NULL a propósito:** `ataque`, `rec_energia` (su celda es la afiladura),
  `perforacion`, `bono_dano_elemento`, `weapon_*`, `set_*`, `disco6_main`. Los llena la captura en vivo.

## Pendiente

- W-Engines (Crimson Thirst, Bloodmarrow Coffer, Catty Luck): no están en `weapons`; entran por S26/S30.
- `energy_regen` de `pj_weapon_synergy`: sin guía para Armeros; revisar cuando la haya.
- `Pj_stats` de HoYoLAB (diferido, como Aria), badges (cosecha en vivo), catalogación IA (RF-12 no implementado).
- **DEF 927 contra el objetivo de 2300+** y contra el primer escalón del 4pc de Thorned Rose (DEF
  inicial ≥ 1000): dato para la build, no para esta migración.

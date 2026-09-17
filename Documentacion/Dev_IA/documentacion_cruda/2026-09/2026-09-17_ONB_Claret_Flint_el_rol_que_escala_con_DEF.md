# Onboarding de Claret Flint: el rol que escala con DEF, y tres cosas que iban a fallar en silencio

**2026-09-17.** Commits `0c5e624` (assets) · `895672d` (migración 35) · `93d78d8` (parser S18).
Plan: `C:\Users\danie\.claude\plans\claret-flint-y-vamos-snappy-lollipop.md`. Reporte de la
migración: `audit/onboarding_claret_flint_20260917.md`.

**Estado al cerrar este doc:** entregas 1-3 en `main` y verdes. La **entrega 4 (en vivo)** estaba en
curso: la app abierta con `-FromSource -ReadOnly -BadgeHarvest -NoRamGuard -IdDiag` esperando que
Daniel pase por S15 → S18 → Equipamiento (screenshot para `row`) → los 6 discos. Ver §6.

## Qué es Claret

S · Eléctrico · **Armero** (especialidad nueva de v3.2, EN "Armorer") · **Flint Workshop** (pantalla:
"Taller Flint de Roscaelifer") · Nv 60/60 · M0 · id **52**. Nombre en DB **`Claret Flint`** (decisión
de Daniel): el menú de personajes dice sólo "Claret", como Remielle.

Fuentes: la ficha S18 del juego (`atributos_base_ejemplo_17.png`) para identidad y stats; **Prydwen**
(guía del 2026-09-09, leída con el navegador integrado porque la descarga directa da 403) para kit,
build y objetivos; **Game8** para cruzar rareza, facción y release.

⭐ **El kit que cambia el modelo:** sus multiplicadores escalan con **DEF**, el crit de su Sharp DMG
usa el **Laceration DMG Bonus** en vez del Daño Crítico, y cada 1 % de CD inicial suma 0,35 % de CR.

## 1 · Lo que iba a fallar en silencio

A diferencia de Aria ("el primero sin vocabulario nuevo"), Claret trajo vocabulario nuevo en tres
capas, y en **las tres** el sistema se habría equivocado sin avisar:

| capa | qué pasaba | cómo fallaba |
|---|---|---|
| scoring | un rol sin arquetipo caía a `ATK_DPS` (`AgentRepo`) | `ATK_DPS` penaliza DEF% con **−1,0**: el scorer le habría dicho que sus mejores discos eran malos |
| parser S18 | el rescate por ROI de Recup. Energía lee la celda donde el Armero muestra la afiladura | **ER = 1,5** en la fila, medido sobre la captura real antes del cambio |
| assets | los logos y splash nuevos vivían sólo en `claude_design_upload/assets/` | gitignoreada y borrada con `rm -rf` por `tools/stage_design_assets.sh` |

Es D2 tres veces ("degradar callado es peor que romper fuerte"). Ahora un rol sin arquetipo **avisa
una vez por rol** (sin cambiar el fallback), y el parser identifica al Armero por sus labels
exclusivos, como hace con FB para los Disruptivos.

## 2 · Entrega 1 — assets (`0c5e624`)

- Splash `claret-ico` / `claret_extend` en `app/resources/ui_assets/splash_arts` (D1), con override
  `"Claret Flint" → "claret"`; la mezcla de separadores la resuelve el fallback existente.
- Ref del avatar: **sólo `claret.png`**, con `crop_head` de `tools/crop_ico_refs.py` sin correr su
  `main()` (regenerar todo degrada refs commiteadas) + `ICO_ALIAS["claret"] = "Claret Flint"`.
- Logos: Flint Workshop, **Covenant of Dayat** (Remielle Dan: faltaba desde v3.1, salió de
  `SIN_LOGO`) y Airspace Patrol Department (sin PJ todavía).
- Originales versionados en `Documentacion/Interfaz/Assets_Originales/` (decisión de Daniel).
- Dato de paso: dos tests que recorren las carpetas de capturas tomaron las nuevas y dieron verde, así
  que **el detector ya clasificaba** la ficha de Claret como S18 y su menú como S15.

## 3 · Entrega 2 — migración 35 (`895672d`)

Ensayada sobre una copia, aplicada con `apply_migration.py` (backup
`db/danibod_zzz_v2.backup_premig_20260917_124914.db`), 19 smoke checks exactos, `snapshot_counts`
antes/después: **sólo cambiaron las 8 tablas previstas**.

- **Antes de escribir, cruce contra el parser** (molde Aria): los 10 stats que ya leía coincidieron
  con la lectura visual (conf 0.972).
- `agents` + **2 columnas** `dano_laceracion` (150.0) y `acumulacion_afiladura` (1.5), decisión de
  Daniel; `ataque` **NULL** porque la ficha del Armero no lo muestra.
- `disc_archetypes` **`ARMORER_DEF`**: mains 4 CR/CD · 5 bonos elementales + Tasa de Perforación · 6 DEF%;
  substats CR 1.0 > DEF% 0.9 > CD 0.7 > PEN 0.6 > DEF 0.4 (orden de Prydwen); ATK%/ATK/MA negativos.
  Sets: Thorned Rose primario + 5 dos-piezas de Prydwen. Los 6 ya existían en `disc_sets`.
- `agent_thresholds` DEF 2300/2600 · PV 9500 · CR 128,9/200 · `substat_preferences` · score
  thresholds · awakening `v3.2` · `pj_weapon_synergy` (**ER 0.4 sin fuente**, anotada así).
- Código en el mismo commit: `ARCHETYPES_BY_ROLE` sube a nivel de módulo con `"Armero"`, y el aviso
  del rol desconocido. Contrato contra la DB real: todo rol del roster tiene arquetipo existente.

## 4 · Entrega 3 — parser S18 (`93d78d8`)

OCR real de Paddle sobre la ficha: `Dafo de laceración 150 %` (sic) y
`Tasa de Perforacion 32 % 1.5 de afiladura` (el valor **antes** del label, pegado al % de TP).

- Regex ancladas en `lacerac` (no en "daño", que el OCR rompe y que también es de Daño Crítico) y en
  `afilad`, con la ventana del valor-antes **sin `%`**: si no, el 32 de TP se leía como afiladura
  (sabotaje 5 lo prueba).
- Exclusividad por rol: laceración o afiladura presentes ⇒ Armero (corrige el rol de la DB/banner),
  ATK leído se descarta, ER queda NULL y la afiladura se rescata por la ROI de ER si falta el dígito.
- Completitud del Armero: comunes − ATK + LAC + TP + AF = 11.
- Syncer: persiste las 2 columnas; **una DB sin ellas se saltea y avisa una vez** (la copia de
  `%LOCALAPPDATA%` del `.exe` es de agosto y rompía el sync de todos los PJs).
- Log de S18 con `LAC=… AF=…`; el modal de PJ muestra Laceración/Afiladura en vez de Ataque/Recup.
  Energía para el Armero (`stats_de_rol`, una sola autoridad para ficha y widget).
- **Los 17 fixtures de S18 leen igual que antes**; Claret sale completa, y un test compara la lectura
  de la captura real con la fila de la migración.

## 5 · Verificación

| | |
|---|---|
| suite | 2894 → **2900** (E1) → **2904** (E2) → **2920** (E3); 0 failed / 0 skipped en las tres |
| sha256 DB | igual en E1 y E3; en E2 cambió por la migración y la suite no la tocó (`d261a7ed…`) |
| sabotajes | E2 3/3 rojos · E3 7/7 rojos (script con `count == 1`) |
| `.exe` | no se recompiló (pedido de Daniel) |

## 6 · Entrega 4 (en vivo) — dónde quedó

**Línea base medida antes de cosechar** (`measure_badge_lib --against-labeled`):
`grid` 93,3 % top-1 · 4,3 % abstención · **2,4 % wrong** (imán Billy Estelar ×4; igual que al cerrar
Aria) · `row` 7,3 % top-1 · 0 % wrong. `detail` no tiene modo `--against-labeled`.

Pasos pendientes, en orden:
1. Daniel: S15 → Claret (`[S15] … PJ=Claret Flint`); S18 (`[stats] … LAC=150.0% AF=1.5`, `[completo] 11/11`);
   Equipamiento con screenshot a `Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_N.png`;
   un disco equipado y los 6 slots; Salir.
2. Leer el log (desde la línea 10783 de `app.log`): `badge aprendido para 'Claret Flint'` y `[id_diag]`.
3. `tools/preseed_badge_lib.py --surface row --source frame --frame <screenshot> --label "Claret Flint"`.
4. `measure_badge_lib --against-labeled` en `grid` y `row`: **no puede empeorar** contra la línea base.
5. Snapshot de las 3 librerías a `audit/` + repuntar `agent_identifier._BASELINES` + commit.

## 7 · Pendiente

- W-Engines de Claret (Crimson Thirst, Bloodmarrow Coffer, Catty Luck): no están en `weapons`; entran
  por S26/S30 y el reporte de fuera de catálogo.
- `energy_regen` en `pj_weapon_synergy` sin fuente para Armeros.
- `Pj_stats` de HoYoLAB (diferido como Aria) y catalogación IA (RF-12 no implementado).
- FB/AD de los Disruptivos siguen sin columna, a diferencia de LAC/AF: asimetría para decidir aparte.
- Su DEF (927) está lejos del objetivo (2300+) y debajo del primer escalón del 4pc de Thorned Rose
  (DEF inicial ≥ 1000): dato de build, no de sistema.

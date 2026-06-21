# L.7 — Validación del lado LIBRE con frames reales (2026-06-20)

El usuario aportó 7 capturas de discos LIBRES reales
(`Documentacion/Screenshots_Triggers/Discos_Triggers/17_Inventario_Disco_Vista_Individual_libres`),
el dato que faltaba offline (toda captura S17 previa era de equipados).

## Hallazgo del diagnóstico (`diag_free_disc_presence.py --free`)
- **Detail = árbitro fiable:** `detail_notnone = 1/7` → 6/7 libres dan `crop_detail_badge=None`.
- **Gate del grid = LEAKY en libres:** 4/7 tienen tile y pasan hough+blob (719-1249). La esquina
  del tile libre = **barra "Nivel" amarilla + arte gris del disco** (NO una cara), pero con suficiente
  saturación + circularidad para pasar. **No existe umbral** que la separe de avatares de baja-sat
  (Lycaon/Corin/Rina: blob 245-333 < estos libres 719-1249). ⇒ perfeccionar el gate del grid es
  whack-a-mole; el **detail** es la señal correcta.

## Causa del bug reportado ("no detectado pj" en vez de LIBRE)
La presencia espuria del grid (`grid_present>0`) BLOQUEABA el árbitro (la 1ª versión de `_s17_is_libre`
exigía `grid_present==0`). Fix: **árbitro POR EL DETALLE** — LIBRE = sin votos + `detail_present==0`
+ `detail_absent≥2`. La presencia leaky del grid ya no bloquea; el grid igual no puede meter dueño
sin VOTAR (gate + reject-set).

## Resultado con el fix (matcher de runtime sobre los 7 libres)
| frame | grid | grid-voto | detail | veredicto |
|---|:-:|---|:-:|---|
| Ejemplo_1 (reemplazar) | sí (leaky) | None@0.68 (sin voto) | None | **LIBRE** ✓ |
| Ejemplo_2 (equipar) | NO | — | sí | incierto (detail localizó, no matcheó) |
| Ejemplo_3 (reemplazar) | sí (leaky) | None@0.54 rej | None | **LIBRE** ✓ |
| Ejemplo_4 (equipar) | NO | — | None | **LIBRE** ✓ |
| Ejemplo_5 (reemplazar) | sí (leaky) | None@0.51 rej | None | **LIBRE** ✓ |
| Ejemplo_6 (reemplazar) | NO | — | None | **LIBRE** ✓ |
| Ejemplo_7 (reemplazar) | sí (leaky) | None@0.51 rej | None | **LIBRE** ✓ |

**6/7 LIBRE · 0 falso-equip** (el grid se abstuvo en los 7) · **1 incierto** (Ejemplo_2: crop de
detail espurio sin match → `detail_present>0` bloquea). El gate del grid sigue útil (rechazó 3/7 +
0 regresión en 218 equipados).

## Fix del 1/7 (Ejemplo_2 + Metal colmilludo en vivo) — filtro de presencia por conf/margen
QA en vivo (`id_diag`: `det_loc=4 det_match=0`) + inspección: el localizador del detail recorta el
**texto '(N)' del nº de slot** del título en algunos libres (`audit/ej2_detail_spurious.png` = "(1)").
Ese crop matchea con **conf 0.66 + margen 0.02** (equidistante entre refs = no es una cara). **Fix:**
`_sample_s17_owner` cuenta `detail_present` solo si `not rejected and (conf≥_DET_PRESENCE_CONF=0.70 o
margen≥_DET_PRESENCE_MARGIN=0.05)`; el texto (ambos bajos) cuenta como AUSENTE → no bloquea LIBRE.
`s17_match_detail` ahora devuelve también el margen.
- **Validación libres: 7/7 LIBRE, 0 falso-equip.**
- **0 regresión:** sobre 167 crops de avatar reales (harvest det) solo 3 caen "ausente" — y son
  `cissia__det__*`, que son **crops de TEXTO "(5)" contaminados** (ya conocido), NO caras. 164/164
  avatares reales → presentes.
- Tests: `test_monitor_detalle_espurio_texto_no_bloquea_libre` (nuevo). Suite S17/grid/S18 136/136.

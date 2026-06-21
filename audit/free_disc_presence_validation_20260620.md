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

## Fix (Ejemplo_2/8 + Metal colmilludo en vivo) — filtro de presencia por conf/margen
QA en vivo (`id_diag`: `det_loc=4 det_match=0`) + inspección: el localizador del detail recorta el
**texto '(N)' del nº de slot** del título en algunos libres ("(1)"). Ese crop matchea con **conf
0.64-0.66 + margen 0.02-0.054 (INESTABLE)** — equidistante entre refs, no es una cara. **Fix:**
`_sample_s17_owner` cuenta `detail_present` solo si `not rejected and (conf≥_DET_PRESENCE_CONF=0.86 o
margen≥_DET_PRESENCE_MARGIN=0.10)`; `s17_match_detail` devuelve también el margen. Además
`_s17_is_libre` exige **ausencia DOMINANTE (≥2:1)** → tolera un spike espurio suelto del texto sin
bloquear LIBRE; presencia consistente (avatar real) sí bloquea.
- **Calibración** (163 avatares reales: conf p5=**1.00** [votan], margen p5=0.092; textos: conf
  0.64-0.66, margen ≤0.054): la regla deja **0/163 avatares ausentes** y excluye todos los textos.
- **Validación libres: 8/8 LIBRE** (Ejemplo_8 = Metal colmilludo, antes fallaba con margen 0.054),
  0 falso-equip (el grid se abstuvo en todos).
- Tests: `test_monitor_detalle_espurio_texto_no_bloquea_libre` + `test_s17_is_libre_tolera_spike_espurio_minoritario`. Suite S17/grid/S18 137/137.

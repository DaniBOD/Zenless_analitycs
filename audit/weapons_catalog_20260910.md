# Catálogo `weapons` — los "6 huecos" del censo, medidos (2026-09-10)

**Migración:** `db/migrations/2026-09-10_27_weapons_dos_huecos_reales.sql` · **59 → 61 filas**

## El hallazgo: 4 de los 6 ya estaban

El censo del 2026-09-08 (`audit/censo_armas_20260908.md`) listó 6 armas fuera de catálogo como
entrada para esta migración. Antes de insertar, cada una se buscó en las 59 filas:

| leído en pantalla | lecturas | ya existe como | similitud | qué le pasó al OCR |
|---|---|---|---|---|
| `Anhelomarcato DESRE` | 1 | **Anhelo marcato** (17) | 0.788 | el arte del arma dice *DESIRE* (su nombre en inglés es *Marcato Desire*) |
| `Viajeestruendoso CRASH` | 2 | **Viaje estruendoso** (40) | 0.821 | texto del arte pegado; el QA del 07-30 la leyó limpia |
| `Cilindroneumatico de Bigger` | 2 | **Cilindro neumático** (42) | 0.756 | ⚠️ ver "abierto" |
| `Temploala granizadaestelifera` | 1 | **Templo a la granizada** (2) | 0.760 | ATK 743 y Prob. Crítica 24 %, idénticos a la fila |
| `Tetera esmeraldina` | 1 | — | — | **hueco real** |
| `Inocencia sacrificada` | 6 | — | — | **hueco real** |

Las cuatro quedan debajo del corte del fuzzy (0.84), y por eso salieron como "fuera de catálogo".
**Darlas de alta habría duplicado el catálogo.** Su problema es de matching.

Es la misma forma que el glifo `X` de `Cúter` (2026-09-08): una lectura sucia de un arma que
existe, reportada como un arma que falta.

## Las dos filas que sí entran

| | Inocencia sacrificada | Tetera esmeraldina |
|---|---|---|
| dueño en la cuenta | N.º 0: Anby | Qingyi |
| rareza | S | S |
| `atk_base` | **713** (leído a Nv 60/60) | **NULL** — la lectura es a Nv 50/50 (595) |
| `stat_secundario` | `CRIT DMG` | `Impact` |
| `stat_secundario_valor` | **48%** (a Nv 60) | **NULL** — el 15.8 % es de nivel 50 |
| `nombre_en` | NULL | NULL |
| `tipo_especialidad` | NULL | NULL |
| lecturas del nombre | 6, todas iguales | **1** |

**Por qué NULL y no el valor leído:** `atk_base` está definida como *"ATK base al nivel 60"*, y el
stat avanzado también escala con el nivel. Guardar el 595 de nivel 50 sería guardar un número
real con la etiqueta equivocada, indistinguible después de uno correcto.

**`nombre_en`:** la regla del catálogo (audit del 07-28) exige traducción palabra por palabra
verificada contra una fuente autorizada; si no, NULL. No se consultó ninguna fuente, así que no
se registra ni siquiera como hipótesis.

**`tipo_especialidad`:** el panel muestra el ícono, pero el parser no lo lee. Se completa cuando
se lea.

## Abierto

1. **¿El catálogo tiene nombres incompletos?** `Cilindro neumático` se leyó **dos veces** como
   `…de Bigger` (Bigger es el apellido de Ben, su dueño), y `Templo a la granizada` **una vez**
   como `…estelífera`. Si la pantalla dice eso, lo que hay que corregir es el catálogo, con una
   migración de renombre, y el matching se arregla solo. Se decide con una captura limpia de cada
   una, no con el OCR.
2. **`Tetera esmeraldina` tiene una sola lectura.** El nombre salió limpio (dos palabras reales),
   pero una lectura es poca evidencia. Si una pasada futura la lee distinto, se corrige con un
   renombre.
3. **Matching tolerante al texto del arte.** Medido: comparar "el nombre del catálogo, sin
   espacios, como prefijo de lo leído sin espacios" resuelve **los 4 falsos huecos**, y en todo el
   catálogo produce **una sola colisión**: `Repercusión - Modelo II` es prefijo de `…Modelo III`.
   Tomar el prefijo más largo la resuelve para lecturas limpias, pero queda un riesgo residual si
   el ruido pegado empieza con un trazo vertical, porque `_norm_nombre` colapsa `l`, `1` e `|` a
   `i` (`Modelo II` + `l` se leería `Modelo III`). Es una decisión de diseño, no se aplicó.

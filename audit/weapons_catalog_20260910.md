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

## Cerrado el 2026-09-11 — el catálogo SÍ tenía nombres cortados (migración `_28`)

Daniel capturó las tres armas en S30 (`Inventario_general_engines/Ejemplo_13` a `_15`, locales).
Leídas a ojo **y** con `parse_weapon_s30`:

| captura | la pantalla dice | el catálogo decía | qué se hizo |
|---|---|---|---|
| `_13` | **Cilindro neumático de Bigger** · A · Nv 20/30 · P5 · ATK 248 · **Defensa 25.6 %** | `Cilindro neumático` · `HP% 20%` | renombre + stat a `DEF%`, valor NULL |
| `_14` | **Templo a la granizada estelífera** · S · Nv 60/60 · P1 · ATK 743 · Prob. Crítica 24 % | `Templo a la granizada` | renombre (el resto coincide) |
| `_15` | **Tetera esmeraldina** · S · Nv 50/50 · P1 · ATK 595 · Impacto 15.8 % | igual | nada: **segunda lectura idéntica**, el nombre queda confirmado |

**Medido:** con el catálogo renombrado, `match_catalogo` resuelve las 4 lecturas, crudas incluidas
(`Cilindroneumatico de Bigger`, `Temploala granizadaestelifera`); con el de antes, ninguna. Las 3
capturas entraron a `test_parser_weapon_s30._TRUTH`.

**Lo que nadie había cruzado:** el repo ya tenía los dos nombres largos. `test_parser_weapon_s26.py`
fija `Templo a la granizada estelífera` como verdad de tierra desde julio, y S29 escribe
`Cilindro neumático de Bigger` en el diálogo de sustitución. Una búsqueda del nombre en `app/`
antes de la `_27` lo habría resuelto sin capturas.

**El stat falso de la fila 42.** La fila nació como `Pneumatic Cylinder`, una traducción inventada
del español (la `_13` la borró a NULL); la `_11` la dejó "sin evidencia, no se toca". Su `HP% 20%`
tenía el mismo origen, y la pantalla dice **Defensa**. El nombre del stat es fijo por arma ⇒
`DEF%`; el valor escala con el nivel y la lectura es de Nv 20 ⇒ NULL.

## Abierto

1. **Fila 42, lo que la captura no desmiente pero tampoco respalda:** `atk_base = 500` (ningún otro
   rango A del catálogo tiene 500 a Nv 60) y las columnas `pasiva_*`, con el mismo origen que el
   stat falso. Se resuelven con una lectura del arma a Nv 60, o con una fuente autorizada.
2. **`nombre_en` de las dos filas renombradas:** la fila 2 conserva `Hailstorm Shrine`; la 42 sigue
   NULL — `Bigger Cylinder` es la hipótesis obvia, pero no se verificó en ninguna fuente.
3. ~~**Matching tolerante al texto del arte.**~~ **Aplicado el 2026-09-11, pero NO como prefijo**
   (ver abajo). Lo que sigue es la propuesta original, como historia.

   **Lo que se aplicó:** `_sin_texto_del_arte` recorta **un token final en MAYÚSCULAS** (3+ letras,
   que no sea un romano `[IVXLCDM]+`) y el resto pasa por el matching de siempre. Se reconoce el
   arte por la **caja**: los nombres del catálogo van en minúsculas después de la primera palabra.
   El prefijo se descartó por dos daños que el recorte no tiene: `Modelo II` cabe dentro de
   `Modelo III`, y un arma **nueva** que empiece como una del catálogo (`Cúter afilado`) se habría
   resuelto a la vieja — fila escrita con el arma equivocada y un hueco menos en la curada.
   **Medido en campo:** de las 12 lecturas distintas que el log de S30 dio "fuera del catálogo",
   hoy resuelven **10**; las 2 que quedan no son armas (el panel de la propia app, y
   `X Hadoemplumado (i)` a Nv 15/15 con ATK 2200, sin investigar).

   *Propuesta original:* Medido: comparar "el nombre del catálogo, sin
   espacios, como prefijo de lo leído sin espacios" resuelve **los 4 falsos huecos**, y en todo el
   catálogo produce **una sola colisión**: `Repercusión - Modelo II` es prefijo de `…Modelo III`.
   Tomar el prefijo más largo la resuelve para lecturas limpias, pero queda un riesgo residual si
   el ruido pegado empieza con un trazo vertical, porque `_norm_nombre` colapsa `l`, `1` e `|` a
   `i` (`Modelo II` + `l` se leería `Modelo III`). Es una decisión de diseño, no se aplicó.

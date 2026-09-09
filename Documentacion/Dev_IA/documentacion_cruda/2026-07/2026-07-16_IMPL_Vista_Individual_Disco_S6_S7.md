# IMPL — Vista individual del disco (S6/S7): la pantalla del "Ver"

**Fecha:** 2026-07-16 · **Estado:** implementado, pendiente QA en vivo · Display-only.

## Qué es

La pantalla a pantalla completa que abre el botón **"Ver"**: arte del disco a la izquierda,
panel de stats a la derecha (título `<set> (N)`, pill de nivel, "Atributo principal",
"Atributos secundarios" en grilla 2×2, "Efecto de conjunto"). Desde ella se **mejora** el disco.

Se llega desde **tres** flujos, no solo la tienda:

```
tienda:     S4 → S5 (afinación)      → "Ver" → S6/S7 → "Mejorar" → S10
baterías:   S13 → S21 → [auto] → S22 ("Obtenido") → "Ver" → S6/S7 → "Mejorar" → S10
inventario: S9                        → "Ver" → S6/S7 → "Mejorar" → S10
```

**No es un estado nuevo.** Ya existía como S6/S7 con ROIs propias — y `rois.toml` dice explícito
que *"S7 tiene layout idéntico a S6 — usa mismas coords"*. Los nombres viejos ("Tienda música —
panel/fullscreen") mentían sobre el alcance; se corrigieron las descripciones. Fixtures:
`04_Inventario_Disco_Vista_Individual/` → **Ejemplo_6, 7 y 17** (el resto del folder es S17).

## Bug 1 — el toast no saltaba: la transición, no el template

Reportado por el usuario: *"cuando paso y extrae el disco no salta el toast"*.

La máquina de estados tenía `S6: {S7, S12, S4}` y `S7: {S12, S4, S6}` ⇒ **la vista solo era
alcanzable desde la tienda**. Viniendo del "Obtenido" (S22) la transición se rechazaba como FP →
S12 → el disco no se parseaba → **sin toast**. Causa raíz, no un problema de detección.

Se abrió a los flujos reales (ida y vuelta) y a la mejora:

```python
"S6":  {"S7", "S12", "S4", "S5", "S9", "S10", "S22"},
"S7":  {"S12", "S4", "S6", "S5", "S9", "S10", "S22"},
"S9":  {..., "S6", "S7"},    "S10": {..., "S6", "S7"},    "S22": {..., "S6", "S7"},
```

## Bug 2 — los dos templates matcheaban por accidente

| Template | Por qué matcheaba | Por qué se rompe |
|---|---|---|
| `s7_tienda_detalle_full.png` | incluye el texto **"Nivel 15 / MAX"** | solo detecta discos **maxeados** |
| `s6_tienda_detalle_panel.png` | banda oscura = **el wallpaper** de Ejemplo_6 | no es UI: muere al cambiar de fondo |

Entre los dos cubrían Ejemplo_6/7 de casualidad; **Ejemplo_17** (Nivel 00, otro wallpaper) caía
a **S12**.

**Template nuevo `s7_detalle_full_iconos.png`**: el cluster **papelera + candado + teclas R/T**
(ROI `(0.485, 0.190, 0.090, 0.100)`, 230×144). Es chrome de UI puro ⇒ invariante al nivel, al
set y al wallpaper. Medido:

| Grupo | NCC |
|---|---|
| **Las 3 capturas de la vista** | **0.997 – 1.000** |
| S17 / S9 / S10 / S5 / S22 / S2-S3 | ≤ **0.738** |
| 37 negativos de QA | ≤ **0.447** |

Recortado desde Ejemplo_6 o desde Ejemplo_17 da lo mismo (0.997 cruzado) → invariante confirmado.
Umbral 0.85, sin `_verify_*` (el margen es enorme). Ejemplo_17: **S12 → S7 (1.000)**.

Los dos templates viejos se **dejan** (el path de la tienda está validado en QA y comparten
ROIs, así que clasifiquen S6 o S7 el parseo es el mismo). Ejemplo_6 sigue dando S6 por empate en
1.000 — inofensivo ahora que las transiciones son simétricas. **Pendiente de decisión:** retirar
`s6_tienda_detalle_panel` (matchea por wallpaper = FP latente) y dejar una sola pantalla.

## Bug 3 — el parser per-ROI inventaba substats

`parse_modal_detalle` (per-ROI) leía mal esta pantalla por la MISMA razón que el modal S3, cuyo
docstring ya lo decía: *"cada celda capturaba la columna vecina"*. Medido sobre Ejemplo_17:

```
sub: 'obablllaaa ae 2.4 % % Pert'     ← nombre y valor pegados
sub: 'Probabilidad de'  valor=2.4 %   ← el nombre envuelto a 2 líneas se parte…
sub: 'Critico'          valor=1.0     ← …y el 2º toma un valor RESCATADO de otra fila → RNF-02
notas=['set_desconocido:Firmamento llameante', ...]
```

Los ROIs por-campo eran estimaciones a ojo (`rois.toml` admite *"no salió en OCR full, pero
estimable"*) y `sub1_nombre` abarca `x 0.605–0.755`, que **se come el valor**.

**Fix:** `parse_disc_s7()` en `parser_disc_s3.py`, reusando el motor de 2 columnas de S3 (mismo
precedente que `parse_disc_s5`, que lo reusa con 1 columna). Geometría medida sobre los 3
fixtures (2559×1439):

```python
_S7_COL_A = PanelLayout(0.60, 0.77, 0.70)   # nombres xn≈0.615 | valores xn≈0.725-0.749
_S7_COL_B = PanelLayout(0.77, 0.96, 0.87)   # nombres xn≈0.782 | valores xn≈0.905
```

Tres particularidades que S3/S5 no tienen:

1. **El título vive lejos del panel** (arriba-izquierda, `xn≈0.05`; el panel en `0.60-0.95`). No
   se puede OCRizar el frame completo y filtrar por banda como S3: una banda que cubra ambos
   deja entrar la **barra superior** del juego ('Ciudad', créditos, batería), que al caer por
   encima del header "Atributo principal" se leería como parte del título. Se OCRizan **dos ROIs
   acotadas** (`_S7_TITLE_ROI`, `_S7_PANEL_ROI`) y se unen con coords absolutas.
2. **El pill de nivel se lee partido.** El "/15" es un gráfico aparte y Paddle devuelve
   `'Nivel 0o'` + `'15'` ⇒ `_RE_NIVEL` (exige el "/15" en la misma línea) nunca matchea. Se lee
   de su ROI propia con `_RE_S7_NIVEL` (sin el "/15"). El `o` del cero zero-padded se mapea a
   `0`: seguro, porque la palabra 'nivel' no tiene ninguna 'o'.
3. **Placeholders "EMPTY"** en los slots de substat vacíos, que Paddle devuelve mutilado
   (`'EMPT'`, `'EUPT'`…). Cazarlos por token es whack-a-mole (`_S9_JUNK_TOKENS` ya acumula
   `empty`/`ept`/`rpt`), así que se filtra por **información**: un substat real SIEMPRE tiene
   valor ⇒ una entrada que ni canoniza ni tiene valor solo puede ser el placeholder → se
   descarta con su nota. Se hace en `parse_disc_s7`, no en `_parse_s3_from_lines`, para no
   tocar S3/S5.

### Resultado — 3/3 fixtures exactos, `notas=[]`

| Fixture | set | slot | nivel | main | substats |
|---|---|---|---|---|---|
| Ejemplo_17 | Firmamento llameante | **2** | 00 | ATK 79 | Prob. Crítica 2.4 % · Perforación 9 · PV 112 |
| Ejemplo_6 | Nana a la luz cenicienta | **4** | 00 | Daño Crítico 12 % | Perforación 9 · Maestría de Anomalía 9 · DEF% 4.8 % |
| Ejemplo_7 | Nana a la luz cenicienta | **3** | 00 | DEF 46 | DEF% 4.8 % · PV 112 · Prob. Crítica 2.4 % |

Los dos nombres envueltos a 2 líneas ('Probabilidad de / Crítico', 'Maestría de / Anomalía')
coalescen a **un** substat con su valor real, y los de la **columna B** (que el per-ROI ni
miraba) salen bien.

## Limitación conocida

`rareza` sale `'S'` en Ejemplo_17 pero `'?'` en 6 y 7 — el ROI `rareza_borde` cae sobre el arte
del disco. Es **best-effort y no bloquea** (mismo tratamiento que en `parse_disc_s3_full`).

## Verificación

`app/tests/unit/test_parser_disc_s7.py` — 11 tests: clasificación de las 3 capturas, no-eclipse
de los 14 frames S17 del mismo folder, las transiciones de los tres flujos + la mejora, los 3
fixtures campo por campo, y que ningún placeholder EMPTY genere un substat fantasma.

**QA en vivo pendiente:** entrar al "Ver" desde el "Obtenido" (baterías) y desde la afinación
(tienda) y confirmar que **salta el toast** con los stats correctos, y que "Mejorar" sigue
llevando a S10.

# Compacto — julio 2026

**27 documentos · 4.679 líneas de crudo.** Los originales están en
[`documentacion_cruda/2026-07/`](../documentacion_cruda/2026-07/) y no se tocan.

Este archivo conserva **mediciones, hipótesis refutadas, dónde vive la autoridad y qué quedó
abierto**. Tira la narrativa, los bloques de código (están en git) y el paso a paso.
**No lleva lecciones transferibles**: esas viven en [`00_Practicas_Aprendidas.md`](../00_Practicas_Aprendidas.md),
que es su única autoridad.

## El arco del mes

Julio empieza **frenando la extracción** para endurecer el detector contra falsos positivos, y
termina con el pipeline leyendo el flujo completo de farmeo, **escribiendo la DB por primera vez**
(reemplazo de disco S23) y con RF-15 (W-Engines) arrancado. Entre medio: predicción de sets,
mejora de disco, bitácora de desmontaje y detección de gacha.

---

## Mapa de los 27 crudos

| fecha | documento | qué cubre |
|---|---|---|
| 07-07 | `Confiabilidad_Detector_Anti_FP` | QA negativo de 33 pantallas; `_verify_s2`; poda de dos ramas HSV |
| 07-07 | `Gate_Captura_Por_Foco_Anti_FP` | gate de foco de ventana — **REVERTIDO como default el 30-07** |
| 07-07 | `QA_En_Vivo_Farmeo_S2_S3` | 6 síntomas en vivo, 7 fixes, cross-thread SQLite |
| 07-08 | `PLAN_` + `IMPL_Prediccion_Sets_S13_y_Badge_S2` | mapa de 14 nodos → 2 sets; matcher de badge por package render |
| 07-09 | `IMPL_Slot_Digit_Matcher_S2` | dígito de slot por NCC en vez de OCR |
| 07-09 | `PLAN_Tienda_Musica_S4_S5` | tienda de Orphie: selector + afinación |
| 07-09 | `QA_Sesion_Farmeo_Multinodo` | 9 fixes de campo con commit cada uno |
| 07-10 | `IMPL_Mejora_Disco_S10` | modal de upgrade: detección, parser, tracking PRE→POST |
| 07-16 | `IMPL_Farmeo_Baterias_S21_S22` | previa de usos + drops del modal "Obtenido" |
| 07-16 | `IMPL_Identidad_PJ_Descriptor_Primario_S8_S19` | descriptor como fuente primaria, votación multi-frame |
| 07-16 | `IMPL_Mejora_Disco_desde_Tienda_Musica_S5` | la tienda confirma el upgrade sin pasar por inventario |
| 07-16 | `IMPL_Vista_Individual_Disco_S6_S7` | la pantalla del "Ver"; 3 bugs encadenados |
| 07-19 | `IMPL_Reemplazo_Disco_S23` | **primer feature que escribe la DB**; 3 rediseños (v1→v3) |
| 07-22 | `IMPL_Disco_Libre_Toast_Equipado` | toast "AHORA EN"; la pantalla era S17, no S6/S7 |
| 07-22 | `PLAN_Disco_Libre_Toast_Equipado` | **SUPERADO** por el IMPL del mismo día |
| 07-22 | `PLAN_Censo_Inicial_Cuenta` | los tres censos (roster, discos, armas) — se ejecutó en ago/sep |
| 07-22 | `SPEC_Invariante_Equipado_Asignado` | **especificado, NO implementado** |
| 07-23 | `QA_Trabe_Mudo_S17_y_Veto_del_Ancla` | trabe mudo por arte animado; FP del ancla; caso A |
| 07-25 | `IMPL_Bitacora_Desmontaje_S11_S24` | atribución por prueba, no por reloj |
| 07-25 | `QA_Desmontaje_en_vivo_y_el_silencio_del_loop` | validación en vivo + falsa alarma del loop |
| 07-26 | `FIX_Gate_Completitud_Stats_Agente` | gate de completitud en S18 |
| 07-26 | `QA_Desmontaje_cierre_del_flujo_completo` | el desmontaje cierra; deuda de UI |
| 07-28 | `IMPL_RF15_S26_Detalle_WEngine` | arranca RF-15: el detalle del arma |
| 07-29 | `Deteccion_Gacha_S27_S28` | banner + resultados de sintonización |
| 07-30 | `IMPL_RF15_Tenencia_Arma_Libre` | libre / de otro / equipada |
| 07-30 | `QA_RF15_S26_en_vivo` | 5 casos, los 5 pasaron |

---

## Mediciones que siguen valiendo

Un número medido no se reconstruye leyendo código. Estos son los de julio.

### Detector y anti-FP
- **QA negativo: 33 pantallas** que no deben disparar captura. Baseline **15 FP**; tras los fixes
  **33/33**. Regresión positiva 13/13 (6 S2 + 7 S18).
- `_DISC_STRIP_MIN = 3` franjas de rareza — **calibrado**: farmeo real da 3 en todas las capturas,
  pantallas sin discos ≤2.
- **Umbral S2 = 0.80.** Bajarlo a 0.70 reabría FP: guías y banners matchean a ~0.72.
- `_verify_s3` reescrito: ROI `x 0.53-0.68, y 0.19-0.44`, umbral `0.015`; los modales reales dan
  **0.029-0.066**.
- S23: **7 fixtures** contra **0.561 en 37 negativos**.

### Farmeo y sets
- **14 nodos → 2 sets cada uno.** 81 badges = 27 sets × 3 tiers. Falta *Branch & Blade Song*.
- Matcher de badge: leave-one-out sobre los 81, **separa los 2 sets de cada nodo ≥90 %**.
- **Open-set contra los 27 sets: 11/11 caen dentro del par predicho.** Ruido puro daría ~2/27.
- Dígito de slot por NCC: leave-one-out **29/30**, cero confusiones entre dígitos.

### El matcher del dígito S22 — el número más útil del mes
| prueba | resultado |
|---|---|
| leave-one-**sample**-out (dígito conocido) | **9/9**, score 0.999 |
| leave-one-**class**-out (dígito desconocido) | **6/11 INVENTAN**, score hasta 0.799 |
| refs de otras pantallas (S2, S5) | **0 ok / 11 WRONG**, score hasta 0.946 |
| 5 clases (falta el `1`) | matcher apagado → 8/11, 0 errores, 3 abstenciones |
| **6 clases** | **14/14, 0 errores, 0 abstenciones** |

**Con clases faltantes el matcher no se abstiene: inventa con confianza.** De ahí el gate de
completitud. Y las refs de otra pantalla no sólo no transfieren — son **peores que no tener nada**.

### W-Engines (RF-15)
- S26 y S17 matchean **el mismo template a 1.000**. El único discriminante que funciona es el texto
  del panel: *"Atributos **avanzados**"* vs *"**secundarios**"* → **40/40 armas, 0/42 discos**.
- Discriminantes baratos que **NO** funcionan: la fila de estrellas (su llenado *es* el
  refinamiento), el hexágono de slot (`None` en ambos), el botón de acción (dice `reemplazar` en las
  dos).
- Estrellas: llena **0.342-0.363**, vacía **exactamente 0.000**. La separación es absoluta.
- Rareza por hue del badge, **varianza cero**: **S=22.0 · A=155.0 · B=98.0**.
- Botón sobre 40 fixtures: **35 `reemplazar` + 5 `desequipar`**, 0 fallos.
- Tenencia por **nitidez**, no saturación: libres ≤4.75, con dueño ≥51.98 → **11× de gap sin
  solape**. Presencia pasó de confundir libre con fallo a **40/40**; recortes **28/28** de los que
  tienen dueño.
- Dueño: el plan pedía ≥35/40, medido **26/40 con recorte, 13/40 nombrados**.

### Gacha (S27/S28)
Detección **15/15** (conf 0.958-1.000) · canal **6/6** · rareza por tile **70/70** sin abstenciones
· W-Engines rango B **90 %** (54/60). **Identidad de agentes NO funciona** y quedó así.

### Desmontaje
Contador `0/300` → `3/300` en vivo, destildado `−1 → 2/300`, cobertura **3/3**, DB con el mismo
sha256 al principio y al final. **95 tests nuevos** en 6 archivos.

### S18
14 fixtures: **13 llegan a nombre + 11/11**, incluidos los 2 Disruptivos. Las pantallas que filtran
stats no llegan a 11/11 ninguna.

### Suites del mes
599 → 704 → 822 → 841 → 845 → 926 → 1226 passed.

---

## Hipótesis refutadas y caminos descartados

Lo más caro de regenerar, y lo primero que tira un resumen genérico.

| se creía | lo que midió |
|---|---|
| bajar el umbral S2 pesca el evento de doble recompensa | **reabre FP** a ~0.72. La solución fue un template dedicado, no un umbral laxo |
| `green_ratio` detecta S10 | **no separa**: Menu_Pausa da 0.377, dentro del rango de S10 real (0.0-0.503), y varias S10 reales dan 0.0 — ni siquiera es discriminante positivo. Rama removida |
| las líneas horizontales del panel central detectan S18 | demasiado genérico: cualquier menú con separadores lo dispara. Rama removida |
| se puede capturar la ventana tapada, tipo Discord | **descartado**: ZZZ es DirectX → `PrintWindow` da frames negros; WGC es pesado de empaquetar y roza RNF-03 |
| la identidad del PJ falla por falta de datos | **falso** — era lógica. La hipótesis inicial estaba equivocada |
| los folders `17_..._libres` / `06`/`07` nombran el estado del detector | **11/11 → S17** a conf 1.00. Los nombres de carpeta son etiquetas organizativas |
| las secciones del "Obtenido" se cortan por el gap vertical | **descartado**: 0.123 vs 0.171, margen frágil. El header es la única fuente |
| las refs del dígito de otra pantalla ayudan | **0 ok / 11 WRONG**: peores que no tener refs |
| un matcher con clases faltantes se abstiene | **inventa**, 6/11 con score hasta 0.799 |
| el verify de S26 cuesta < 60 ms (presupuesto del plan) | **9× más**: Tesseract 533 ms, Paddle 124-235 ms. La banda de una línea era peor **en las dos** (25/40) |
| el ATK base se lee por el orden de las líneas | rompía **20 de 40 fixtures**: Paddle devuelve el número con `y1` unos píxeles menor. La columna es estable, el orden no |
| un recorte fijo agarra la fila de estrellas | se corre **~42 px** según el nombre envuelva a dos líneas |
| el área saturada distingue un avatar de un hueco | **se solapa**: los libres con resplandor dan blobs de hasta 8002 px², más que varios avatares reales |
| el techo del nombrado lo pone el arma | **no**: los discos de control dan tasa parecida (6/10 vs 13/26). El techo es la librería, que además **no existía en la ruta de runtime** |
| el loop del monitor se quedó mudo 8 minutos | **falsa alarma**. Igual quedó la instrumentación, para que el próximo silencio sea legible |
| el bench del desmontaje medía tiempo | **mintió tres veces**: `thread_time` avanza de a 15.625 ms. *(Corregido recién el 2026-08-12.)* |

---

## Dónde vive la autoridad

| tema | archivo |
|---|---|
| estados y verificación | `app/core/detector.py` (`_VERIFICATION_REGISTRY`) |
| grilla y franjas de S2 | `app/core/parser_s2.py` (`count_reward_rarity_strips`, `_grid_region`) |
| nodos de farmeo | `app/resources/farm_nodes.toml` + `app/core/farm_nodes.py` |
| contexto S13→S2 | `app/core/farm_session.py` |
| panel de arma | `app/core/parser_weapon_s26.py` |
| escritura de discos | `app/core/sync_equip.py` |
| upgrade PRE→POST | `app/core/sync_upgrade.py` |

**Dos decisiones de arquitectura de julio que siguen en pie:**
- **El estado final del upgrade lo da S17, no S10.** S10 muestra el preview; la confirmación viene
  de la pantalla siguiente.
- **El toast es observacional y no depende de la DB** (rediseño v3 del S23). La v1 ataba la
  corrección de la DB a atrapar el diálogo y dejaba filas duplicadas cuando no lo atrapaba.

---

## Qué quedó abierto en julio, y qué pasó después

| abierto en julio | estado hoy |
|---|---|
| gate de foco de ventana activado por default | **revertido el 30-07** por pedido repetido de Daniel: la captura no debe cortarse sola. Se resigna el FP de la ventana encima — y ese mismo FP reapareció el **2026-09-08**, cuando el OCR leyó el panel de la propia app como si fuera un arma |
| SPEC del invariante `equipado`/`agente_asignado` | **sigue sin implementar** — esperaba a re-sincronizar la DB |
| censo inicial de la cuenta (plan) | ejecutado: discos en agosto, **armas en septiembre** |
| identidad de agentes en el gacha | sigue sin funcionar |
| `Branch & Blade Song` sin package badge | abierto |
| `Hado emplumado` no está en `disc_sets` | cerrado por las migraciones `_18`/`_24`/`_25` (30/30 sets) |
| denominador `/N` del S21 | abierto |
| dueño `incierto` en las 4 armas del QA | causa: la librería no estaba en la ruta de runtime. Se restaura del snapshot de `audit/` |
| S23 vuelca un PNG por cada diálogo de **arma** | motivó la desambiguación S23/S29 de agosto |

# Latencia del log en S9: lo que midieron las pasadas A y B

**2026-09-16 / 17.** Sigue a `2026-09-15_FIX_El_reloj_de_la_frescura_media_el_epoch_y_la_espera_la_pone_el_warmup.md`
(Fase 0, el instrumento). Esto es la Fase 2 del plan "latencia del log + censo de discos": bajar la
espera entre que Daniel mira un disco en el inventario (S9) y que sale su línea en el log, que es su
señal para pasar al siguiente. Antes del censo completo de 385 discos.

Commits: `841497a` (paso 2.0) · `f7a7efb` · `b0bb89c` · `53a27a9` · `4614bd0` (arreglos) ·
`2567fa5` (duplicado) · `06c6888` (revert de la caché del header).

## Resultado en una tabla

> ⚠️ **CORREGIDO el 2026-09-20 — el −18 % de abajo no se sostiene.** Los dos titulares (3109 y
> 2562) son **el quinto valor de diez muestras**, y el bootstrap de sus medianas da intervalos que
> **se solapan casi por completo** (A: 2641-3703 · B: 2188-3305). No hay evidencia de que la espera
> haya bajado. El censo posterior (n=383, 3547 ms) resultó **indistinguible de la Pasada A**, o sea
> del estado previo. Lo demás de este doc sigue en pie: los defectos arreglados, la caché revertida
> por acertar 0/72 y el OCR del panel como tramo grande. Detalle, remuestreo y la regla que faltaba:
> [2026-09-20_QA_El_menos_18_por_ciento_no_existia.md](2026-09-20_QA_El_menos_18_por_ciento_no_existia.md).

Sólo la ventana en S9 de cada pasada, 10-11 discos, readonly, `-Metrics`.

| | Pasada A (16-09 22:12) | Pasada B (17-09 00:32) | |
|---|---|---|---|
| **click→log** (la espera real) | p50 **3109** · p90 3828 ms | p50 **2562** · p90 3375 ms | **−547 ms (−18 %)** |
| disco→log (la lectura en sí) | 1890 | 1891 | no se tocó |
| discos que pasaron por warmup | 2 | **0** | los LIBRES ya no esperan |
| lecturas descartadas (`desc`) | 0 | **0** | el despacho rápido no lee frames animados |
| `detector` (classify) en S9 | 499 | 509 | la caché del header no ahorró nada |
| OCR del panel (`ocr_bboxes`) | sin medir | **p50 1608 ms** | el tramo más grande que queda |

La ganancia real (0,55 s) es la mitad de lo estimado (~1 s): el contador `re-armados=9` dice que el
panel muchas veces seguía moviéndose en la pasada de confirmación, y cada pasada en S9 dura ~1 s.

## 1 · Paso 2.0 — instrumento y diagnóstico (`841497a`)

- **"Salir" no guardaba las métricas.** Las tres salidas (la X, la bandeja, el auto-restart del
  watchdog) llaman a `QApplication.quit()` y nada estaba conectado a `aboutToQuit`: el proceso
  terminaba sin `Monitor.stop()`, que es quien vuelca el buffer. Cada pasada perdía su última
  tanda (la Pasada 1 quedó en 500 muestras exactas y le faltaba el disco 10). Verificado en vivo
  después: `[metrics] 78 muestras volcadas` + `Monitor detenido` al cerrar.
- **`frescura_disco_click_a_log`**: se abre cuando el LOOP RÁPIDO ve el disco nuevo, no en el
  despacho. Tapa el punto ciego de `frescura_disco_a_log` (que no ve la espera hasta el primer
  despacho). Sólo abre si no hay uno abierto: la animación del panel cambia la firma varias veces.
- **La línea de S9 decía `dueno=-` para tres casos distintos**: LIBRE, "tiene dueño y no sé quién"
  (se guarda marcado) y "no se leyó el badge" (no se guarda). Ahora: `dueño=X` / `LIBRE` /
  `dueño=? (sin identificar)` / `dueño=? (badge sin leer)`, más `(agg Nc · D desc · W warm)`.
- "¿Es otro disco?" pasó a tener UNA respuesta (`_s9_firmas_distintas`), usada por el despacho y
  por el loop: con dos comparaciones la métrica mediría la diferencia entre dos umbrales.

## 2 · Pasada A — contradijo el diagnóstico (y ahí paró todo, como estaba escrito)

La hipótesis de la Pasada 1 era "el primer despacho no emite y el segundo sí". **Falso**: los 8
discos con dueño dieron `(agg 1c · 0 desc · 0 warm)` — la primera lectura alcanzaba.

⭐ **Dos errores míos, los dos de medición:**

1. **Mediana de una distribución bimodal.** `dispatch:S9` mezcla despachos que no leen (11-148 ms,
   el disco ya salió) con lecturas reales (1,8-3,0 s). En la Pasada 1 la mediana dio 135 ms y se
   tomó como "el costo de leer un disco". Es la misma forma que el centroide bimodal del
   2026-08-18. Queda en la práctica **C1**.
2. **El OCR más caro nunca se había medido.** `OcrProxy` instrumentaba sólo `text`;
   `text_with_bboxes` —el panel de S9, S17, S26, S3, S10, desmontaje— no. Medido offline sobre las
   capturas: **735 ms contra 89** de una lectura de texto (8,2×). Explica también los ~2,5 s por
   arma sin atribuir de S26. Queda en la práctica **C3** ("una métrica que parece completa").

**Reparto de los ~3,1 s (p50, S9)**: esperar la cadencia ~1,0 s · OCR del panel ~1,5 s · dos OCR de
texto ~0,4 s · dueño (badge + match, medido offline) 12 ms. Más un tramo que ninguna métrica ve: del
click a que el loop lo note (classify en S9 = 499 ms; el OCR del header se lleva 315, el 62 %).

Los 2 LIBRES dieron `(agg 2c · 0 desc · 1 warm)`: bug de entrada al warmup confirmado.

**Decisión de Daniel:** el OCR del panel va en fase propia DESPUÉS del censo de discos y ANTES del
de engines (mismo código: una sola validación de precisión sirve a los dos censos).

## 3 · Los arreglos

| commit | qué | resultado en vivo |
|---|---|---|
| `f7a7efb` | medir `text_with_bboxes` y `number` (`ocr_bboxes`, `ocr_number`), con un test que deriva los métodos de `OcrBackend` y exige que el proxy los mida TODOS | ✅ `ocr_bboxes` p50 1608 ms |
| `b0bb89c` | un disco LIBRE no entra al warmup (el criterio estaba en la salida, no en la entrada) | ✅ 0 warm |
| `3fb660c` | caché del OCR del header por BYTES del recorte | ❌ 0/72 aciertos → revertida (`06c6888`) |
| `53a27a9` | despacho rápido con confirmación de panel quieto | ✅ −0,55 s, 0 desc |
| `4614bd0` | comentarios con tiempos vencidos (el "10 fps" que originó todo) | — |
| `2567fa5` | filtro de repetidos por set RESUELTO | apareció en la Pasada B, ver §5 |

### El despacho rápido: por qué no alcanzaba con leer en el acto

Hallazgo antes de implementar: **el despacho lee el MISMO frame en el que el loop vio el cambio**, y
ese frame puede estar a mitad de la animación del panel. La espera de cadencia de antes le daba
tiempo a asentarse sin querer — por eso la Pasada A dio 0 descartes. Leer en el acto podía costar
dos lecturas de ~1,9 s por disco.

La regla implementada: la pasada que VE el disco no lo lee (se suprime el despacho de cadencia de esa
pasada); la siguiente compara la firma ANTES de clasificar y, si coincide, lee ya y saltea el
`classify` y el OCR del slot de esa pasada. Tope de 3 re-armados para que un panel que no se asienta
nunca degrade a la cadencia de siempre. `DANIBOD_S9_DESPACHO_RAPIDO=0` deja el comportamiento exacto
de antes.

Los tests corren el `Monitor._run` VERDADERO con frames inyectados (`app/tests/unit/arnes_loop_monitor.py`),
no leen su código fuente. Se predijo pasada por pasada qué se despacha y se cumplió exacto.

## 4 · Pasada B

Ver la tabla de arriba. Contadores al cerrar: `[s9-despacho-rapido] confirmados=14 re-armados=9
abandonados=0` · `[header-cache] aciertos=0 fallos=72`.

**La caché del header no acertó nunca.** Los tests pasaron porque comparaban el frame con `a.copy()`,
idéntico byte a byte POR CONSTRUCCIÓN: probaron el mecanismo, no la premisa (queda en **A1**). Dos
explicaciones que estos datos no separan: (a) el header cambia de píxeles entre frames en vivo;
(b) el OCR del header devuelve vacío en vivo, y un vacío no se guardaba a propósito (para no dejar a
`_verify_s30` sin reconocer armas). Si se retoma: contar vacíos aparte primero.

## 5 · Lo que la Pasada B destapó: una lectura duplicada

`Firmamento · slot 2 · ATK · Pyrois` salió DOS veces (00:32:28 y :31), como `Ilameante` y
`llameante`. Dos causas que se suman:

1. **Relectura del mismo disco**: se leyó un frame que todavía no estaba del todo quieto; al
   asentarse, la firma cambió, el loop lo vio como disco nuevo, confirmó y releyó (~1,9 s de loop
   bloqueado). Pasó en 1 de 11 discos.
2. **El filtro de repetidos comparaba el nombre del set tal como lo leyó el OCR.** Es el bug del
   2026-08-18, arreglado en la persistencia (compara `set_id` resuelto) pero no en la emisión.

`2567fa5` arregla la 2: la clave de emisión usa `DiscSetRepo.resolve_id`, la misma autoridad que la
persistencia (verificado contra la DB: las dos grafías dan el set 53). `_disc_identity` no se tocó
porque arma claves serializadas del mapa de equipamiento. **La 1 queda abierta**: evitar la
relectura sin romper los 22 pares de gemelos no es trivial.

En la DB no habría duplicado (la persistencia ya compara por set resuelto); el daño era la señal:
dos líneas por un disco.

## 6 · Errores de proceso que conviene no repetir

- **Un sabotaje "pasó" porque nunca se aplicó**: el script no encontró el texto a reemplazar y el
  test corrió contra el código arreglado. El mensaje del commit ya decía "sabotaje: rojo". Se
  repitió bien. Regla: el script de sabotaje tiene que AFIRMAR que reemplazó (`count == 1`) y
  terminar con error si no — y hay que mirar esa salida antes de leer el resultado del test.
- **Una continuación de línea con `\` se colapsó** al escribir código desde un string de Python
  (`\` + salto de línea adentro de `"""` es continuación). La lógica andaba, el formato no. Para
  condiciones partidas, paréntesis.
- **Los heredocs de bash con código largo se rompen** por comillas. Para ediciones grandes: script
  en el scratchpad con la herramienta de escritura, y correrlo.
- **Un test pasaba por la granularidad del reloj** (C2): `monotonic()` avanza de a 15,625 ms, tres
  llamadas seguidas devuelven lo mismo y "no se re-abrió" parecía cierto aunque se re-abriera. Reloj
  controlado.

## 7 · Pendientes

| qué | dónde | estado |
|---|---|---|
| **Botones en vez de hotkeys** (F8 cerrar censo, F10 pausa; F9 no lleva botón, lo cubre la bandeja) | Fase 2B | **siguiente**; diseño en el plan |
| **`nivel` 0 como centinela** (23 discos, 4 trampas localizadas) | Fase 3 | antes del censo |
| censo completo de 385 discos por S9 | Fase 4 | después de 2B y 3 |
| **OCR del panel** (~1,6 s en vivo, compartido con S26) | Fase 2C | después del censo de discos, antes del de engines |
| relectura del mismo disco al asentarse el panel (1/11, ~1,9 s) | S9 | abierta |
| **OCR del slot en CADA pasada del loop en S9** (`raw_state.slot = extract_s9_slot`), que el handler de S9 no usa (relee el slot por su cuenta) | loop | hallado, no tocado (fuera de plan) |
| caché del header: ¿píxeles o texto vacío? | detector | revertida; hipótesis anotadas |
| S17 sin baseline de latencia (no está en el camino del censo) | — | — |
| freeze de la UI al arrancar el OCR (carga del modelo ~6,8 s) | — | conocido, fuera de alcance |
| engines: segundo censo de QA | — | después del de discos |

## Verificación

- Suite: 2929 → **2945** (paso 2.0) → **2967** (arreglos), 0 failed, 0 skipped; sha256 de la DB de
  dominio sin cambios en todas. Los dos últimos commits (`2567fa5`, `06c6888`) se escribieron con la
  suite completa corriendo: ver el estado de su push en `git log origin/main..HEAD`.
- Sabotajes: 6 en el paso 2.0 y 11 en los arreglos, todos detectados (uno repetido porque la primera
  vez no se aplicó).
- Pasadas en vivo: A y B, readonly, con la ventana del juego en 2560×1440. ⚠️ Una sesión intermedia
  encontró la ventana en **1296×728** y detectó `S11` con confianza 0,53-0,60 (falsos positivos:
  las plantillas están calibradas para la resolución completa). No hubo lecturas de discos en ella.

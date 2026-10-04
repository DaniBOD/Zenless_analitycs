# SPEC · Hito "El ritmo de Daniel": latencia y robustez de los datos in-game (2026-10-02)

> Daniel: "la idea es usar todas las herramientas/técnicas posibles para este apartado … vamos a ir
> punto por punto". Diagnóstico: `2026-10-02_DIAG_El_ritmo_de_Daniel_vs_el_loop.md`.

## Problema

A su ritmo normal (un click por segundo), la app pierde eventos. El 2026-10-02 quedó la DB con
418 discos contra 379 en el juego: 36 desmontados sin baja (22 + 4 sin leer, una tanda de 10 que
nunca cerró). Las causas medidas:

- el loop lee un frame cada 407 ms (p50) a 922 ms (p90) en S11;
- el detector re-clasifica la pantalla en cada ciclo, aunque no haya cambiado (188 ms, el 46 %);
- el voto 2/3 del `TemporalBuffer` hace invisibles las pantallas que duran menos de ~2 ciclos;
- la app no sabe nada de los inputs: todo sale de polling de píxeles.

## Decisiones de Daniel (2026-10-02)

- **Clicks del mouse: sí**, sólo lectura (`pynput.mouse.Listener`), con el juego enfocado. Ampliación
  de RNF-03 (hasta acá sólo nombraba el listener de teclado).
- **Grabador + reproductor: sí.** Una sesión grabada "a su ritmo" es el banco de pruebas de todas
  las fases.
- **Medir primero**, y punto por punto; el censo, al final.

## Fases

| fase | qué | estado |
|---|---|---|
| 0 | push de lo de hoy + corrección de #478/#484 | ✅ |
| 1 | grabador (`app/core/grabacion.py`, `tools/grabar_sesion.py`), clicks (`app/core/clicks.py`), verdad de tierra y reproducción (`app/core/ritmo.py`, `tools/verdad_de_sesion.py`, `tools/reproducir_sesion.py`); línea de base con una sesión de Daniel | ✅ (2026-10-03) |
| 2 | no re-clasificar en un estado estable (`ScreenDetector.sigue_en`) | ✅ (ganancia chica: loop p90 1036→854; S11 dentro del ruido) |
| 3 | pantallas breves (promoción de modales verificados) y la tanda que se cierra sin el "Obtenido" | ✅ (S25 vista 0,33→1,67 de 2) |
| 4 | los clicks como disparador de la captura y como evidencia (S11, S10, S22) | — |
| 5 | capturar rápido, procesar después (sólo si 2-4 no alcanzan) | — |
| 6 | censo de discos (S9) y QA final grabado | — |

## Metas (contra la línea de base grabada)

- S11: ≤ 5 % de discos sin leer a un click por segundo; 100 % de tandas confirmadas cerradas.
- S10: 100 % de niveles subidos escritos.
- S22: sin duplicados ni faltantes.
- `loop_period` p50 ≤ 200 ms en estados estables.
- RAM idle < 200 MB (RNF-06).

## Cómo se mide

1. `tools/grabar_sesion.py --minutos N` mientras Daniel juega (sin la app): frames + clicks a
   `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\grabaciones\<fecha>`.
2. `tools/verdad_de_sesion.py <carpeta>`: la verdad de tierra, frame por frame y sin apuro →
   `verdad.json`.
3. `tools/reproducir_sesion.py <carpeta>`: la grabación hace de pantalla en tiempo real contra el
   controlador y el monitor de verdad (DB en copia) → `audit/ritmo/<carpeta>_<commit>.md`.

La Fase 1 vale si la reproducción del código de hoy reproduce las pérdidas de hoy.

## Línea de base (2026-10-03)

Grabación `20261003_111858` (2 min 9 s, 347 frames, 51 clicks, 0 descartados): dos desmontajes
rápidos (17 discos en ~8 s y 4) y una mejora 0→3. Reproducida contra `332f3d6` (`audit/ritmo/20261003_111858_base.md`):

| KPI | verdad | en vivo (11:20) | reproducción `base` |
|---|---|---|---|
| S11 · discos marcados con datos | 21 | 7 (33 %) | 8 (38 %) |
| S11 · tandas confirmadas y cerradas | 2 | 2 | 2 |
| S10 · niveles subidos vistos | 3 | (leyó el PRE ya en Nv 3) | 3 |
| pantalla breve S25 vista | 2 | 0 | 0 |
| `loop_period` p50 / p90 | | | 328 / 937 ms |
| `detector` p50 | | | 171 ms |

**El banco reproduce las pérdidas en vivo** (33 % vs 38 % con datos; la confirmación S25 nunca se
ve, en ninguno de los dos) → la Fase 1 vale y las fases siguientes se miden contra esta tabla.

Falta en la línea de base: un desmontaje **cancelado** y el **Obtenido de baterías** (S22). Se
suman en la próxima grabación.

## Fase 2 · resultado (2026-10-03)

3 reproducciones por versión de `20261003_111858` (la reproducción en tiempo real tiene varianza
grande: S11 entre 5 y 9 con el mismo código):

| | S11 con datos (de 21) | tandas (de 2) | loop p50 / p90 | detector total |
|---|---|---|---|---|
| base (`DANIBOD_SIN_SIGUE=1`) | 8 · 9 · 5 → 7,3 | 2 · 2 · 1 | 323 / 1036 ms | 36,6 s |
| fase 2 | 9 · 6 · 9 → 8,0 | 2 · 1 · 2 | 302 / 854 ms | 32,8 s |

El atajo es seguro (0 "sigue" falsos medidos) y baja el p90, pero en S11 no mueve la aguja: sólo
cubre pantallas de template propio (la sesión pasa mucho en S12/S4/S15) y en S11 el cuello es el
**despacho** (OCR del contador en cada ciclo + el del panel, p90 ~550 ms), no la clasificación.
Conclusión para el orden: la mejora real de S11 está en capturar un frame por click y procesarlo
después (fases 4 y 5); la fase 3 (S25 breve, tanda que cierra en 0/300) va antes por barata.

### Hallazgo: ZZZ corre como administrador (UIPI)

Un proceso sin elevar no ve los clicks sobre el juego (pynput: 0, `GetAsyncKeyState`: 0, en pleno
combate). Elevado, sí. Decisión de Daniel (2026-10-03): **un ayudante mínimo elevado que sólo lee
clicks** (`tools/clicks_elevado.py`); la app sigue sin elevar. El grabador también corre elevado
(`Start-Process -Verb RunAs`, se corta con el archivo `PARAR`). Para la Fase 4 el ayudante le pasa
los clicks a la app (archivo/pipe).

## Commits

| commit | fase | qué |
|---|---|---|
| `5e964c0`…`b8f8636` | 0 | los 6 commits del duplicado y la mejora en vivo (suite 3643) |
| `f04cb45` | 0 | data: #478 borrado, #484 dado de baja (418 → 416 activas) |
| `a8cb8c5` | 1 | `ClickListener` (9 tests, 5 sabotajes) |
| `90dfed1` | 1 | grabador de sesiones (6 tests, 6 sabotajes) |
| `bd80797` | 1 | verdad de tierra + reproducción (7 tests, 6 sabotajes) |
| `9ad3692` | — | data: farmeo del 2026-10-03 (16 drops S3, 1 baja; 431 activas) |
| `2e69319` | 1 | grabador elevado + `clicks_elevado.py` (UIPI) + 4 escritores + `PARAR` |
| `332f3d6` | 1 | la verdad ignora parpadeos de S12 y sigue la confirmación hasta el Obtenido |
| `663e91f` | 2 | `sigue_en` + `_clasificar` (red 1 s, `DANIBOD_SIN_SIGUE`) |
| `ac5c8d4` | 3 | la selección vaciada tras la confirmación cierra la tanda (`cierre`) |
| `74d58dd` | 3 | S20/S24/S25 verificados se confirman con un frame (`_votar`) |

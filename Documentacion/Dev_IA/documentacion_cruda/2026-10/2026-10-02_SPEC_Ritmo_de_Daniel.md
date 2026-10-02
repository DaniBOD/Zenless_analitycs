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
| 0 | push de lo de hoy + corrección de #478/#484 | en curso |
| 1 | grabador (`app/core/grabacion.py`, `tools/grabar_sesion.py`), clicks (`app/core/clicks.py`), verdad de tierra y reproducción (`app/core/ritmo.py`, `tools/verdad_de_sesion.py`, `tools/reproducir_sesion.py`); línea de base con una sesión de Daniel | en curso |
| 2 | no re-clasificar en un estado estable (`ScreenDetector.sigue_en`) | — |
| 3 | pantallas breves (promoción de modales verificados) y la tanda que se cierra sin el "Obtenido" | — |
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

## Commits

| commit | fase | qué |
|---|---|---|

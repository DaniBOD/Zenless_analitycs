# BUG — Fuga de memoria en sesiones largas de cosecha (RNF-06) · 2026-06-12

**Estado:** ABIERTO · prioridad ALTA antes de la corrida definitiva C.5 (~200 discos).
**Severidad:** bloqueante para sesiones largas; no bloquea sesiones cortas (<~10-15 PJs).

## Síntoma

Durante la cosecha full-roster (Fase 5R.C), la app deja de responder tras una sesión larga.
La UI se cuelga; el juego/captura siguen pero el panel no reacciona.

## Evidencia (2026-06-12)

- Proceso `DaniBOD_ZZZ_Analytics` PID 8788, ~83 min de corrida (relanzado ~14:42).
- `Get-Process`: **RAM ≈ 11.960 MB (~12 GB)**, `Responding = False`, CPU 3670 s, 25 threads.
- Objetivo RNF-06: **RAM idle < 200 MB**, CPU polling < 3 %. Violación clara (~60×).
- Tras kill + relaunch limpio: PID 19284, **549 MB**, `Responding = True` (549 MB ya es alto
  al arranque — Paddle + 443 refs de badge cargadas; el problema es el CRECIMIENTO, no el piso).
- Crecimiento monótono durante la sesión → fuga, no pico transitorio.

## Causa probable (a confirmar con profiling)

El monitor poll-ea a ~10 fps capturando frames de **2560×1440** (~11 MB/frame). 12 GB ≈ ~1100
frames retenidos, o un leak lento de arrays/objetos derivados. Candidatos a auditar:

- **Frames MSS** no liberados por ciclo (capturer.py / monitor loop) — `mss.grab` retornando
  buffers que quedan referenciados.
- **Crops de badge / numpy arrays** del voto S17 (`_sample_s17_owner`, 10 fps) o del harvest
  (`learn_s17` → `add_reference`) retenidos.
- **Qt:** log de la consola del LivePanel sin `maximumBlockCount`, o QPixmap/QImage del toast/
  preview acumulados.
- Aggregator de discos / diccionarios del monitor que crecen sin poda.

## Workaround actual (validado)

Reiniciar la app cada ~10-15 PJs. `equip_map` (`audit/equip_map_<fecha>.json`, escritura
sincrónica) y `avatar_badge_v2.npz` (badges) **persisten y se acumulan entre reinicios** — un
reinicio NO pierde cosecha. Para sesiones cortas (terminar 1-3 PJs) no hace falta.

## Próximos pasos (cuando se trabaje)

1. Profiling con `tracemalloc` / `memory_profiler` sobre una corrida cronometrada (medir RAM
   cada N min, aislar el array/objeto que crece).
2. Auditar el loop de captura del monitor: asegurar que cada frame/crop se libere por ciclo
   (no quedar referenciado en listas/atributos del Monitor).
3. Acotar buffers per-frame y poner `maximumBlockCount` en el log de UI.
4. (Mitigación de producto) Watchdog de RAM con auto-restart del monitor en corridas largas.

## Referencias

- RNF-06 (CLAUDE.md §2): toast <500 ms, RAM idle <200 MB, CPU polling <3 %.
- `Documentacion/QA/QA-06_Performance_y_UX.md` (decorator `@measure_latency`, tabla `metrics_latency`).
- Contexto: cosecha Fase 5R.C — `project-context-IA.md`, este Dev_IA.

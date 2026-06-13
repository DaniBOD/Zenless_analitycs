"""Diagnóstico de memoria (RNF-06) — heartbeat env-gated `DANIBOD_MEM_DIAG`.

Fase 0 del fix de la fuga RNF-06: aislar el culpable sin adivinar. Loguea cada ~N
segundos el **RSS** (working set del proceso) + el heap Python (`tracemalloc`) + un
contador global de inferencias OCR. La firma diagnóstica clave:

    RSS crece monótono PERO el heap Python (pyheap) queda plano
        => la fuga es NATIVA (C++ de paddlepaddle / cv2), invisible a tracemalloc.

Sin dependencias nuevas: el RSS sale de `win32process` (pywin32 ya está bundleado),
con fallback a ctypes/psapi. Todo es no-op salvo que `DANIBOD_MEM_DIAG` esté seteado,
así que es seguro dejarlo cableado en producción (cero costo cuando está apagado).
"""
from __future__ import annotations

import logging
import os
import time
import tracemalloc

log = logging.getLogger("app.core.mem_diag")

_INTERVAL_S = 20.0
_last_hb = 0.0
_ocr_calls = 0
_tm_started = False


def enabled() -> bool:
    return os.environ.get("DANIBOD_MEM_DIAG", "") not in ("", "0", "false", "False")


def bump_ocr(n: int = 1) -> None:
    """Incrementa el contador global de inferencias OCR (lo llama el backend OCR)."""
    global _ocr_calls
    _ocr_calls += n


def ocr_calls() -> int:
    return _ocr_calls


def mem_counters() -> tuple[float, float]:
    """(WorkingSet, Commit) del proceso actual en MB. (0,0) si no se puede leer.

    El **commit charge** (`PagefileUsage`, ≈ private bytes de Get-Process) es el metric
    MONÓTONO para la fuga: el WorkingSet lo recorta Windows al paginar cuando la app está en
    background, así que baja aunque la memoria siga creciendo. `win32process` (pywin32 ya es
    dep) devuelve `PROCESS_MEMORY_COUNTERS` con `WorkingSetSize` + `PagefileUsage`.
    """
    mb = 1024 * 1024
    try:
        import win32api
        import win32process
        info = win32process.GetProcessMemoryInfo(win32api.GetCurrentProcess())
        # PagefileUsage = commit privado (≈ PrivateUsage); PrivateUsage solo viene en la
        # struct EX, que win32process no expone → usamos PagefileUsage.
        commit = info.get("PrivateUsage") or info.get("PagefileUsage", 0)
        return info["WorkingSetSize"] / mb, commit / mb
    except Exception:
        pass
    # Fallback: ctypes + psapi (PROCESS_MEMORY_COUNTERS base; commit = PagefileUsage).
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _PMC()
        counters.cb = ctypes.sizeof(_PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / mb, counters.PagefileUsage / mb
    except Exception:
        pass
    return 0.0, 0.0


def rss_mb() -> float:
    """Working set del proceso actual en MB (compat)."""
    return mem_counters()[0]


def maybe_start() -> None:
    """Arranca tracemalloc la primera vez (si el diag está habilitado)."""
    global _tm_started
    if not _tm_started and enabled():
        try:
            tracemalloc.start(10)
            _tm_started = True
            log.info("[mem] tracemalloc iniciado (DANIBOD_MEM_DIAG=1)")
        except Exception:
            log.debug("tracemalloc no se pudo iniciar", exc_info=True)


def heartbeat(extra: dict | None = None) -> None:
    """Loguea un heartbeat de memoria si está habilitado y pasó el intervalo (~20s).

    `extra` agrega contadores del caller (p.ej. ticks del loop, estado actual). El
    throttle es interno → es seguro llamarlo en cada iteración del loop de monitoreo.
    """
    global _last_hb
    if not enabled():
        return
    maybe_start()
    now = time.monotonic()
    if now - _last_hb < _INTERVAL_S:
        return
    _last_hb = now

    ws, priv = mem_counters()
    parts = [f"RSS={ws:.0f}MB", f"priv={priv:.0f}MB", f"ocr_calls={_ocr_calls}"]
    if extra:
        parts += [f"{k}={v}" for k, v in extra.items()]

    tm_line = ""
    try:
        if _tm_started:
            cur, _peak = tracemalloc.get_traced_memory()
            parts.append(f"pyheap={cur / 1048576:.1f}MB")
            snap = tracemalloc.take_snapshot()
            top = snap.statistics("lineno")[:3]
            tm_line = " | py-top: " + "  ".join(
                f"{os.path.basename(s.traceback[0].filename)}:{s.traceback[0].lineno}="
                f"{s.size / 1048576:.1f}MB"
                for s in top
            )
    except Exception:
        pass

    log.info("[mem] %s%s", "  ".join(parts), tm_line)

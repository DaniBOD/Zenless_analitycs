"""Analiza los heartbeats `[mem]` del app.log (Fase 0 del fix RNF-06).

Extrae la serie temporal RSS / pyheap / ocr_calls y reporta tasas de crecimiento.
La firma diagnóstica: si **RSS crece** monótono pero **pyheap queda plano** → la fuga
es NATIVA (paddlepaddle C++), invisible a tracemalloc → el fix va por flags/recycle de
Paddle, no por objetos Python.

Uso:
    .venv/Scripts/python.exe tools/parse_mem_diag.py                # app.log por defecto
    .venv/Scripts/python.exe tools/parse_mem_diag.py <ruta_app.log>
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_KV = re.compile(r"(\w+)=([\d.]+)")  # RSS=123MB ocr_calls=4 ticks=9 pyheap=1.2MB


def _default_log() -> str:
    return os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "DaniBOD_ZZZ_Analytics", "app.log"
    )


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else _default_log()
    if not os.path.exists(path):
        print(f"No existe el log: {path}")
        return 1

    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    # Analizar SOLO la última sesión: el app.log acumula varias corridas y cada arranque
    # escribe "Logging a archivo iniciado". Cortamos desde el último marcador para no
    # mezclar la curva del build viejo con la nueva (antes/después limpio).
    starts = [i for i, ln in enumerate(lines) if "Logging a archivo iniciado" in ln]
    if starts:
        lines = lines[starts[-1]:]

    rows = []
    for line in lines:
        if "[mem]" in line and "RSS=" in line:
            mts = _TS.match(line)
            if not mts:
                continue
            t = datetime.strptime(mts.group(1), "%Y-%m-%d %H:%M:%S")
            kv = {k: float(v) for k, v in _KV.findall(line.split("[mem]", 1)[1])}
            if "RSS" not in kv:
                continue
            st = re.search(r"\bst=(\S+)", line)
            rows.append((t, kv, st.group(1) if st else "-"))

    if not rows:
        print(f"Sin heartbeats [mem] en {path}. ¿Corriste con DANIBOD_MEM_DIAG=1?")
        return 1

    t0 = rows[0][0]
    print(f"Log: {path}")
    print(f"Heartbeats: {len(rows)}  |  ventana: "
          f"{(rows[-1][0] - t0).total_seconds() / 60:.1f} min\n")
    # `priv` (private bytes) es el metric MONÓTONO; el WorkingSet (RSS) lo recorta Windows al
    # paginar → engañoso. Si el log no tiene priv (instrumentación vieja), cae a RSS.
    def leak_metric(kv: dict) -> float:
        return kv.get("priv", kv.get("RSS", 0.0))

    has_priv = any("priv" in kv for _, kv, _ in rows)
    label = "priv_MB" if has_priv else "RSS_MB"
    print(f"{'t+min':>7} {label:>8} {'dMEM':>7} {'pyheap':>8} "
          f"{'ocr':>7} {'docr':>6}  state")
    print("-" * 60)
    prev = None
    for t, kv, st in rows:
        tmin = (t - t0).total_seconds() / 60
        mem = leak_metric(kv)
        py = kv.get("pyheap", float("nan"))
        ocr = kv.get("ocr_calls", 0.0)
        dmem = mem - prev[0] if prev else 0.0
        docr = ocr - prev[1] if prev else 0.0
        print(f"{tmin:7.1f} {mem:8.0f} {dmem:+7.0f} {py:8.1f} "
              f"{ocr:7.0f} {docr:+6.0f}  {st}")
        prev = (mem, ocr)

    # Tasas globales
    dt_min = (rows[-1][0] - t0).total_seconds() / 60 or 1e-9
    m0, mN = leak_metric(rows[0][1]), leak_metric(rows[-1][1])
    py0, pyN = rows[0][1].get("pyheap", 0), rows[-1][1].get("pyheap", 0)
    ocrN = rows[-1][1].get("ocr_calls", 0) - rows[0][1].get("ocr_calls", 0)
    print("-" * 60)
    print(f"{'priv' if has_priv else 'RSS'}:   {m0:.0f} → {mN:.0f} MB   "
          f"({(mN - m0) / dt_min:+.1f} MB/min)")
    print(f"pyheap: {py0:.1f} → {pyN:.1f} MB   ({(pyN - py0) / dt_min:+.2f} MB/min)")
    print(f"OCR:    {ocrN:.0f} inferencias   ({ocrN / dt_min:.0f}/min)")
    mem_rate = (mN - m0) / dt_min
    py_rate = (pyN - py0) / dt_min
    print()
    if mem_rate > 20 and py_rate < 0.5 * mem_rate:
        print("⇒ DIAGNÓSTICO: memoria crece y pyheap plano → fuga NATIVA (paddle C++). "
              "Fix por flags/recycle de Paddle.")
    elif mem_rate > 20:
        print("⇒ DIAGNÓSTICO: memoria y pyheap crecen juntos → fuga en objetos PYTHON. "
              "Auditar acumuladores/listas.")
    else:
        print("⇒ memoria estable en esta ventana (sin fuga apreciable aquí).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

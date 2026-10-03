"""Ayudante ELEVADO que sólo lee clicks sobre el juego y los anota (hito "El ritmo de Daniel").

Por qué existe (medido el 2026-10-03): ZZZ corre como administrador, y Windows (UIPI) no le
entrega el mouse de una ventana elevada a un proceso sin elevar — ni por hook (`pynput`) ni por
`GetAsyncKeyState`: 0 clicks en pleno combate. Decisión de Daniel: un proceso chiquito, aparte, que
corre elevado y SOLO lee clicks; la app sigue sin elevar.

Qué hace y qué no:
  - `ClickListener` (app/core/clicks.py): sólo el click apretado, sólo con ZZZ en primer plano,
    relativo a la ventana. Nunca envía input (RNF-03).
  - Escribe una línea por click en `--salida` (JSONL, `{"tipo": "click", "t", "x", "y", "boton"}`).
    `t` es `time.monotonic()`, que en Windows es el contador del sistema (QueryPerformanceCounter):
    el mismo reloj que ven el grabador y la app en sus procesos.
  - Termina a los `--minutos` o cuando aparece el archivo `--parar`.

Uso (pide UAC):
    Start-Process -Verb RunAs .venv\\Scripts\\python.exe "tools\\clicks_elevado.py --salida <archivo>"
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.capturer import find_zzz_window  # noqa: E402
from app.core.clicks import ClickListener  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--minutos", type=float, default=60.0)
    ap.add_argument("--parar", default=None, help="archivo cuya aparición corta la escucha")
    args = ap.parse_args()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    parar = Path(args.parar) if args.parar else salida.with_suffix(".parar")
    ventana = {"w": find_zzz_window(), "t": time.monotonic()}

    def ventana_fn():
        if ventana["w"] is None or time.monotonic() - ventana["t"] > 5.0:
            ventana["w"], ventana["t"] = find_zzz_window(), time.monotonic()
        return ventana["w"]

    cl = ClickListener(ventana_fn)
    if not cl.start():
        return 1
    visto = float("-inf")
    fin = time.monotonic() + args.minutos * 60.0
    with open(salida, "a", encoding="utf-8") as f:
        f.write(json.dumps({"tipo": "inicio_clicks", "t": time.monotonic()}) + "\n")
        f.flush()
        while time.monotonic() < fin and not parar.exists():
            for c in cl.desde(visto):
                visto = c.t
                f.write(json.dumps({"tipo": "click", "t": c.t, "x": c.x, "y": c.y,
                                    "boton": c.boton}) + "\n")
                f.flush()
            cl.evento.wait(0.2)
            cl.evento.clear()
    cl.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

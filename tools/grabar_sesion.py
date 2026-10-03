"""Graba una sesión de juego: frames + clicks con su hora (hito "El ritmo de Daniel", 2026-10-02).

Corre SOLO, sin la app (proceso aparte): la grabación es la verdad de tierra, y la app se mide
después reproduciéndola (`tools/reproducir_sesion.py`). Read-only: no toca la DB y no envía
inputs (RNF-03: lee píxeles con mss y clicks con pynput).

Guarda en `%LOCALAPPDATA%\\DaniBOD_ZZZ_Analytics\\grabaciones\\<fecha_hora>\\` (pantalla completa:
nunca al repo). ~2 MB por frame; a 8 fps sostenidos son ~1 GB por minuto en el peor caso.

Uso:
    .venv\\Scripts\\python tools\\grabar_sesion.py --minutos 20
    .venv\\Scripts\\python tools\\grabar_sesion.py --minutos 5 --fps 10 --out D:\\grabaciones\\prueba
Ctrl-C corta antes y cierra la grabación bien.

ZZZ corre como ADMINISTRADOR: para que entren los clicks, el grabador también tiene que correr
elevado (UIPI, medido el 2026-10-03: sin elevar, 0 clicks en pleno combate). Lanzarlo con
`Start-Process -Verb RunAs` y cortarlo creando el archivo `PARAR` en la carpeta de la grabación
(un proceso elevado no se corta con Ctrl-C desde otra consola).
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.capturer import find_zzz_window, get_foreground_window, is_zzz_focused  # noqa: E402
from app.core.clicks import ClickListener  # noqa: E402
from app.core.grabacion import Grabador  # noqa: E402


def _destino_por_defecto() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return Path(base) / "DaniBOD_ZZZ_Analytics" / "grabaciones" / datetime.now().strftime("%Y%m%d_%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=20.0)
    ap.add_argument("--fps", type=float, default=8.0, help="capturas por segundo (no todas se guardan)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--parar", default=None,
                    help="archivo cuya aparición corta la grabación (por defecto <carpeta>/PARAR)")
    args = ap.parse_args()

    # Píxeles físicos para mss y para pynput por igual (si no, a escala != 100 % los clicks caen
    # corridos respecto del frame).
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    ventana = find_zzz_window()
    if ventana is None:
        print("[grabar] no encuentro la ventana de ZZZ — abrí el juego primero")
        return 1
    destino = Path(args.out) if args.out else _destino_por_defecto()
    print(f"[grabar] ventana '{ventana.title}' {ventana.width}x{ventana.height}")
    print(f"[grabar] guardando en {destino}")
    print(f"[grabar] {args.minutos:g} min · Ctrl-C para cortar antes\n")

    import cv2
    import mss
    import numpy as np
    sct = mss.mss()
    mon = {"left": ventana.left, "top": ventana.top, "width": ventana.width, "height": ventana.height}

    def capturar():
        if not is_zzz_focused(get_foreground_window(), ventana.hwnd):
            return None                       # sin foco: la imagen no es del juego
        return cv2.cvtColor(np.array(sct.grab(mon)), cv2.COLOR_BGRA2BGR)

    clicks = ClickListener(lambda: ventana)
    clicks.start()
    g = Grabador(destino, capturar=capturar, clicks=clicks)
    g.iniciar(ventana=(ventana.width, ventana.height), fps=args.fps)
    t0 = time.monotonic()
    try:
        parar = Path(args.parar) if args.parar else destino / "PARAR"
        g.correr(args.minutos * 60.0, fps=args.fps, seguir=lambda: not parar.exists())
    except KeyboardInterrupt:
        print("\n[grabar] cortado a mano")
    finally:
        clicks.stop()
        descartados = g.cerrar()
    n = len(list(destino.glob("*.png")))
    print(f"[grabar] {n} frames en {time.monotonic() - t0:.0f} s · descartados {descartados}")
    print(f"[grabar] carpeta: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

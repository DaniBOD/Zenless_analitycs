"""Cosecha read-only de frames del flujo de desmontaje (QA en vivo).

Captura la ventana de ZZZ, clasifica cada frame con el detector real y guarda a
PNG solo los frames que cambian (dedupe por diferencia media). El nombre del
archivo lleva el estado y la confianza, así el fixture queda etiquetado por el
mismo clasificador que corre en producción.

Sirve para el caso donde el juego muestra una pantalla que el detector NO ve:
la verdad de tierra tiene que salir del frame real, no de deducir el log.

NO toca la DB. NO envía inputs (RNF-03: solo lee píxeles).

Uso:
    .venv\\Scripts\\python tools\\grab_desmontaje_frames.py --seconds 180
    .venv\\Scripts\\python tools\\grab_desmontaje_frames.py --out audit/frames_qa
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.capturer import capture_window, find_zzz_window  # noqa: E402
from app.core.detector import ScreenDetector  # noqa: E402


def _huella(frame: np.ndarray) -> np.ndarray:
    """Miniatura gris para comparar frames sin costo."""
    chico = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(chico, cv2.COLOR_BGR2GRAY).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=180.0)
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument("--out", default="audit/frames_desmontaje_qa")
    ap.add_argument("--diff", type=float, default=2.5,
                    help="diferencia media mínima (0-255) para considerar el frame nuevo")
    args = ap.parse_args()

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    ventana = find_zzz_window()
    if ventana is None:
        print("[grab] no encuentro la ventana de ZZZ — abrí el juego primero")
        return 1
    print(f"[grab] ventana: '{ventana.title}' ({ventana.width}x{ventana.height})")

    det = ScreenDetector(use_state_machine=False)  # crudo: sin filtro de transiciones
    print(f"[grab] {len(det._templates)} templates cargados")
    print(f"[grab] guardando en {destino.resolve()}")
    print(f"[grab] {args.seconds:.0f}s · Ctrl-C para cortar antes\n")

    fin = time.time() + args.seconds
    previa: np.ndarray | None = None
    n = 0
    try:
        while time.time() < fin:
            frame = capture_window(ventana)
            if frame is None:
                time.sleep(args.interval)
                continue
            h = _huella(frame)
            if previa is not None and float(np.abs(h - previa).mean()) < args.diff:
                time.sleep(args.interval)
                continue
            previa = h
            st = det.classify(frame)
            n += 1
            nombre = (f"{n:03d}_{time.strftime('%H%M%S')}_{st.code}"
                      f"_{st.confidence:.2f}_{st.template_name[:34]}.png")
            nombre = "".join(c if c.isalnum() or c in "._-+" else "-" for c in nombre)
            cv2.imwrite(str(destino / nombre), frame)
            print(f"  {n:03d}  {st.code:4s} conf={st.confidence:.3f}  {st.template_name}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[grab] cortado a mano")

    print(f"\n[grab] {n} frames guardados en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

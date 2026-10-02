"""Verdad de tierra de una grabación: qué pasó en pantalla, frame por frame y sin apuro.

Recorre TODOS los frames de una carpeta de `tools/grabar_sesion.py` con el detector y los parsers
de la app (sin cadencia ni votación) y deja `verdad.json` en la carpeta. Es la referencia contra
la que `tools/reproducir_sesion.py` mide cuánto se pierde la app a su ritmo. Read-only.

Uso:
    .venv\Scripts\python tools\verdad_de_sesion.py <carpeta_de_grabacion>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.detector import ScreenDetector  # noqa: E402
from app.core.grabacion import leer_grabacion  # noqa: E402
from app.core.ritmo import eventos_de_verdad, observar_frame  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    args = ap.parse_args()
    rec = leer_grabacion(args.carpeta)
    print(f"[verdad] {len(rec.frames)} frames · {len(rec.clicks)} clicks · descartados {rec.descartados}")
    from app.core.ocr_paddle import PaddleBackend
    ocr = PaddleBackend()
    det = ScreenDetector(use_state_machine=False)
    obs = []
    t0 = time.perf_counter()
    for i, f in enumerate(rec.frames, 1):
        obs.append(observar_frame(f.t, f.cargar(), det, ocr))
        if i % 100 == 0:
            print(f"  {i}/{len(rec.frames)} · {time.perf_counter() - t0:.0f} s")
    v = eventos_de_verdad(obs)
    salida = {
        "frames": [asdict(o) for o in obs],
        "resumen": {k: val for k, val in asdict(v).items() if k != "corridas"},
        "corridas": [asdict(c) for c in v.corridas],
    }
    destino = Path(args.carpeta) / "verdad.json"
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[verdad] {json.dumps(salida['resumen'], ensure_ascii=False)}")
    print(f"[verdad] → {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

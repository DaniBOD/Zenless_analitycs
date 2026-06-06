"""
Diagnóstico OCR en vivo: captura la ventana de ZZZ (mismo pipeline mss que la app)
y corre PaddleOCR sobre el frame, mostrando el texto normalizado completo + el
contexto alrededor de 'energ'/'recup'/'adrenal' y el resultado de _extract_by_regex.

Uso: parado en una pantalla S18 (Atributos base) de un PJ, ejecutar:
    python tools/diag_ocr_live.py

ToS-safe (RNF-03): solo lee píxeles en pantalla, no envía inputs al juego.
"""
import os
import sys
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if os.path.isdir(r"D:\paddle_site"):
    sys.path.insert(0, r"D:\paddle_site")

import cv2
import numpy as np

from app.core.capturer import find_zzz_window, capture_window
from app.core.ocr_paddle import PaddleBackend
from app.core.parser_agent_stats import _normalize_ocr_text, _extract_by_regex


def main() -> int:
    win = find_zzz_window()
    if win is None:
        print("ERROR: ventana ZZZ no encontrada. ¿Está el juego abierto y en foreground?")
        return 1
    print(f"Ventana: '{win.title}' {win.width}x{win.height}")
    frame = capture_window(win)
    if frame is None:
        print("ERROR: capture_window devolvió None.")
        return 1

    out = REPO / "tools" / "diag_live_frame.png"
    cv2.imencode(".png", frame)[1].tofile(str(out))
    print(f"Frame guardado: {out}  ({frame.shape[1]}x{frame.shape[0]})")

    ocr = PaddleBackend(lang="es")
    txt, conf = ocr.text(frame)
    norm = _normalize_ocr_text(txt)
    print(f"\nOCR conf={conf:.3f}  len(norm)={len(norm)}")

    print("\n===== CONTEXTO alrededor de energ/recup/adrenal/perfor =====")
    for kw in ("recup", "energ", "adrenal", "perfor"):
        found = False
        for m in re.finditer(kw, norm):
            found = True
            a = max(0, m.start() - 50)
            b = min(len(norm), m.end() + 25)
            print(f"  [{kw}] ...{norm[a:b]!r}...")
        if not found:
            print(f"  [{kw}] (NO aparece en el OCR)")

    print("\n===== _extract_by_regex =====")
    ex = _extract_by_regex(txt)
    for k in ("prob_crit", "dano_crit", "tasa_perforacion", "recup_energia", "adrenalina"):
        print(f"  {k} = {ex[k]!r}")

    print("\n===== TEXTO NORMALIZADO COMPLETO =====")
    print(norm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

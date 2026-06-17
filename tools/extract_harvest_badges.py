"""Hito E.1 — Extrae crops de badge con ETIQUETA-ORO de los frames harvest.

Los `audit/harvest/{label}__{surface}__{n}.png` son **frames completos 2560×1440**
etiquetados por el latch del flujo-ancla (= dueño CERTERO). Acá se recorta el badge
con la MISMA lógica de la app (`detector.crop_grid_selected_badge` / `crop_detail_badge`)
→ crops reales in-game con etiqueta verdadera (no la lectura del descriptor, que es
lo que tiene `audit/grid_diag`). Es el set GOLD correcto para el spike E.0/E.1.

Salida:
    audit/harvest_badges/{label}__grid__{n}.png   (badge de grilla S17 — target runtime)
    audit/harvest_badges/{label}__det__{n}.png    (badge del panel detalle S18)

Uso:
    .venv_spike\\Scripts\\python.exe tools/extract_harvest_badges.py
"""
from __future__ import annotations

import glob
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.detector import crop_grid_selected_badge, crop_detail_badge  # noqa: E402

_OUT = ROOT / "audit" / "harvest_badges"
_SURFACES = [("S17", "grid", crop_grid_selected_badge),
             ("S18", "det", crop_detail_badge)]


def _imread(p: str) -> np.ndarray | None:
    d = np.fromfile(p, np.uint8)
    return cv2.imdecode(d, cv2.IMREAD_COLOR) if d.size else None


def _imwrite(p: Path, img: np.ndarray) -> bool:
    ok, enc = cv2.imencode(".png", img)
    if ok:
        enc.tofile(str(p))  # tofile → ruta unicode-safe en Windows
    return ok


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    for old in glob.glob(str(_OUT / "*.png")):
        os.remove(old)

    per_label: Counter = Counter()
    for surf, tag, fn in _SURFACES:
        loc = tot = 0
        for p in sorted(glob.glob(str(ROOT / f"audit/harvest/*__{surf}__*.png"))):
            base = os.path.basename(p)
            label = base.split(f"__{surf}__")[0]
            n = os.path.splitext(base)[0].split("__")[-1]
            fr = _imread(p)
            if fr is None:
                continue
            tot += 1
            crop = fn(fr)
            if crop is None or not crop.size:
                continue
            if _imwrite(_OUT / f"{label}__{tag}__{n}.png", crop):
                loc += 1
                per_label[label] += 1
        print(f"{surf}→{tag}: {loc}/{tot} localizados")

    print(f"\nGOLD badges → {_OUT} | {sum(per_label.values())} crops, {len(per_label)} PJs")
    missing = [k for k, v in sorted(per_label.items()) if v < 2]
    if missing:
        print(f"PJs con <2 crops (LOO flojo): {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

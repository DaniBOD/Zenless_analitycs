"""Prep (READ-ONLY sobre fuentes) — recorta los `-ico.webp` del roster a crops
circulares de CABEZA, alineados con el encuadre del badge in-game, para usarlos
como librería de referencia del descriptor de identidad de PJ.

Salida: app/resources/avatar_refs/<Name>.png  (circular, fondo negro, 160px).
Parámetros de recorte (calibrados vs badge real 2026-06-09): centro y=0.40,
radio=0.36·W. Son un KNOB — ajustables en la fase de robustez del descriptor.
"""
from __future__ import annotations
import glob
import os
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Documentacion" / "Interfaz" / "splash_arts"
OUT = ROOT / "app" / "resources" / "avatar_refs"

CY, CX, RAD, SIZE = 0.40, 0.50, 0.36, 160

# Overrides por-PJ (revisión del usuario 2026-06-09). Default = (CY, CX, RAD).
#   cy↑  = baja el recorte (cara que salía "un poco arriba")
#   cx↑  = mueve a la derecha (cara "un poco a la derecha")
#   rad↓ = tensa el círculo (come el "aura" de píxeles borrosos del borde)
OVERRIDES: dict[str, tuple[float, float, float]] = {
    "Alice":           (0.45, 0.50, 0.33),  # arriba + aura
    "Billy-starlight": (0.45, 0.50, 0.36),  # arriba
    "Caesar":          (0.45, 0.50, 0.36),  # arriba
    "cissia":          (0.40, 0.50, 0.33),  # aura
    "Harumasa":        (0.45, 0.50, 0.36),  # arriba
    "Lichter":         (0.45, 0.50, 0.36),  # arriba (user: "lighter")
    "Lucy":            (0.40, 0.55, 0.36),  # derecha
    "Lycaon":          (0.40, 0.55, 0.36),  # derecha
    "Nekomata":        (0.45, 0.50, 0.36),  # arriba
    "Seth":            (0.45, 0.50, 0.36),  # arriba
    "Soldier-11":      (0.45, 0.50, 0.36),  # arriba (user: "N°11")
    "Yanagi":          (0.45, 0.50, 0.36),  # arriba
}


def crop_head(im: np.ndarray, cy: float = CY, cx_n: float = CX, rad: float = RAD) -> np.ndarray:
    H, W = im.shape[:2]
    cx, cyp, r = cx_n * W, cy * H, int(rad * W)
    x0, y0 = int(cx - r), int(cyp - r)
    c = im[max(0, y0):y0 + 2 * r, max(0, x0):x0 + 2 * r].copy()
    s = min(c.shape[:2])
    c = c[:s, :s]
    yy, xx = np.ogrid[:s, :s]
    # Máscara erosionada ~4% del radio: el filo del círculo queda negro, así no
    # entra el "aura" del fondo casi-blanco del -ico (queja del usuario en
    # Alice/Cissia). Beneficia a todos: el descriptor no se contamina con borde.
    erode = max(2.0, 0.04 * s)
    m = ((xx - s / 2) ** 2 + (yy - s / 2) ** 2) <= (s / 2 - erode) ** 2
    c[~m] = 0
    return cv2.resize(c, (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    srcs = sorted(glob.glob(str(SRC / "*-ico.webp"))) + sorted(glob.glob(str(SRC / "*_ico.webp")))
    n = 0
    for p in srcs:
        name = os.path.basename(p).replace("-ico.webp", "").replace("_ico.webp", "")
        im = cv2.imread(p)
        if im is None:
            print(f"  [warn] no leído: {p}")
            continue
        cy, cx_n, rad = OVERRIDES.get(name, (CY, CX, RAD))
        cv2.imwrite(str(OUT / f"{name}.png"), crop_head(im, cy, cx_n, rad))
        n += 1
    print(f"Refs generadas: {n} -> {OUT.relative_to(ROOT)}")
    # montaje de verificación
    files = sorted(glob.glob(str(OUT / "*.png")))
    thumbs = [cv2.resize(cv2.imread(f), (64, 64)) for f in files]
    cols = 11
    rows = (len(thumbs) + cols - 1) // cols
    canvas = np.zeros((rows * 64, cols * 64, 3), np.uint8)
    for i, t in enumerate(thumbs):
        r_, c_ = divmod(i, cols)
        canvas[r_ * 64:(r_ + 1) * 64, c_ * 64:(c_ + 1) * 64] = t
    cv2.imwrite(str(ROOT / "audit" / "qa_shots" / "avatar_refs_montage.png"), canvas)
    print("Montaje: audit/qa_shots/avatar_refs_montage.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

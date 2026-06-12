"""Segmentación de badges de dueño en la grilla de discos (READ-ONLY).

Detecta los círculos de avatar (esquina sup-der de cada tile de disco) con
HoughCircles sobre la región de la grilla, los recorta CON máscara circular
(fondo a negro) y guarda un montaje + cada badge aislado, para alimentar el
descriptor con un recorte limpio (lo que faltaba en descriptor_spike Test 2).
"""
from __future__ import annotations
import os
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "qa_shots"
SHOT = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/04_Inventario_Disco_Vista_Individual/Ejemplo_13_Lucia.png"


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    f = cv2.imread(str(SHOT))
    H, W = f.shape[:2]
    # Región donde viven los badges (mitad-superior de la columna de la grilla).
    x0, x1 = int(0.04 * W), int(0.40 * W)
    y0, y1 = int(0.06 * H), int(0.62 * H)
    roi = f[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    # El badge ~40px diám en full-frame → radio ~18-26 px.
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=40,
        param1=120, param2=34, minRadius=15, maxRadius=30,
    )
    if circles is None:
        print("No se detectaron círculos. Ajustar param2/minRadius.")
        return 1
    circles = np.uint16(np.around(circles[0]))
    print(f"Badges detectados: {len(circles)}")
    badges = []
    for k, (cx, cy, r) in enumerate(sorted(circles, key=lambda c: (c[1] // 40, c[0]))):
        # recorte cuadrado del círculo + máscara
        cx0, cy0 = int(cx) - r, int(cy) - r
        crop = roi[max(0, cy0):cy0 + 2 * r, max(0, cx0):cx0 + 2 * r].copy()
        if crop.shape[0] < 2 * r - 2 or crop.shape[1] < 2 * r - 2:
            continue
        side = min(crop.shape[:2])
        crop = crop[:side, :side]
        yy, xx = np.ogrid[:side, :side]
        m = ((xx - side / 2) ** 2 + (yy - side / 2) ** 2) <= (side / 2 - 1) ** 2
        crop[~m] = 0
        out = OUT / f"hbadge_{k}.png"
        cv2.imwrite(str(out), cv2.resize(crop, (96, 96), interpolation=cv2.INTER_NEAREST))
        # versión nativa para el descriptor
        cv2.imwrite(str(OUT / f"hbadge_{k}_native.png"), crop)
        badges.append(crop)
        print(f"  hbadge_{k}: centro=({cx},{cy}) r={r} -> {side}px")
    # montaje
    if badges:
        thumbs = [cv2.resize(b, (72, 72), interpolation=cv2.INTER_NEAREST) for b in badges]
        cols = min(8, len(thumbs))
        rows = (len(thumbs) + cols - 1) // cols
        canvas = np.zeros((rows * 72, cols * 72, 3), np.uint8)
        for i, t in enumerate(thumbs):
            r_, c_ = divmod(i, cols)
            canvas[r_ * 72:(r_ + 1) * 72, c_ * 72:(c_ + 1) * 72] = t
        cv2.imwrite(str(OUT / "hbadges_montage.png"), canvas)
        print(f"\nMontaje: audit/qa_shots/hbadges_montage.png ({len(thumbs)} badges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Spike de viabilidad (READ-ONLY) — descriptor de identidad de PJ por ícono de avatar.

Objetivo: medir, con NÚMEROS reales, si un descriptor liviano (sin OCR, sin deps
nuevas) separa los 46 PJs a la resolución de los íconos in-game (~40 px), usando
como referencia los `-ico.webp` de Documentacion/Interfaz/splash_arts.

Descriptor (híbrido color, estilo "segmentación de regiones + color-normalizado"):
  - Recorte → círculo inscripto (máscara) → HSV.
  - Normalización de iluminación: se ecualiza el canal V (CLAHE suave) para robustez
    a brillo/sombra del juego.
  - Componente A (PALETA): histograma 2D H×S (16×8) sobre píxeles enmascarados,
    L1-normalizado. Captura la mezcla de colores (pelo + ropa). [robustez global]
  - Componente B (ESTRUCTURA): la cara se parte en 3 bandas (pelo-arriba / ojos-medio
    / boca-abajo); media HSV por banda. Captura el LAYOUT espacial del color
    (p.ej. 'rosa arriba'). [discrimina entre paletas parecidas]
  - Distancia = w_h * Bhattacharyya(histos) + w_r * L1(region_means norm).

Tests:
  1. Auto-separación de las 46 referencias a 40 px (min margen inter-clase).
  2. Match de recortes REALES de badges de la grilla (audit/qa_shots/badge*.png)
     → top-1 + confianza + margen (se evalúa la plausibilidad por color de pelo).

Uso:  .venv\\Scripts\\python.exe tools\\descriptor_spike.py
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ICO_DIR = ROOT / "Documentacion" / "Interfaz" / "splash_arts"

S = 48          # tamaño de trabajo (px). Las referencias se bajan a ESTE tamaño para
                # comparar a igualdad de información con un badge ~40 px.
H_BINS, S_BINS = 16, 8
W_HIST, W_REG = 0.65, 0.35


def _circle_mask(side: int) -> np.ndarray:
    yy, xx = np.ogrid[:side, :side]
    return ((xx - side / 2) ** 2 + (yy - side / 2) ** 2) <= (side / 2 - 1) ** 2


_MASK = _circle_mask(S)


def descriptor(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (histograma H×S normalizado, vector de medias por región)."""
    img = cv2.resize(bgr, (S, S), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Normalización de iluminación: CLAHE sobre V.
    v = hsv[:, :, 2]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    hsv[:, :, 2] = clahe.apply(v)
    mask = _MASK
    # --- Componente A: histograma H×S sobre el círculo ---
    hist = cv2.calcHist([hsv], [0, 1], mask.astype(np.uint8), [H_BINS, S_BINS], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist, norm_type=cv2.NORM_L1).flatten().astype(np.float32)
    # --- Componente B: medias HSV por 3 bandas horizontales (enmascaradas) ---
    regions = []
    for y0, y1 in [(0, S // 3), (S // 3, 2 * S // 3), (2 * S // 3, S)]:
        band = hsv[y0:y1]
        bmask = mask[y0:y1]
        if bmask.sum() == 0:
            regions.extend([0, 0, 0])
            continue
        px = band[bmask]
        # H en seno/coseno para que sea circular; S y V normalizados 0-1
        hrad = px[:, 0].astype(np.float32) * (np.pi / 90.0)
        regions.extend([
            float(np.cos(hrad).mean()), float(np.sin(hrad).mean()),
            float(px[:, 1].mean() / 255.0),
        ])
    return hist, np.asarray(regions, dtype=np.float32)


def distance(a, b) -> float:
    ha, ra = a
    hb, rb = b
    dh = cv2.compareHist(ha, hb, cv2.HISTCMP_BHATTACHARYYA)  # 0=igual, 1=distinto
    dr = float(np.abs(ra - rb).mean())                       # ~0..1
    return W_HIST * dh + W_REG * dr


def load_refs() -> dict[str, tuple]:
    refs = {}
    for p in sorted(glob.glob(str(ICO_DIR / "*-ico.webp"))) + sorted(glob.glob(str(ICO_DIR / "*_ico.webp"))):
        name = os.path.basename(p).replace("-ico.webp", "").replace("_ico.webp", "")
        img = cv2.imread(p)
        if img is None:
            print(f"  [warn] no se pudo leer {p}")
            continue
        refs[name] = descriptor(img)
    return refs


def main() -> int:
    refs = load_refs()
    names = list(refs.keys())
    print(f"Referencias cargadas: {len(names)} íconos -ico (a {S}px)\n")

    # --- Test 1: auto-separación entre las 46 referencias ---
    n = len(names)
    D = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(n):
            D[i, j] = distance(refs[names[i]], refs[names[j]]) if i != j else 9.9
    nearest = D.min(axis=1)
    worst_i = int(np.argmin(nearest))
    print("== Test 1: separación de las 46 referencias (a 40-48px) ==")
    print(f"  distancia al vecino más cercano: min={nearest.min():.3f} "
          f"media={nearest.mean():.3f} max={nearest.max():.3f}")
    j = int(np.argmin(D[worst_i]))
    print(f"  par MÁS confundible: {names[worst_i]} ~ {names[j]} (d={D[worst_i, j]:.3f})")
    # top-3 pares más cercanos
    pairs = sorted(((D[i, k], names[i], names[k]) for i in range(n) for k in range(i + 1, n)))[:5]
    print("  5 pares más cercanos:")
    for d, a, b in pairs:
        print(f"    {d:.3f}  {a} ~ {b}")

    # --- Test 2: match de badges reales de la grilla ---
    print("\n== Test 2: match de badges reales (audit/qa_shots/badge*.png) ==")
    for bp in sorted(glob.glob(str(ROOT / "audit" / "qa_shots" / "badge*.png"))):
        img = cv2.imread(bp)
        if img is None:
            continue
        # el badge crop tiene fondo; recortar el círculo central (badge ocupa ~centro-der)
        q = descriptor(img)
        scored = sorted(((distance(q, refs[nm]), nm) for nm in names))
        d1, n1 = scored[0]
        d2, n2 = scored[1]
        conf = max(0.0, 1.0 - d1)
        margin = d2 - d1
        print(f"  {os.path.basename(bp):<12} top1={n1:<14} conf={conf:.3f} "
              f"margen={margin:.3f}  (2º={n2}, d2={d2:.3f})")
    print("\nNota: los badge*.png son recortes aproximados (sin centrar fino). El número")
    print("a mirar es el MARGEN top1-vs-top2: si es amplio, el descriptor separa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fase 5R.3 — Extrae crops etiquetados de los frames cosechados (READ-ONLY).

Entrada: carpeta con `<normkey>__<estado>__<n>.png` (frames completos que guardó el
hook `monitor._maybe_harvest`, etiquetados por el latch).
Salida: `<out>/<NombrePJ>/<estado>_<src>_<n>.png` — crops circulares de cabeza, mismo
encuadre que los `-ico`, listos para `validate_descriptor.py --labeled <out>`.

Dos extractores:
  - S8/S18/S19 → avatar de fila (`crop_selected_avatar`), recortado a la cabeza.
  - S17 → badge del tile seleccionado de la grilla (highlight + Hough acotado).

Uso:  .venv\\Scripts\\python.exe tools\\extract_harvested.py --in <harvestdir> [--out audit/labeled_badges]
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.detector import _AVATAR_HL_LOWER, _AVATAR_HL_UPPER, crop_selected_avatar  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402


def _imread_u(p: str):
    """imread unicode-safe (paths con 'º' etc. que cv2.imread no abre en Windows)."""
    try:
        return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _circle_crop(bgr: np.ndarray) -> np.ndarray:
    s = min(bgr.shape[:2])
    c = bgr[:s, :s].copy()
    yy, xx = np.ogrid[:s, :s]
    m = ((xx - s / 2) ** 2 + (yy - s / 2) ** 2) <= (s / 2 - max(2, 0.04 * s)) ** 2
    c[~m] = 0
    return c


def _selected_tile_bbox(frame: np.ndarray):
    """Bbox (en frame) del tile resaltado de la grilla izquierda, o None."""
    H, W = frame.shape[:2]
    gx0, gy0 = int(0.01 * W), int(0.10 * H)
    sub = frame[gy0:int(0.95 * H), gx0:int(0.235 * W)]
    if sub.size == 0:
        return None
    mask = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), _AVATAR_HL_LOWER, _AVATAR_HL_UPPER)
    n, _, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, area = st[i]
    if area < 1500:
        return None
    return gx0 + bx, gy0 + by, bw, bh


# Offset FIJO del badge de dueño respecto al bbox del tile seleccionado
# (calibrado sobre frames reales 2026-06-10, Corin S17): el badge cuelga de la
# esquina sup-der. centro=(tx+0.86·tw, ty+0.13·th), radio≈0.18·tw.
_BADGE_CX_F, _BADGE_CY_F, _BADGE_R_F = 0.86, 0.13, 0.18


def crop_grid_selected_badge(frame: np.ndarray):
    """Badge (cabeza circular) del tile seleccionado de la grilla S17: highlight
    para localizar el tile + offset FIJO a su esquina sup-der (robusto, sin Hough)."""
    bb = _selected_tile_bbox(frame)
    if bb is None:
        return None
    tx, ty, tw, th = bb
    cx = int(tx + _BADGE_CX_F * tw)
    cy = int(ty + _BADGE_CY_F * th)
    r = int(_BADGE_R_F * tw)
    if r < 8:
        return None
    H, W = frame.shape[:2]
    crop = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    return _circle_crop(crop) if crop.size else None


def crop_row_head(frame: np.ndarray):
    """Avatar de fila (S8/S18/S19) recortado a la cabeza circular."""
    face = crop_selected_avatar(frame)
    if face is None:
        return None
    h, w = face.shape[:2]
    # el tile es cabeza+hombros; la cabeza está arriba-centro → recorte superior.
    s = int(0.72 * min(h, w))
    x0 = (w - s) // 2
    head = face[0:s, x0:x0 + s]
    return _circle_crop(head) if head.size else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", default="audit/labeled_badges")
    args = ap.parse_args()

    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    rk = {_norm_key(n): n for n in roster}

    out = ROOT / args.out
    counts: dict[str, int] = {}
    montage_tiles = []
    for p in sorted(glob.glob(os.path.join(args.indir, "*.png"))):
        base = os.path.basename(p)
        parts = base.split("__")
        if len(parts) < 3:
            continue
        normkey, state, _ = parts[0], parts[1], parts[2]
        label = rk.get(normkey, normkey)
        frame = _imread_u(p)
        if frame is None:
            continue
        crop = crop_grid_selected_badge(frame) if state == "S17" else crop_row_head(frame)
        if crop is None or crop.size == 0:
            continue
        d = out / label
        d.mkdir(parents=True, exist_ok=True)
        k = counts.get(label + state, 0); counts[label + state] = k + 1
        cv2.imwrite(str(d / f"{state}_{k}.png"), crop)
        if len(montage_tiles) < 80:
            t = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_NEAREST)
            cv2.putText(t, label[:7], (2, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1, cv2.LINE_AA)
            montage_tiles.append(t)
    total = sum(counts.values())
    print(f"Crops extraídos: {total} en {len(set(k[:-3] for k in counts))} PJs -> {out}")
    if montage_tiles:
        cols = 10; rows = (len(montage_tiles) + cols - 1) // cols
        cv = np.zeros((rows * 64, cols * 64, 3), np.uint8)
        for i, t in enumerate(montage_tiles):
            r_, c_ = divmod(i, cols); cv[r_ * 64:(r_ + 1) * 64, c_ * 64:(c_ + 1) * 64] = t
        cv2.imwrite(str(ROOT / "audit" / "qa_shots" / "harvested_montage.png"), cv)
        print("Montaje: audit/qa_shots/harvested_montage.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

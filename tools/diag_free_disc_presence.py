"""diag_free_disc_presence.py — Caracteriza la PRESENCIA de badge de dueño en la
esquina del tile seleccionado (grid) vs el panel de detalle, para discos EQUIPADOS
vs LIBRES (Fase 5R · L.7.1).

Objetivo: encontrar una métrica (HSV) que separe "hay avatar de dueño" (equipado)
de "esquina sin avatar / arte de disco / candado" (libre), para gate-ear el crop del
grid (L.7.2) y dejar de votar fantasmas (el falso 'Cissia' en discos libres).

Read-only puro. No toca DB ni librerías. Vuelca los crops de esquina a un dir para
inspección visual (clasificar libre/equipado a ojo cuando no hay label).

Uso:
    python tools/diag_free_disc_presence.py
        --equipped audit/harvest         (default; frames *__S17__*.png = equipados/GT)
        --free <dir>                     (opcional; frames de discos LIBRES)
        --extra <dir>                    (opcional; mezcla sin label, p.ej. carpeta 04)
        --dump audit/free_disc_presence_crops
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import cv2
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.detector import (  # noqa: E402
    _selected_grid_tile_bbox,
    _BADGE_CX_F, _BADGE_CY_F, _BADGE_R_F,
    crop_grid_selected_badge,
    crop_detail_badge,
)


def _corner_crop(frame: np.ndarray):
    """Recorte de la esquina del tile donde CUELGA el badge del dueño (mismo offset
    fijo que crop_grid_selected_badge). Devuelve (crop|None, bbox|None)."""
    bb = _selected_grid_tile_bbox(frame)
    if bb is None:
        return None, None
    tx, ty, tw, th = bb
    cx, cy, r = int(tx + _BADGE_CX_F * tw), int(ty + _BADGE_CY_F * th), int(_BADGE_R_F * tw)
    if r < 8:
        return None, bb
    H, W = frame.shape[:2]
    crop = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    return (crop if crop.size else None), bb


def _presence_metrics(crop: np.ndarray) -> dict:
    """Métricas candidatas de presencia de avatar sobre el crop de esquina del grid.
    Un avatar real = retrato colorido con anillo → alta saturación + blob grande.
    Esquina vacía / candado / arte oscuro → poca saturación / blob chico."""
    if crop is None or crop.size == 0:
        return {"sat_mean": 0.0, "sat_blob_area": 0, "sat_blob_frac": 0.0,
                "hough_circle": 0, "area_px": 0}
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    sat_mean = float(sat.mean())
    # blob saturado (mismo criterio que el gate del detail: sat > 50)
    mask = (sat > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
    blob_area = int(stats[1:, 4].max()) if n > 1 else 0
    total = crop.shape[0] * crop.shape[1]
    # ¿hay un círculo (anillo del avatar) del tamaño esperado?
    gray = cv2.medianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 3)
    h = crop.shape[0]
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=h,
                               param1=120, param2=18,
                               minRadius=int(0.30 * h), maxRadius=int(0.60 * h))
    return {
        "sat_mean": round(sat_mean, 1),
        "sat_blob_area": blob_area,
        "sat_blob_frac": round(blob_area / float(total), 3),
        "hough_circle": 0 if circles is None else len(circles[0]),
        "area_px": total,
    }


def _scan(label: str, frames: list[str], dump_dir: Path) -> list[dict]:
    rows = []
    for fp in frames:
        frame = cv2.imread(fp)
        if frame is None:
            continue
        name = Path(fp).stem
        crop, bb = _corner_crop(frame)
        gbadge = crop_grid_selected_badge(frame)
        det = crop_detail_badge(frame)
        m = _presence_metrics(crop)
        row = {"label": label, "frame": name, "tile_found": bb is not None,
               "grid_badge_notnone": gbadge is not None, "detail_notnone": det is not None,
               **m}
        rows.append(row)
        if crop is not None and crop.size:
            tag = f"{label}__{name}__sat{m['sat_mean']:.0f}_blob{m['sat_blob_area']}_circ{m['hough_circle']}"
            cv2.imwrite(str(dump_dir / f"{tag}.png"), crop)
    return rows


def _summary(rows: list[dict], label: str) -> str:
    sub = [r for r in rows if r["label"] == label]
    if not sub:
        return f"  ({label}: sin frames)\n"
    def col(k):
        return [r[k] for r in sub if r["tile_found"]]
    sat = col("sat_mean"); blob = col("sat_blob_area"); circ = col("hough_circle")
    det = [r["detail_notnone"] for r in sub]
    out = [f"  {label}: {len(sub)} frames ({sum(r['tile_found'] for r in sub)} con tile)"]
    if sat:
        out.append(f"    sat_mean   min/med/max = {min(sat):.0f} / {np.median(sat):.0f} / {max(sat):.0f}")
        out.append(f"    blob_area  min/med/max = {min(blob)} / {int(np.median(blob))} / {max(blob)}")
        out.append(f"    hough_circ >=1 en {sum(c >= 1 for c in circ)}/{len(circ)}")
    out.append(f"    detail_notnone = {sum(det)}/{len(sub)}")
    return "\n".join(out) + "\n"


def _scan_crops(crop_dir: str) -> list[dict]:
    """Modo CROPS: procesa PNGs que YA son recortes de esquina de badge (p.ej. el
    dump de audit/grid_diag, con el veredicto en el nombre: badge_<PJ>_<conf> = avatar
    matcheado [equipado]; badge_none / NOLOC = abstención [candidato a LIBRE]). Mide la
    presencia sobre cada uno y agrupa por clase para ver si la métrica los separa."""
    rows = []
    for fp in sorted(glob.glob(str(Path(crop_dir) / "*.png"))):
        stem = Path(fp).stem
        if "NOLOC" in stem:
            cls = "noloc"
        elif "_none_" in stem or stem.endswith("_none") or "REJECT" in stem:
            cls = "none"
        elif "_badge_" in stem:
            cls = "matched"
        else:
            cls = "other"
        crop = cv2.imread(fp)
        if crop is None:
            continue
        m = _presence_metrics(crop)
        rows.append({"label": cls, "frame": stem, "tile_found": True,
                     "grid_badge_notnone": True, "detail_notnone": False, **m})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equipped", default="audit/harvest")
    ap.add_argument("--free", default=None)
    ap.add_argument("--extra", default=None)
    ap.add_argument("--crops", default=None, help="dir de crops de esquina ya recortados (grid_diag)")
    ap.add_argument("--dump", default="audit/free_disc_presence_crops")
    args = ap.parse_args()

    if args.crops:
        rows = _scan_crops(args.crops)
        print(f"[crops] {len(rows)} crops de {args.crops}")
        print("\n=== RESUMEN (crops pre-recortados) ===")
        for lab in ("matched", "none", "noloc", "other"):
            print(_summary(rows, lab), end="")
        return

    dump_dir = Path(args.dump); dump_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    eq = sorted(glob.glob(str(Path(args.equipped) / "*__S17__*.png")))
    if not eq:  # fallback: cualquier png del dir
        eq = sorted(glob.glob(str(Path(args.equipped) / "*.png")))
    print(f"[equipped] {len(eq)} frames de {args.equipped}")
    rows += _scan("equipped", eq, dump_dir)

    if args.free:
        fr = sorted(glob.glob(str(Path(args.free) / "*.png")))
        print(f"[free] {len(fr)} frames de {args.free}")
        rows += _scan("free", fr, dump_dir)

    if args.extra:
        ex = sorted(glob.glob(str(Path(args.extra) / "*.png")))
        print(f"[extra] {len(ex)} frames de {args.extra}")
        rows += _scan("extra", ex, dump_dir)

    print("\n=== RESUMEN ===")
    for lab in ("equipped", "free", "extra"):
        print(_summary(rows, lab), end="")

    # markdown
    out_md = Path("audit") / "free_disc_presence_diag.md"
    lines = ["# Diagnóstico presencia de badge — libres vs equipados (L.7.1)\n",
             f"Frames: equipped={sum(r['label']=='equipped' for r in rows)} "
             f"free={sum(r['label']=='free' for r in rows)} "
             f"extra={sum(r['label']=='extra' for r in rows)}\n",
             "\n## Resumen por clase\n```"]
    for lab in ("equipped", "free", "extra"):
        lines.append(_summary(rows, lab).rstrip())
    lines.append("```\n\n## Detalle por frame\n")
    lines.append("| clase | frame | tile | grid≠None | det≠None | sat_mean | blob_area | blob_frac | hough |")
    lines.append("|---|---|:-:|:-:|:-:|--:|--:|--:|:-:|")
    for r in rows:
        lines.append(f"| {r['label']} | {r['frame']} | {'✓' if r['tile_found'] else '·'} | "
                     f"{'✓' if r['grid_badge_notnone'] else '·'} | {'✓' if r['detail_notnone'] else '·'} | "
                     f"{r['sat_mean']} | {r['sat_blob_area']} | {r['sat_blob_frac']} | {r['hough_circle']} |")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[ok] crops → {dump_dir}\n[ok] reporte → {out_md}")


if __name__ == "__main__":
    main()

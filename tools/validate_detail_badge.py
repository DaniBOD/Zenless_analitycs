"""Fase 5R.C.4 — Valida el DETALLE-badge (avatar al lado de 'Nivel 15/15' del panel
de detalle S17) como fuente alternativa/primaria de dueño.

El detalle-badge tiene localización trivial y robusta (posición fija-en-X, fondo
oscuro, sin confound de arte ni NOLOC de transición — 100% loc vs 73% del grid),
PERO encuadre distinto al grid-badge → necesita su PROPIA librería.

Este harness lo valida OFFLINE desde un video de barrida (sin tocar la app):
  1. Por frame: matchea el GRID-badge (librería actual). Si conf>=GATE → owner certero
     (los reads del grid son 0-wrong, verificado) → etiqueta el DETALLE-crop de ese
     frame con ese owner.
  2. Construye una librería de DETALLE etiquetada, leave-one-out → discriminación.
  3. Montaje por owner para inspección visual.

Uso:
    python tools/validate_detail_badge.py <video.mp4> [--gate 0.85] [--step 15]
"""
from __future__ import annotations
import argparse
import glob
import os
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import (  # noqa: E402
    AvatarMatcher, AvatarDescriptor, build_descriptor, build_name_map,
)
from app.core.detector import crop_grid_selected_badge  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402
from app.db.connection import get_connection  # noqa: E402

_SNAP = ROOT / "audit" / "avatar_badge_v2_snapshot_20260612_full47.npz"


def crop_detail_badge(img):
    """Localiza el detalle-badge (blob saturado a la derecha del header 'Nivel 15/15').
    Robusto al corrimiento en Y (nombre 1 vs 2 líneas). Devuelve crop BGR o None."""
    H, W = img.shape[:2]
    rx0, rx1, ry0, ry1 = 0.475, 0.515, 0.12, 0.26
    sub = img[int(ry0 * H):int(ry1 * H), int(rx0 * W):int(rx1 * W)]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1 or stats[1:, 4].max() < 200:
        return None
    i = 1 + int(np.argmax(stats[1:, 4]))
    ccx, ccy = cent[i]
    cx, cy, r = int(rx0 * W + ccx), int(ry0 * H + ccy), int(0.019 * W)
    crop = img[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
    return crop if crop.size else None


def _grid_matcher():
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                   ROOT / "app/resources/avatar_reject", name_map=build_name_map(stems, roster))
    d = np.load(str(_SNAP), allow_pickle=True)
    for i, nm in enumerate([str(x) for x in d["names"]]):
        m.add_reference(nm, AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                             d["gray"][i], bool(d["is_gray"][i])), max_per_name=20)
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--gate", type=float, default=0.85, help="conf mínima del grid para etiquetar")
    ap.add_argument("--step", type=int, default=600, help="cada cuántos frames seek-muestrear (~10s a 60fps)")
    ap.add_argument("--cap", type=int, default=20, help="máx detalle-crops por owner")
    ap.add_argument("--trim0", type=float, default=0.02, help="fracción inicial a saltar")
    ap.add_argument("--trim1", type=float, default=0.99, help="fracción final a procesar hasta")
    args = ap.parse_args()

    gm = _grid_matcher()
    v = cv2.VideoCapture(args.video)
    n = int(v.get(cv2.CAP_PROP_FRAME_COUNT))
    by_owner: dict[str, list] = defaultdict(list)   # owner -> [(desc, crop)]
    # SEEK-based (robusto en archivos grandes; el grab secuencial crashea cv2/ffmpeg
    # en el .mp4 de 5GB). Muestreo grueso + progreso flusheado para no morir en silencio.
    seen = labeled = 0
    fr, end = int(n * args.trim0), int(n * args.trim1)
    print(f"procesando {args.video} | frames {n} | step {args.step} (~{args.step/60:.0f}s)", flush=True)
    while fr < end:
        v.set(cv2.CAP_PROP_POS_FRAMES, fr); ok, img = v.read(); fr += args.step
        if not ok:
            continue
        seen += 1
        if seen % 50 == 0:
            print(f"  ...{seen} muestras | {labeled} etiquetadas | {len(by_owner)} owners", flush=True)
        g = crop_grid_selected_badge(img)
        if g is None:
            continue
        rg = gm.match(g)
        if rg.name is None or rg.conf < args.gate:
            continue
        det = crop_detail_badge(img)
        if det is None:
            continue
        desc = build_descriptor(det)
        if desc is None:
            continue
        if len(by_owner[rg.name]) < args.cap:
            by_owner[rg.name].append((desc, det)); labeled += 1
    v.release()
    print(f"frames muestreados: {seen} | detalle-crops etiquetados: {labeled}", flush=True)

    by_owner = {k: val for k, val in by_owner.items() if len(val) >= 2}
    ntot = sum(len(v) for v in by_owner.values())
    print(f"Owners etiquetados (grid conf>={args.gate}): {len(by_owner)} | detalle-crops: {ntot}\n")

    # leave-one-out sobre la librería de DETALLE (sin semilla -ico)
    dm = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                    ROOT / "app/resources/avatar_reject")
    dm._refs.clear()   # librería de detalle pura
    for owner, items in by_owner.items():
        for desc, _crop in items:
            dm.add_reference(owner, desc, max_per_name=99)

    ok = ab = wr = 0
    conf = defaultdict(int)
    diag = ROOT / "audit" / "grid_diag"
    for owner, items in by_owner.items():
        lst = dm._refs.get(owner, [])
        # montaje por owner
        row = [cv2.resize(c, (72, 72)) for _d, c in items]
        if row:
            cv2.imencode(".png", np.hstack(row))[1].tofile(str(diag / f"_det_{_norm_key(owner)[:10]}.png"))
        for desc, _c in items:
            idx = next((j for j, x in enumerate(lst) if x is desc), None)
            held = lst.pop(idx) if idx is not None else None
            r = dm.match(desc)
            if held is not None:
                lst.insert(idx, held)
            if r.name is None:
                ab += 1
            elif _norm_key(r.name) == _norm_key(owner):
                ok += 1
            else:
                wr += 1; conf[(owner, r.name)] += 1
    t = max(1, ok + ab + wr)
    print(f"DISCRIMINACIÓN detalle-badge (leave-one-out):")
    print(f"  TOP-1: {ok}/{t} = {ok/t:.0%}  |  ABST: {ab}/{t} = {ab/t:.0%}  |  WRONG: {wr}/{t} = {wr/t:.0%}")
    if conf:
        print("  Wrongs:", "  ".join(f"{a}->{b} x{c}" for (a, b), c in sorted(conf.items(), key=lambda kv: -kv[1])))
    print(f"\n  Owners: {', '.join(f'{k}({len(v)})' for k, v in sorted(by_owner.items()))}")
    print(f"  Montajes por owner -> audit/grid_diag/_det_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

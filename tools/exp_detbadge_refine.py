"""Hito L.2b (Fase 5R) — Experimento offline del REFINE del crop del detalle-badge.

L.1 probó que el imán es del ENCUADRE: el crop fijo (96px) ahoga al avatar (~55px) en
fondo a rayas compartido por página → el descriptor se agrupa por fondo. Acá se prueban
variantes de crop que **ajustan a la cara excluyendo el fondo**, midiendo apples-to-apples
(refs y query con el MISMO encuadre):

  - refs    = det de audit/harvest/*__S17__* (GT = label del latch).
  - query   = det de 16_discos_pj_grilla (GT = grid-matcher, page != owner = CROSS-DOMAIN).

El número que importa es el CROSS-DOMAIN (query examples): ahí page != owner, así que el
fondo NO ayuda — mide discriminación real de cara. (LOO dentro de harvest es optimista
porque mismo PJ = misma página = mismo fondo.)

Uso:
    .venv/Scripts/python.exe tools/exp_detbadge_refine.py [--dump]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import (  # noqa: E402
    AvatarMatcher, AvatarDescriptor, build_descriptor, build_name_map,
)
from app.core.detector import crop_grid_selected_badge, _DET_REGION, _DET_SAT_MIN  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402

_HARVEST = ROOT / "audit" / "harvest"
_EXAMPLES = ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "16_discos_pj_grilla"
_GRID_SNAP = ROOT / "audit" / "avatar_badge_v2_snapshot_20260612_full47.npz"
_REFS = ROOT / "app" / "resources" / "avatar_refs"
_REJECT = ROOT / "app" / "resources" / "avatar_reject"
_GUARD = 0.80


def _imread(p: str) -> np.ndarray | None:
    d = np.fromfile(p, np.uint8)
    return cv2.imdecode(d, cv2.IMREAD_COLOR) if d.size else None


# --------------------------------------------------------------------------- #
# Variantes de crop del detalle-badge
# --------------------------------------------------------------------------- #

def _det_centroid_blob(frame):
    """Sub-región + máscara saturada + centroide del blob mayor (lógica actual).
    Devuelve (sub_bgr, cx, cy, W) en coords del frame, o None."""
    H, W = frame.shape[:2]
    x0, x1, y0, y1 = _DET_REGION
    sub = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
    if sub.size == 0:
        return None
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > _DET_SAT_MIN).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _l, st, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1 or st[1:, 4].max() < 200:
        return None
    i = 1 + int(np.argmax(st[1:, 4]))
    ccx, ccy = cent[i]
    return sub, int(x0 * W + ccx), int(y0 * H + ccy), W, mask, i, st


def _crop_fixed(frame, r_frac):
    """Radio fijo (r_frac·W) centrado en el centroide del blob saturado."""
    res = _det_centroid_blob(frame)
    if res is None:
        return None
    _sub, cx, cy, W, _m, _i, _st = res
    r = int(r_frac * W)
    if r < 8:
        return None
    H = frame.shape[0]
    c = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(frame.shape[1], cx + r)]
    return c if c.size else None


def _crop_open(frame, pad=1.05):
    """Apertura morfológica para matar las colas finas del fondo a rayas; el blob
    compacto restante = la cara. Radio = 0.5·max(bbox del blob abierto)·pad."""
    H, W = frame.shape[:2]
    x0, x1, y0, y1 = _DET_REGION
    sub = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
    if sub.size == 0:
        return None
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > _DET_SAT_MIN).astype(np.uint8) * 255
    k = max(3, int(0.012 * W) | 1)   # ~7px @2560
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, _l, st, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1 or st[1:, 4].max() < 200:
        return None
    i = 1 + int(np.argmax(st[1:, 4]))
    bx, by, bw, bh, _a = st[i]
    ccx, ccy = cent[i]
    r = int(0.5 * max(bw, bh) * pad)
    cx, cy = int(x0 * W + ccx), int(y0 * H + ccy)
    if r < 8:
        return None
    c = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    return c if c.size else None


def _crop_hough(frame):
    """Hough sobre la sub-región para hallar el círculo del avatar (~28px de radio)."""
    H, W = frame.shape[:2]
    x0, x1, y0, y1 = _DET_REGION
    sub = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
    if sub.size == 0:
        return None
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    rmin, rmax = int(0.008 * W), int(0.015 * W)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(0.05 * W),
                               param1=120, param2=22, minRadius=rmin, maxRadius=rmax)
    if circles is None:
        return None
    c0 = circles[0][0]
    cx, cy, r = int(x0 * W + c0[0]), int(y0 * H + c0[1]), int(c0[2] * 1.05)
    if r < 8:
        return None
    c = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    return c if c.size else None


# orden: (nombre, fn)
def _variants():
    return [
        ("OLD fix .019", lambda f: _crop_fixed(f, 0.019)),
        ("fix .013", lambda f: _crop_fixed(f, 0.013)),
        ("fix .011", lambda f: _crop_fixed(f, 0.011)),
        ("open blob", _crop_open),
        ("hough", _crop_hough),
    ]


# --------------------------------------------------------------------------- #

def _grid_matcher(nm):
    gm = AvatarMatcher.from_folders(_REFS, _REJECT, name_map=nm)
    d = np.load(str(_GRID_SNAP), allow_pickle=True)
    for i, n in enumerate([str(x) for x in d["names"]]):
        gm.add_reference(n, AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                             d["gray"][i], bool(d["is_gray"][i])), max_per_name=20)
    return gm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="vuelca montajes de cada variante")
    args = ap.parse_args()

    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(_REFS / "*.png"))]
    nm = build_name_map(stems, roster)
    rejects = AvatarMatcher.from_folders(_REFS, _REJECT)._rejects

    harvest_frames = sorted(glob.glob(str(_HARVEST / "*__S17__*.png")))
    example_frames = sorted(glob.glob(str(_EXAMPLES / "*.png")))

    # GT de los ejemplos (grid-matcher) — cachear el grid crop una vez.
    gm = _grid_matcher(nm)
    example_gt = {}
    for p in example_frames:
        fr = _imread(p)
        if fr is None:
            continue
        g = crop_grid_selected_badge(fr)
        if g is None:
            continue
        rg = gm.match(g)
        if rg.name is not None and rg.conf >= 0.85:
            example_gt[p] = rg.name
    print(f"ejemplos con GT de grid (conf>=0.85): {len(example_gt)}/{len(example_frames)}\n")

    dump_dir = ROOT / "audit" / "detbadge_magnet_diag"
    print(f"{'variante':14} | refs(loc) | LOO harvest | CROSS-DOMAIN ejemplos (lo que importa)")
    print("-" * 92)
    results = {}
    for vname, fn in _variants():
        # refs desde harvest
        m = AvatarMatcher(rejects=list(rejects))
        loc = 0
        harv_descs = []   # (label, desc)
        for p in harvest_frames:
            fr = _imread(p)
            if fr is None:
                continue
            c = fn(fr)
            if c is None:
                continue
            label = os.path.basename(p).split("__S17__")[0]
            canon = nm.get(label) or nm.get(label.replace(".", "")) or label
            d = build_descriptor(c)
            if d is None:
                continue
            m.add_reference(canon, d, max_per_name=99)
            harv_descs.append((canon, d))
            loc += 1

        # LOO harvest (optimista)
        ok = wr = ab = 0
        for canon, d in harv_descs:
            lst = m._refs.get(canon, [])
            idx = next((j for j, x in enumerate(lst) if x is d), None)
            held = lst.pop(idx) if idx is not None else None
            r = m.match(d)
            if held is not None:
                lst.insert(idx, held)
            if r.name is None or r.conf < _GUARD:
                ab += 1
            elif _norm_key(r.name) == _norm_key(canon):
                ok += 1
            else:
                wr += 1
        loo = f"top1 {ok/max(1,ok+wr+ab):.0%} wr {wr}"

        # CROSS-DOMAIN ejemplos
        eok = ewr = eab = 0
        epreds = Counter()
        crops_dump = []
        for p, gt in example_gt.items():
            fr = _imread(p)
            c = fn(fr) if fr is not None else None
            if c is None:
                eab += 1
                continue
            r = m.match(c)
            if r.name:
                epreds[r.name] += 1
            if args.dump:
                crops_dump.append(cv2.resize(c, (64, 64)))
            if r.name is None or r.conf < _GUARD:
                eab += 1
            elif _norm_key(r.name) == _norm_key(gt):
                eok += 1
            else:
                ewr += 1
        et = max(1, eok + ewr + eab)
        cross = (f"top1 {eok}/{et}={eok/et:.0%} · WRONG {ewr} · abst {eab} · "
                 f"distintos {len(epreds)}")
        results[vname] = (eok, ewr, eab, len(epreds))
        print(f"{vname:14} | {loc:3d}/180  | {loo:14} | {cross}")
        if args.dump and crops_dump:
            cv2.imencode(".png", np.hstack(crops_dump))[1].tofile(
                str(dump_dir / f"REFINE_{vname.replace(' ', '_').replace('.', '')}.png"))

    print("\n(LOO harvest es OPTIMISTA: mismo PJ=misma página=mismo fondo. El número real es CROSS-DOMAIN.)")
    best = max(results.items(), key=lambda kv: (kv[1][3], kv[1][0], -kv[1][1]))
    print(f"Mejor por (distintos, top1, -wrong): {best[0]} → {best[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

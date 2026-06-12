"""Fase 5R.C — Harness de validación/tuning del descriptor de badge a escala.

Leave-one-out multi-ref sobre los badges cosechados (`audit/labeled_badges/<PJ>/S17_*`),
con **barrido de pesos** del descriptor (w_hist, w_ncc, w_reg) y **matriz de confusión**
por PJ. Es el número GO/NO-GO que guía C.3 (tuning): qué pesos maximizan top-1 sin meter
wrongs, y qué pares de PJs se confunden (look-alikes).

Reusa el patrón de `validate_hybrid.py`. La librería = -ico (semilla) + reject + todas las
refs cosechadas. NO toca DB. Tras el pase full-roster, correr `extract_harvested.py` primero
para refrescar `labeled_badges` con la cosecha nueva.

Uso:
    python tools/validate_grid_scale.py                 # barrido de pesos + confusión
    python tools/validate_grid_scale.py --weights 0.4 0.45 0.15   # un punto fijo
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
    AvatarMatcher, build_descriptor, build_name_map, _W_HIST, _W_NCC, _W_REG,
)
from app.core.stats_vocab import _norm_key  # noqa: E402


def _imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def _load(seed_ico=True):
    labeled = ROOT / "audit" / "labeled_badges"
    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    nm = build_name_map(stems, roster)
    by_pj: dict[str, list] = defaultdict(list)
    for pjdir in sorted(glob.glob(str(labeled / "*"))):
        label = os.path.basename(pjdir)
        for p in sorted(glob.glob(pjdir + "/S17_*.png")):
            d = build_descriptor(_imread_u(p))
            if d is not None:
                by_pj[label].append(d)
    by_pj = {k: v for k, v in by_pj.items() if len(v) >= 2}
    m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                   ROOT / "app/resources/avatar_reject", name_map=nm)
    for pj, descs in by_pj.items():
        for d in descs:
            m.add_reference(pj, d, max_per_name=12)
    return m, by_pj


def evaluate(m, by_pj, weights, min_conf=0.45, min_margin=0.04):
    m.weights = weights; m.min_conf, m.min_margin = min_conf, min_margin
    ok = ab = wr = 0
    conf = defaultdict(int)
    for pj, descs in by_pj.items():
        lst = m._refs[pj]
        for i in range(len(descs)):
            held = lst.pop(i)
            r = m.match(descs[i])
            lst.insert(i, held)
            if r.name is None:
                ab += 1
            elif _norm_key(r.name) == _norm_key(pj):
                ok += 1
            else:
                wr += 1; conf[(pj, r.name)] += 1
    t = max(1, ok + ab + wr)
    return ok / t, ab / t, wr / t, conf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs=3, type=float, default=None, metavar=("WH", "WN", "WR"))
    args = ap.parse_args()
    m, by_pj = _load()
    n = sum(len(v) for v in by_pj.values())
    print(f"PJs>=2: {len(by_pj)} | badges test: {n} | base pesos=({_W_HIST},{_W_NCC},{_W_REG})\n")

    if args.weights:
        grid = [tuple(args.weights)]
    else:
        # barrido alrededor de la base, normalizado a suma 1
        grid = []
        for wh in (0.30, 0.40, 0.50):
            for wn in (0.35, 0.45, 0.55):
                wr = max(0.05, 1.0 - wh - wn)
                grid.append((round(wh, 2), round(wn, 2), round(wr, 2)))

    print(f"{'w_hist':>7} {'w_ncc':>6} {'w_reg':>6} | {'top1':>6} {'abst':>6} {'wrong':>6}")
    best = None
    for w in grid:
        top1, abst, wrong, conf = evaluate(m, by_pj, w)
        print(f"{w[0]:>7.2f} {w[1]:>6.2f} {w[2]:>6.2f} | {top1:>6.0%} {abst:>6.0%} {wrong:>6.0%}")
        score = top1 - 3.0 * wrong          # robustez: penaliza fuerte los wrongs
        if best is None or score > best[0]:
            best = (score, w, top1, abst, wrong, conf)
    _s, w, top1, abst, wrong, conf = best
    print(f"\nMEJOR pesos=({w[0]},{w[1]},{w[2]}) → top1={top1:.0%} abst={abst:.0%} wrong={wrong:.0%}")
    if conf:
        print("Confusiones (look-alikes) en el mejor punto:")
        for (a, b), c in sorted(conf.items(), key=lambda kv: -kv[1]):
            print(f"  {a} -> {b}  x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fase 5R.3/tuning — GO/NO-GO híbrido leave-one-out multi-ref sobre badges S17.

Producción para PJs poseídos: librería = -ico + N badges cosechados por PJ. Cada
badge se testea con los OTROS del mismo PJ como referencia (sin fuga). Sweep de
gate (min_conf/min_margin) para elegir el punto robusto.
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
from app.core.avatar_descriptor import AvatarMatcher, build_descriptor, build_name_map  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402


def _imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="S17_*", help="glob de crops a evaluar (S17_* o S18_*/S8_*)")
    ap.add_argument("--seed-ico", action="store_true", default=True)
    ap.add_argument("--no-seed-ico", dest="seed_ico", action="store_false",
                    help="sin semilla -ico (matcher de fila puro cosecha)")
    args = ap.parse_args()
    patterns = args.pattern.split("/")
    labeled = ROOT / "audit" / "labeled_badges"
    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    nm = build_name_map(stems, roster)

    # descriptores cosechados por PJ (según patrón: badge S17 o avatar de fila S8/S18)
    by_pj: dict[str, list] = defaultdict(list)
    for pjdir in sorted(glob.glob(str(labeled / "*"))):
        label = os.path.basename(pjdir)
        for pat in patterns:
            for p in sorted(glob.glob(pjdir + "/" + pat + ".png")):
                d = build_descriptor(_imread_u(p))
                if d is not None:
                    by_pj[label].append(d)
    by_pj = {k: v for k, v in by_pj.items() if len(v) >= 2}
    n_test = sum(len(v) for v in by_pj.values())
    print(f"Patrón={args.pattern} seed_ico={args.seed_ico} | PJs>=2: {len(by_pj)} | test: {n_test}\n")

    # matcher: -ico (opcional) + reject + TODAS las refs cosechadas (multi-ref)
    if args.seed_ico:
        m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                       ROOT / "app/resources/avatar_reject", name_map=nm)
    else:
        m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                       ROOT / "app/resources/avatar_reject", name_map=nm)
        m._refs.clear()  # sin semilla -ico (matcher de fila puro cosecha), conserva reject
    for pj, descs in by_pj.items():
        for d in descs:
            m.add_reference(pj, d, max_per_name=10)

    def evaluate(min_conf, min_margin):
        m.min_conf, m.min_margin = min_conf, min_margin
        ok = ab = wr = 0
        conf = defaultdict(int)
        for pj, descs in by_pj.items():
            lst = m._refs[pj]
            for i in range(len(descs)):
                held = lst.pop(i)              # leave-one-out: saco el badge a testear
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

    print("Sweep de gate (leave-one-out multi-ref):")
    print(f"  {'min_conf':>8} {'min_margin':>10} {'top1':>6} {'abst':>6} {'wrong':>6}")
    best = None
    for mc in (0.0, 0.40, 0.50):
        for mm in (0.0, 0.02, 0.04, 0.06):
            top1, abst, wrong, conf = evaluate(mc, mm)
            print(f"  {mc:>8.2f} {mm:>10.2f} {top1:>6.0%} {abst:>6.0%} {wrong:>6.0%}")
            # objetivo: maximizar top1 penalizando wrong (robustez = pocos falsos)
            score = top1 - 2.0 * wrong
            if best is None or score > best[0]:
                best = (score, mc, mm, conf)
    print(f"\nMejor: min_conf={best[1]} min_margin={best[2]}")
    if best[3]:
        print("Errores en el mejor punto:")
        for (a, b), c in sorted(best[3].items(), key=lambda kv: -kv[1]):
            print(f"  {a} -> {b}  x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

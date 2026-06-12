"""Fase 5R.3 — GO/NO-GO: valida crops cosechados etiquetados contra el matcher.

Usa name_map (alias roster) + lectura unicode-safe + comparación por _norm_key,
desglosado por pantalla (S8/S18 = row-head localizador existente; S17 = badge de
grilla localizador experimental).
"""
from __future__ import annotations
import glob
import os
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher, build_name_map  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402


def _imread_u(p: str):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def main() -> int:
    labeled = ROOT / "audit" / "labeled_badges"
    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    nm = build_name_map(stems, roster)
    m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                   ROOT / "app/resources/avatar_reject", name_map=nm)
    print(f"Matcher: {len(m.names)} refs\n")

    stats = defaultdict(lambda: [0, 0, 0])     # grupo -> [ok, abst, wrong]
    conf = defaultdict(int)
    per_pj = defaultdict(lambda: [0, 0, 0])    # solo S8/S18
    for pjdir in sorted(glob.glob(str(labeled / "*"))):
        gt = _norm_key(os.path.basename(pjdir))
        for p in glob.glob(pjdir + "/*.png"):
            st = os.path.basename(p).split("_")[0]
            grp = "S8/S18" if st in ("S8", "S18", "S19") else st
            img = _imread_u(p)
            if img is None:
                continue
            r = m.match(img)
            slot = 1 if r.name is None else (0 if _norm_key(r.name) == gt else 2)
            stats[grp][slot] += 1
            if grp == "S8/S18":
                per_pj[os.path.basename(pjdir)][slot] += 1
            if slot == 2:
                conf[(gt, _norm_key(r.name))] += 1

    for grp in sorted(stats):
        ok, ab, wr = stats[grp]; t = max(1, ok + ab + wr)
        print(f"{grp:8} top1={ok/t:.0%}  abst={ab/t:.0%}  wrong={wr/t:.0%}   (n={ok+ab+wr})")
    print("\nPJs con error o abstención (S8/S18):")
    for pj, (ok, ab, wr) in sorted(per_pj.items()):
        if ab or wr:
            print(f"  {pj:16} ok={ok} abst={ab} wrong={wr}")
    print("\nConfusiones top (todas las pantallas):")
    for (a, b), c in sorted(conf.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {a} -> {b}  x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

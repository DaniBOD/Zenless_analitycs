"""Fase 5R.C.5 — Medición GO/NO-GO de la librería de badges COMPLETA (47/47).

Leave-one-out directo sobre los descriptores del .npz cosechado (no requiere
re-extraer imágenes): por cada badge, se lo saca de las refs de su PJ y se
matchea contra el resto (otras refs del mismo PJ + -ico semilla + reject). Mide
discriminación inter-PJ con las refs ricas. Reporta top1/abstención/wrong global,
PJs que fallan, y matriz de confusión (look-alikes).

NOTA: esto mide sobre badges COSECHADOS (limpios, del flujo-ancla). Es optimista
respecto al gap "dueño incierto" en vivo (frames a mitad de scroll). El número
real-real sale del QA en vivo contra el equip_map. Esto da el techo de discriminación.

Uso:
    python tools/measure_badge_lib.py                       # usa el snapshot del repo
    python tools/measure_badge_lib.py <ruta.npz>
"""
from __future__ import annotations
import glob
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import (  # noqa: E402
    AvatarMatcher, AvatarDescriptor, build_name_map,
)
from app.core.stats_vocab import _norm_key  # noqa: E402

_DEFAULT_NPZ = ROOT / "audit" / "avatar_badge_v2_snapshot_20260612_full47.npz"


def main() -> int:
    npz_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_NPZ
    if not npz_path.exists():
        print(f"No existe el npz: {npz_path}")
        return 1

    # Roster + name_map (-ico → roster) + matcher semilla (-ico + reject).
    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    nm = build_name_map(stems, roster)
    m = AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                   ROOT / "app/resources/avatar_reject", name_map=nm)

    # Reconstruir descriptores del npz y agruparlos por PJ.
    d = np.load(str(npz_path), allow_pickle=True)
    names = [str(x) for x in d["names"]]
    by_pj: dict[str, list] = defaultdict(list)
    for i, nm_i in enumerate(names):
        desc = AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                d["gray"][i], bool(d["is_gray"][i]))
        by_pj[nm_i].append(desc)
        m.add_reference(nm_i, desc, max_per_name=99)   # cargar TODAS para la medición

    n = sum(len(v) for v in by_pj.values())
    print(f"npz: {npz_path.name} | PJs: {len(by_pj)} | refs cosechadas: {n} "
          f"| refs totales matcher (con -ico): {len(m.names)}\n")

    # Recolectar (gt, pred, conf, rejected) por badge con leave-one-out.
    results = []   # (pj, pred_name|None, conf)
    for pj, descs in by_pj.items():
        lst = m._refs.get(pj)
        if lst is None:
            continue
        for desc in descs:
            idx = next((j for j, x in enumerate(lst) if x is desc), None)
            held = lst.pop(idx) if idx is not None else None
            r = m.match(desc)
            if held is not None:
                lst.insert(idx, held)
            results.append((pj, r.name, r.conf))

    def report(guard: float, title: str):
        """Acepta el match solo si conf >= guard (None o conf bajo → abstención)."""
        ok = ab = wr = 0
        conf = defaultdict(int)
        per_pj = defaultdict(lambda: [0, 0, 0])
        for pj, pred, c in results:
            if pred is None or c < guard:
                ab += 1; per_pj[pj][1] += 1
            elif _norm_key(pred) == _norm_key(pj):
                ok += 1; per_pj[pj][0] += 1
            else:
                wr += 1; per_pj[pj][2] += 1; conf[(pj, pred)] += 1
        t = max(1, ok + ab + wr)
        print(f"\n=== {title} (guard conf>={guard}) ===")
        print(f"  TOP-1: {ok}/{t} = {ok/t:.1%}  |  ABSTENCIÓN: {ab}/{t} = {ab/t:.1%}  "
              f"|  WRONG: {wr}/{t} = {wr/t:.1%}")
        if conf:
            print("  Wrongs:", "  ".join(f"{a}->{b} x{c}" for (a, b), c in
                                          sorted(conf.items(), key=lambda kv: -kv[1])))
        return per_pj

    report(0.0, "Gate base match() — sin guard extra")
    per_pj = report(0.80, "GUARD S17 LIVE (s17_match _S17_GUARD_DEFAULT)")

    fails = {pj: v for pj, v in per_pj.items() if v[2]}   # solo wrongs bajo guard live
    print("\nPJs con WRONG bajo guard 0.80 (RNF-02 — foco):",
          ", ".join(f"{pj}(w={v[2]})" for pj, v in fails.items()) or "NINGUNO ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Diagnóstico: por qué algunos PJs abstienen. Para cada PJ, leave-one-out de sus
badges cosechados contra la librería (–ico + cosecha), reportando margen y top-2.
"""
from __future__ import annotations
import glob, os
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher, build_descriptor, build_name_map, descriptor_distance
from app.core.stats_vocab import _norm_key

def rd(p): return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)

def main():
    labeled = ROOT/"audit"/"labeled_badges"
    from app.db.connection import get_connection
    con=get_connection(); roster=[str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems=[p.stem for p in (ROOT/"app/resources/avatar_refs").glob("*.png")]
    nm=build_name_map(stems, roster)
    m=AvatarMatcher.from_folders(ROOT/"app/resources/avatar_refs", ROOT/"app/resources/avatar_reject", name_map=nm)
    by_pj={}
    for d in sorted(glob.glob(str(labeled/"*"))):
        name=os.path.basename(d); badges=[build_descriptor(rd(p)) for p in sorted(glob.glob(d+"/S17_*.png"))]
        badges=[b for b in badges if b is not None]
        if badges: by_pj[name]=badges
    for pj,ds in by_pj.items():
        for x in ds: m.add_reference(pj, x, max_per_name=10)
    focus=["Yuzuha","Burnice","Jane","Vivian","Alice","Yanagi","Nangong Yu"]
    print(f"{'PJ':<14} {'n':>2} {'ok':>3} {'abst':>4} {'wrong':>5}  margen_medio  segundo_mas_cercano")
    for pj in focus:
        if pj not in by_pj:
            print(f"{pj:<14} (sin cosecha)"); continue
        ds=by_pj[pj]; lst=m._refs[pj]; ok=ab=wr=0; margins=[]; conf2={}
        for i in range(len(ds)):
            held=lst.pop(i); r=m.match(ds[i]); lst.insert(i,held)
            if r.name is None:
                ab+=1
                # ver el top real sin gate
                if r.top:
                    n2=r.top[1][0] if len(r.top)>1 else "-"; conf2[n2]=conf2.get(n2,0)+1
            elif _norm_key(r.name)==_norm_key(pj): ok+=1; margins.append(r.margin)
            else: wr+=1
        mm=f"{np.mean(margins):.3f}" if margins else "-"
        c2=",".join(f"{k}:{v}" for k,v in sorted(conf2.items(),key=lambda x:-x[1])[:2])
        print(f"{pj:<14} {len(ds):>2} {ok:>3} {ab:>4} {wr:>5}  {mm:>11}  {c2}")

if __name__=="__main__": raise SystemExit(main())

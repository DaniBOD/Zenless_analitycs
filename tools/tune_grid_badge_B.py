"""Sub-fase B: tuning de la ID de candidatos en la grilla S17, contra la verdad de
tierra de Ejemplo1 (20 discos, etiquetados por el usuario 2026-06-12). Dos palancas:
  1) guard de identify_s17 (umbral de confianza).
  2) offset del recorte del badge (_BADGE_CX_F/CY_F/R_F).
Mide por config: OK (dueño correcto), WRONG (dueño equivocado — debe ser 0), miss,
y free-OK (sueltos correctamente abstenidos). Matchea contra las refs YA cosechadas.
"""
from __future__ import annotations
import glob
import re

import cv2
import numpy as np
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app.core.detector as det                                  # noqa: E402
from app.core.detector import crop_grid_selected_badge          # noqa: E402
from app.core.agent_identifier import AgentIdentifier           # noqa: E402

F = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla"
TRUTH = {1: 'Nangong Yu', 2: 'Yuzuha', 3: 'LIBRE', 4: 'Yanagi', 5: 'LIBRE', 6: 'Piper',
         7: 'Seth', 8: 'LIBRE', 9: 'Dialyn', 10: 'Rina', 11: 'Jane', 12: 'Grace',
         13: 'Burnice', 14: 'Vivian', 15: 'César', 16: 'Gatillo', 17: 'Soukaku',
         18: 'Nicole', 19: 'Sunna', 20: 'Lucía'}


def rd(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def k(p):
    return int(re.search(r'_(\d+)\.png$', p).group(1))


def evaluate(ident, guard, cx_f, cy_f, r_f):
    det._BADGE_CX_F, det._BADGE_CY_F, det._BADGE_R_F = cx_f, cy_f, r_f
    ok = wrong = miss = freeok = freebad = 0
    for p in sorted(glob.glob(str(F / "Ejemplo1_*.png")), key=k):
        n = k(p)
        b = crop_grid_selected_badge(rd(p))
        r = ident.identify_s17(b, min_sim=guard) if b is not None else None
        t = TRUTH[n]
        if t == 'LIBRE':
            freeok += (r is None); freebad += (r is not None)
        elif r is None:
            miss += 1
        elif r[0] == t:
            ok += 1
        else:
            wrong += 1
    return ok, wrong, miss, freeok, freebad


def main() -> int:
    ident = AgentIdentifier(prune=False)
    print(f"Refs: {len(ident._badge._refs)} PJs · offset base=({det._BADGE_CX_F},{det._BADGE_CY_F},{det._BADGE_R_F})")
    base = (det._BADGE_CX_F, det._BADGE_CY_F, det._BADGE_R_F)

    print("\n=== 1) BARRIDO DE GUARD (offset base) ===")
    print(f"{'guard':>6} | {'OK':>3} {'WRONG':>5} {'miss':>4} | sueltos OK/{'bad':>3}")
    for g in [0.74, 0.76, 0.78, 0.80, 0.82, 0.84, 0.86]:
        ok, wr, ms, fok, fbad = evaluate(ident, g, *base)
        flag = "  <-- WRONG!" if wr else ("  <= seguro" if fbad == 0 else "")
        print(f"{g:>6.2f} | {ok:>3} {wr:>5} {ms:>4} | {fok}/3      {fbad}{flag}")

    print("\n=== 2) BARRIDO DE OFFSET (guard 0.80) ===")
    print(f"{'cx':>5} {'cy':>5} {'r':>5} | {'OK':>3} {'WRONG':>5} {'miss':>4} | sueltos")
    best = None
    for cx in [0.82, 0.84, 0.86, 0.88, 0.90]:
        for cy in [0.08, 0.11, 0.13, 0.16, 0.19]:
            for r in [0.16, 0.18, 0.20, 0.22]:
                ok, wr, ms, fok, fbad = evaluate(ident, 0.80, cx, cy, r)
                score = ok - 10 * wr - 2 * fbad   # penaliza fuerte wrong/falso-dueño
                if best is None or score > best[0]:
                    best = (score, cx, cy, r, ok, wr, ms, fok, fbad)
    s, cx, cy, r, ok, wr, ms, fok, fbad = best
    print(f"MEJOR offset @guard0.80: ({cx},{cy},{r}) -> OK={ok} WRONG={wr} miss={ms} sueltos={fok}/3 (base OK={evaluate(ident,0.80,*base)[0]})")

    print("\n=== 3) MEJOR offset + barrido de guard ===")
    for g in [0.76, 0.78, 0.80, 0.82, 0.84]:
        o = evaluate(ident, g, cx, cy, r)
        print(f"  guard={g:.2f} offset=({cx},{cy},{r}) -> OK={o[0]} WRONG={o[1]} miss={o[2]} sueltos={o[3]}/3 bad={o[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

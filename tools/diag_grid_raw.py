"""Por cada frame de 16_discos_pj_grilla: match() CRUDO del badge (sin colapsar a
identify_s17) → name, conf, margen, rejected, top-3 distancias. Clasifica el motivo de
cada abstención: conf baja / margen chico / reject-set (lock/rareza/disco) — para
distinguir disco SUELTO (abstención correcta) de disco equipado PERDIDO (miss real).
"""
from __future__ import annotations
import glob
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.detector import crop_grid_selected_badge          # noqa: E402
from app.core.agent_identifier import AgentIdentifier            # noqa: E402

FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla"


def rd(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def numkey(p):
    m = re.search(r"_(\d+)\.png$", p)
    return int(m.group(1)) if m else 0


def main() -> int:
    ident = AgentIdentifier()
    m = ident._badge
    print(f"min_conf={m.min_conf} min_margin={m.min_margin} · refs={len(m._refs)} PJs "
          f"· rejects={len(getattr(m, '_rejects', []))}")
    groups = defaultdict(list)
    for p in sorted(glob.glob(str(FOLDER / "*.png"))):
        g = re.match(r"(Ejemplo\d+)_", Path(p).stem).group(1)
        groups[g].append(p)

    for g, paths in groups.items():
        print(f"\n===== {g} =====")
        for p in sorted(paths, key=numkey):
            badge = crop_grid_selected_badge(rd(p))
            if badge is None:
                print(f"  {numkey(p):>2}: badge=NO")
                continue
            r = m.match(badge)
            top = " ".join(f"{n}:{d:.3f}" for n, d in r.top[:3])
            motivo = ""
            if r.name is None:
                if r.rejected:
                    motivo = "REJECT(lock/disco)"
                elif r.conf < m.min_conf:
                    motivo = f"conf<{m.min_conf}"
                elif r.margin < m.min_margin:
                    motivo = f"margen<{m.min_margin}"
            verdict = r.name if r.name else f"ABSTIENE[{motivo}]"
            print(f"  {numkey(p):>2}: {verdict:28} conf={r.conf:.3f} margen={r.margin:.3f} "
                  f"rej={int(r.rejected)} | top: {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

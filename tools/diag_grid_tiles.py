"""Grid de tiles seleccionados (alta-res) de los frames de 16_discos_pj_grilla, para
clasificar visualmente cada INCIERTO: ¿el tile tiene badge de dueño (miss real) o está
suelto/lock (abstención correcta)? Recorta el tile resaltado + un margen y lo etiqueta
con la predicción del matcher.
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
from app.core.detector import crop_grid_selected_badge, _selected_grid_tile_bbox  # noqa: E402
from app.core.agent_identifier import AgentIdentifier            # noqa: E402

FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla"
OUT = ROOT / "audit" / "grid_diag"
OUT.mkdir(parents=True, exist_ok=True)


def rd(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def numkey(p):
    m = re.search(r"_(\d+)\.png$", p)
    return int(m.group(1)) if m else 0


def main() -> int:
    ident = AgentIdentifier()
    groups = defaultdict(list)
    for p in sorted(glob.glob(str(FOLDER / "*.png"))):
        g = re.match(r"(Ejemplo\d+)_", Path(p).stem).group(1)
        groups[g].append(p)

    for g, paths in groups.items():
        paths = sorted(paths, key=numkey)
        CELL = 230
        cols = 5
        rows = (len(paths) + cols - 1) // cols
        canvas = np.full((rows * CELL, cols * CELL, 3), 20, np.uint8)
        for idx, p in enumerate(paths):
            fr = rd(p)
            H, W = fr.shape[:2]
            bb = _selected_grid_tile_bbox(fr)
            badge = crop_grid_selected_badge(fr)
            r = ident.identify_s17(badge) if badge is not None else None
            label = (f"{r[0]} {r[1]:.2f}" if r else ("INCIERTO" if badge is not None else "noTILE"))
            # recortar tile + margen generoso (incluye esquina sup-der = badge dueño)
            cell = np.full((CELL, CELL, 3), 35, np.uint8)
            if bb is not None:
                x, y, w, h = bb
                mx = int(0.12 * w); my = int(0.12 * h)
                x0 = max(0, x - mx); y0 = max(0, y - my)
                x1 = min(W, x + w + mx); y1 = min(H, y + h + my)
                crop = fr[y0:y1, x0:x1]
                if crop.size:
                    s = (CELL - 26) / max(crop.shape[0], crop.shape[1])
                    rs = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)))
                    cell[:rs.shape[0], :rs.shape[1]] = rs
            col = (90, 230, 90) if r else (100, 100, 235)
            cv2.putText(cell, f"{numkey(p)}: {label}", (4, CELL - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
            rr, cc = divmod(idx, cols)
            canvas[rr * CELL:(rr + 1) * CELL, cc * CELL:(cc + 1) * CELL] = cell
        out = OUT / f"{g}_tiles.png"
        cv2.imencode(".png", canvas)[1].tofile(str(out))
        print(f"{g}: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

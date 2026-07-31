"""Montaje visual de los badges recortados en frames reales de la grilla S17.
Por grupo EjemploN genera audit/grid_diag/<grupo>_montage.png: una fila por frame con
[ tile-bbox recortado | badge circular recortado | etiqueta predicha ]. Permite VER si
el crop cae sobre el badge de dueño correcto y qué tan limpio es.
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


def group_of(stem):
    m = re.match(r"(Ejemplo\d+)_", stem)
    return m.group(1) if m else stem


def numkey(p):
    m = re.search(r"_(\d+)\.png$", p)
    return int(m.group(1)) if m else 0


def main() -> int:
    ident = AgentIdentifier(prune=False)
    groups = defaultdict(list)
    for p in sorted(glob.glob(str(FOLDER / "*.png"))):
        groups[group_of(Path(p).stem)].append(p)

    for g, paths in groups.items():
        paths = sorted(paths, key=numkey)
        rows = []
        TILE_W, BADGE_W, ROW_H = 240, 120, 130
        for p in paths:
            fr = rd(p)
            bb = _selected_grid_tile_bbox(fr)
            badge = crop_grid_selected_badge(fr)
            # panel tile
            tile_img = np.full((ROW_H, TILE_W, 3), 30, np.uint8)
            if bb is not None:
                x, y, w, h = bb
                crop = fr[y:y + h, x:x + w]
                if crop.size:
                    ch = ROW_H; cw = int(crop.shape[1] * ch / crop.shape[0])
                    cw = min(cw, TILE_W)
                    tile_img[:, :cw] = cv2.resize(crop, (cw, ch))
            # panel badge
            badge_img = np.full((ROW_H, BADGE_W, 3), 30, np.uint8)
            label = "badge=NO"
            if badge is not None:
                bw = ROW_H; bb2 = cv2.resize(badge, (bw, bw))
                badge_img[:, :min(bw, BADGE_W)] = bb2[:, :min(bw, BADGE_W)]
                r = ident.identify_s17(badge)
                label = f"{r[0]} {r[1]:.2f}" if r else "INCIERTO"
            # panel texto
            txt = np.full((ROW_H, 360, 3), 30, np.uint8)
            cv2.putText(txt, Path(p).name, (6, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
            col = (90, 230, 90) if (badge is not None and "INCIERTO" not in label and "NO" not in label) else (90, 90, 230)
            cv2.putText(txt, label, (6, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
            rows.append(np.hstack([tile_img, badge_img, txt]))
        montage = np.vstack(rows)
        out = OUT / f"{g}_montage.png"
        cv2.imencode(".png", montage)[1].tofile(str(out))
        print(f"{g}: {len(paths)} frames -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

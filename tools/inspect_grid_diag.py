"""Inspecciona el volcado DANIBOD_GRID_DIAG (recortes de badge S17 por disco).

Agrupa por disco (prefijo de hash en el nombre), arma un MONTAJE por disco (los
crops de badge en fila, con su verdicto/conf), y un resumen de texto: cuántos
frames localizaron vs NOLOC, qué nombres/confs votó, y el ganador. Sirve para ver
A OJO por qué un disco posado queda 'incierto'/'no localizado'.

Uso:
    python tools/inspect_grid_diag.py [carpeta]     # default audit/grid_diag
Salida: <carpeta>/_montage_<key>.png + resumen por stdout.
"""
from __future__ import annotations
import glob
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIAG = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "audit" / "grid_diag"

_RE = re.compile(r"^([0-9a-f]{8})_(\d+)_(badge_(.+?)_([0-9.]+)|NOLOC)\.png$")


def main() -> int:
    files = sorted(glob.glob(str(DIAG / "*.png")))
    files = [f for f in files if not os.path.basename(f).startswith("_montage")]
    if not files:
        print(f"Sin crops en {DIAG}")
        return 1
    by_disc: dict[str, list] = defaultdict(list)
    for f in files:
        m = _RE.match(os.path.basename(f))
        if not m:
            continue
        key, idx, kind, name, conf = m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5)
        by_disc[key].append((idx, f, name, float(conf) if conf else None, kind == "NOLOC" or kind.startswith("NOLOC")))

    print(f"Discos distintos: {len(by_disc)} | crops totales: {len(files)}\n")
    for key, items in by_disc.items():
        items.sort()
        noloc = sum(1 for *_, isnoloc in items if isnoloc)
        votes: dict[str, float] = defaultdict(float)
        for _i, _f, name, conf, isnoloc in items:
            if not isnoloc and name and name not in ("none", "REJECT") and conf:
                votes[name] += conf
        winner = max(votes.items(), key=lambda kv: kv[1])[0] if votes else None
        seen = ", ".join(f"{n}:{c:.2f}" for n, c in
                         sorted(votes.items(), key=lambda kv: -kv[1])) or "—"
        print(f"[{key}] {len(items)} frames | NOLOC={noloc} | votado={winner or 'INCIERTO'} | {seen}")

        # Montaje: fila de crops de badge (NOLOC se omite del montaje de badges).
        crops = []
        for _i, f, name, conf, isnoloc in items:
            if isnoloc:
                continue
            img = cv2.imdecode(np.fromfile(f, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            img = cv2.resize(img, (72, 72), interpolation=cv2.INTER_NEAREST)
            lbl = f"{(name or '?')[:6]} {conf:.2f}" if conf else "?"
            img = cv2.copyMakeBorder(img, 16, 2, 2, 2, cv2.BORDER_CONSTANT, value=(20, 20, 20))
            cv2.putText(img, lbl, (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 255, 0), 1)
            crops.append(img)
        if crops:
            row = np.hstack(crops)
            out = DIAG / f"_montage_{key}.png"
            cv2.imencode(".png", row)[1].tofile(str(out))
    print(f"\nMontajes → {DIAG}/_montage_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

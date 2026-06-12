"""Pre-siembra la librería de badge (avatar_badge_v2.npz) con los badges cosechados
de `audit/labeled_badges/<PJ>/S17_*.png`, para que el QA readonly muestre la
identificación robusta (96%) sin necesidad de cosechar en vivo.

Escribe en la ruta que carga la app (LOCALAPPDATA por defecto). Los crops son
salida de `detector.crop_grid_selected_badge` (mismo que usa la app en vivo), así
que el encuadre es consistente. La app, al cargar, FUSIONA esto con la semilla -ico
→ multi-ref.
"""
from __future__ import annotations
import glob
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher  # noqa: E402
from app.core.agent_identifier import _default_library_path  # noqa: E402


def main() -> int:
    labeled = ROOT / "audit" / "labeled_badges"
    if not labeled.is_dir():
        print("No hay audit/labeled_badges (corré extract_harvested primero)."); return 1
    m = AvatarMatcher()
    n_pj = n_ref = 0
    for pjdir in sorted(glob.glob(str(labeled / "*"))):
        name = os.path.basename(pjdir)
        s17 = sorted(glob.glob(pjdir + "/S17_*.png"))
        if not s17:
            continue
        n_pj += 1
        for p in s17:
            img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None and m.add_reference(name, img, max_per_name=8):
                n_ref += 1
    badge_path = _default_library_path().with_name("avatar_badge_v2.npz")
    badge_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(badge_path)
    print(f"Pre-sembrados {n_ref} badges de {n_pj} PJs -> {badge_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

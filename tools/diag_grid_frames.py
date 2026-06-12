"""Diagnóstico sobre frames REALES de la grilla S17 (carpeta 16_discos_pj_grilla).
Para cada grupo EjemploN (mismo disco, varios frames), reporta por frame:
  - ¿se localiza el tile resaltado y se recorta el badge?
  - identify_s17(badge) → (dueño, conf) o abstención.
  - firma híbrida del disco (detail, hex) y si es "cercana" al primer frame del grupo
    (mide si la animación idle del modelo 3D rompe la firma → resetea la votación).
Esto aísla la causa del parpadeo residual: ¿crop inconsistente, descriptor débil, o
firma inestable que tira los votos?
"""
from __future__ import annotations
import glob
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.detector import crop_grid_selected_badge          # noqa: E402
from app.core.monitor import Monitor, _S17_SIG_DETAIL_MAX, _S17_SIG_HEX_MAX  # noqa: E402
from app.core.agent_identifier import AgentIdentifier            # noqa: E402

FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla"
# Etiqueta esperada por grupo (lo que el usuario dijo). Ajustar si agrega más.
EXPECTED = {"Ejemplo1": "Nangong Yu", "Ejemplo2": "Gatillo"}  # Gatillo = Trigger


def rd(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def group_of(stem):
    m = re.match(r"(Ejemplo\d+)_", stem)
    return m.group(1) if m else stem


def main() -> int:
    ident = AgentIdentifier()
    print(f"Librería badge cargada · refs={len(ident.names_s17)} PJs")
    groups = defaultdict(list)
    for p in sorted(glob.glob(str(FOLDER / "*.png"))):
        groups[group_of(Path(p).stem)].append(p)

    for g, paths in groups.items():
        exp = EXPECTED.get(g, "?")
        print(f"\n===== {g}  (esperado: {exp})  · {len(paths)} frames =====")
        base_sig = None
        votes = Counter()
        conf_sum = defaultdict(float)
        n_badge = n_id = 0
        for p in paths:
            fr = rd(p)
            badge = crop_grid_selected_badge(fr)
            sig = Monitor._s17_disc_signature(fr)
            if base_sig is None:
                base_sig = sig
            dd = Monitor._sig_component_diff(sig[0], base_sig[0]) if sig and base_sig else float("inf")
            dh = Monitor._sig_component_diff(sig[1], base_sig[1]) if sig and base_sig else float("inf")
            close = (dd <= _S17_SIG_DETAIL_MAX and dh <= _S17_SIG_HEX_MAX)
            if badge is None:
                print(f"  {Path(p).name:18} badge=NO   sig_d={dd:5.2f} sig_h={dh:5.2f} close={close}")
                continue
            n_badge += 1
            r = ident.identify_s17(badge)
            if r:
                n_id += 1
                votes[r[0]] += 1
                conf_sum[r[0]] += r[1]
                tag = f"{r[0]} ({r[1]:.3f})"
            else:
                tag = "INCIERTO"
            print(f"  {Path(p).name:18} badge=ok  {tag:24} sig_d={dd:5.2f} sig_h={dh:5.2f} close={close}")
        winner = votes.most_common(1)[0][0] if votes else "—"
        ok = "✅" if winner == exp else "❌"
        print(f"  ---- badges={n_badge}/{len(paths)} identificados={n_id} · "
              f"VOTO GANADOR={winner} {ok} · dist={dict(votes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

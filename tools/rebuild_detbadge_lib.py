"""Hito L.2b (Fase 5R) — Reconstruye la librería del DETALLE-badge con el encuadre
NUEVO (Hough refine).

El imán del detail (L.1) NO era librería sucia sino ENCUADRE: el crop viejo (radio fijo)
ahogaba al avatar en fondo. Cambiado `detector.crop_detail_badge` a Hough (L.2b), las refs
viejas (`avatar_detbadge_v2.npz`) quedan en OTRO dominio (encuadre viejo) → hay que
reconstruir con el MISMO crop nuevo. Las etiquetas eran correctas; solo cambia el encuadre.

Siembra desde los frames GOLD `audit/harvest/*__S17__*` (label = latch certero del
flujo-ancla). Hace BACKUP del npz viejo, escribe el nuevo en la ruta runtime y un snapshot
versionable en `audit/`. La cosecha en vivo (`-BadgeHarvest`) seguirá sumando refs con el
mismo crop nuevo.

Uso:
    .venv/Scripts/python.exe tools/rebuild_detbadge_lib.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher, build_name_map  # noqa: E402
from app.core.detector import crop_detail_badge  # noqa: E402
from app.core.agent_identifier import _default_library_path  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402

_HARVEST = ROOT / "audit" / "harvest"
_REFS = ROOT / "app" / "resources" / "avatar_refs"

# PJs CONTAMINADOS en la cosecha vieja (anclas con bug + crop viejo, pre-2026-06-19):
# sus frames `*__S17__*` no son del PJ etiquetado. Verificado visualmente
# (audit/detbadge_magnet_diag/CONTACT_det_all.png):
#   - ben    → las caras son SOUKAKU (hacía empatar/abstener a Soukaku, QA 2026-06-19).
#   - cissia → fragmentos de texto "(5)" en vez de cara.
# Se EXCLUYEN del rebuild para no re-introducir las refs malas. Re-cosechar en vivo con
# `-BadgeHarvest` (el ancla ya cross-checkea → cosecha limpia) y se re-agregan solas.
_CONTAMINATED = {_norm_key(x) for x in ("ben", "cissia")}


def _imread(p: str) -> np.ndarray | None:
    d = np.fromfile(p, np.uint8)
    return cv2.imdecode(d, cv2.IMREAD_COLOR) if d.size else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="no escribe; solo reporta")
    args = ap.parse_args()

    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(_REFS / "*.png"))]
    nm = build_name_map(stems, roster)
    # Las etiquetas del harvest son _norm_key (minúsculas, p.ej. "nangongyu"), NO stems de
    # -ico ("Nangong-Yu"). Canonicalizar por _norm_key del roster → nombre canónico, IGUAL que
    # AgentIdentifier._canonical_name. Si no, las refs quedan con clave minúscula y
    # `prune_to_roster` las BORRA al cargar (det_match=0 en vivo). Ver QA 2026-06-18.
    canon_map = {_norm_key(r): r for r in roster}

    frames = sorted(glob.glob(str(_HARVEST / "*__S17__*.png")))
    if not frames:
        print("No hay frames audit/harvest/*__S17__* — nada que sembrar."); return 1

    m = AvatarMatcher()   # SIN -ico (el detail no comparte refs con el grid), sin reject (se carga en runtime)
    per_pj = Counter()
    loc = 0
    skipped_contam = 0
    for p in frames:
        label = os.path.basename(p).split("__S17__")[0]
        if _norm_key(label) in _CONTAMINATED:        # frames mal-etiquetados (cosecha vieja)
            skipped_contam += 1
            continue
        fr = _imread(p)
        if fr is None:
            continue
        crop = crop_detail_badge(fr)
        if crop is None:
            continue
        canon = canon_map.get(_norm_key(label)) or nm.get(label) or label
        if m.add_reference(canon, crop, max_per_name=99):
            per_pj[canon] += 1
            loc += 1

    print(f"Frames S17: {len(frames)} | excluidos (contaminados): {skipped_contam} "
          f"| det localizado (Hough): {loc} | PJs: {len(per_pj)}")
    miss = [k for k, v in sorted(per_pj.items()) if v < 2]
    if miss:
        print(f"PJs con <2 refs (LOO flojo / baja-sat): {miss}")
    all_canon = {canon_map.get(_norm_key(os.path.basename(p).split('__S17__')[0]))
                 or os.path.basename(p).split('__S17__')[0] for p in frames}
    no_ref = sorted(all_canon - set(per_pj))
    if no_ref:
        print(f"PJs SIN ninguna ref: {no_ref}")

    runtime = _default_library_path().with_name("avatar_detbadge_v2.npz")
    today = _dt.date.today().isoformat().replace("-", "")
    snapshot = ROOT / "audit" / f"avatar_detbadge_v2_snapshot_{today}_hough.npz"

    if args.dry_run:
        print(f"\n[dry-run] escribiría → {runtime}\n[dry-run] snapshot → {snapshot}")
        return 0

    if runtime.exists():
        bak = runtime.with_name(f"avatar_detbadge_v2.backup_preL2b_{today}.npz")
        shutil.copy2(runtime, bak)
        print(f"\nBackup del npz viejo → {bak}")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    m.save(runtime)
    m.save(snapshot)
    print(f"Librería NUEVA (Hough) → {runtime}")
    print(f"Snapshot versionable   → {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

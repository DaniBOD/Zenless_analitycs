"""Quita las refs de uno o más PJs de una librería de avatares (.npz), con backup.

Para sacar PJs contaminados (refs de otro PJ, p.ej. Antón↔Harumasa de la cosecha vieja)
antes de re-cosecharlos en vivo. Funciona con cualquier .npz formato AvatarMatcher
(grilla `avatar_badge_v2.npz` o detalle `avatar_detbadge_v2.npz`).

Uso:
    .venv/Scripts/python.exe tools/clean_lib_refs.py <ruta.npz> "Antón" "Harumasa" "Ben" "Cissia"
    .venv/Scripts/python.exe tools/clean_lib_refs.py --grid  "Antón" "Harumasa" ...   # ruta runtime grilla
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.agent_identifier import _default_library_path  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--grid":
        path = _default_library_path().with_name("avatar_badge_v2.npz")
        names_to_drop = args[1:]
    elif args[0] == "--detail":
        path = _default_library_path().with_name("avatar_detbadge_v2.npz")
        names_to_drop = args[1:]
    else:
        path = Path(args[0])
        names_to_drop = args[1:]
    if not path.exists():
        print(f"No existe: {path}")
        return 1
    if not names_to_drop:
        print("Faltan PJs a quitar.")
        return 1

    drop = {_norm_key(n) for n in names_to_drop}
    d = np.load(str(path), allow_pickle=True)
    names = [str(x) for x in d["names"]]
    keep = [i for i, nm in enumerate(names) if _norm_key(nm) not in drop]
    dropped = len(names) - len(keep)
    if dropped == 0:
        print(f"Ningún ref coincide con {names_to_drop} en {path.name} (nada que hacer).")
        return 0

    bak = path.with_name(path.stem + ".backup_preclean.npz")
    shutil.copy2(path, bak)
    keep = np.array(keep)
    np.savez(
        str(path),
        names=np.array([names[i] for i in keep], dtype=object),
        hist=d["hist"][keep], ncc=d["ncc"][keep], regions=d["regions"][keep],
        gray=d["gray"][keep], is_gray=d["is_gray"][keep],
    )
    from collections import Counter
    c = Counter(str(x) for x in np.load(str(path), allow_pickle=True)["names"])
    print(f"{path.name}: quitadas {dropped} refs de {names_to_drop} | backup → {bak.name}")
    print(f"  ahora: {sum(c.values())} refs / {len(c)} PJs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

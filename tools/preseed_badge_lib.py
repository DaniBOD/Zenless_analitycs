"""Siembra/restaura las librerías de badges en la ruta que carga la app (LOCALAPPDATA).

Dos fuentes, según lo que haya:

* `--source snapshot` — copia un `.npz` versionado de `audit/`. Es lo que corresponde cuando la
  librería del runtime se perdió: los snapshots tienen la cosecha entera (el del grid, 459 refs
  de 47 PJs con 6-10 cada uno), mucho más rica que los recortes sueltos.
* `--source labeled` — reconstruye desde `audit/labeled_badges/<PJ>/`. Sirve para superficies sin
  snapshot (el `row` no tiene ninguno) y para regenerar con un encuadre nuevo.

Los recortes etiquetados son salida de los mismos `crop_*` que usa la app en vivo (S17 → grid,
S8/S18 → row), así que el encuadre es consistente — la regla like-with-like de la Fase 5R. La
app, al cargar, FUSIONA esto con la semilla `-ico`.

Contexto de por qué existe el modo snapshot (2026-07-31): la carpeta del runtime se vació y el
grid quedó solo con la semilla `-ico` (arte de comunidad, otro dominio). Medido contra los
badges reales etiquetados: **4.3% top-1 y 14.6% wrong**, con Cissia llevándose 14 discos ajenos.
Restaurado el snapshot: **93.3% / 2.4%**. Verificar siempre con:

    python tools/measure_badge_lib.py --against-labeled [--surface row]

Uso:
    python tools/preseed_badge_lib.py --surface grid --source snapshot
    python tools/preseed_badge_lib.py --surface row  --source labeled
    python tools/preseed_badge_lib.py --surface grid --source labeled   # comportamiento viejo
"""
from __future__ import annotations
import argparse
import collections
import glob
import os
import shutil
from datetime import date
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher  # noqa: E402
from app.core.agent_identifier import _default_library_path  # noqa: E402

_LABELED = ROOT / "audit" / "labeled_badges"
_AUDIT = ROOT / "audit"

# Por superficie: nombre del .npz que carga la app, qué recortes etiquetados le corresponden, y
# el snapshot versionado que hace de baseline.
_SURFACES = {
    "grid": {
        "npz": "avatar_badge_v2.npz",
        "globs": ("S17_*.png",),
        "snapshot": "avatar_badge_v2_snapshot_20260612_full47.npz",
    },
    "row": {
        "npz": "avatar_row_v2.npz",
        "globs": ("S8_*.png", "S18_*.png"),
        "snapshot": None,      # no existe todavía; `--source labeled` lo genera
    },
}
_MAX_PER_NAME = 8


def _cobertura(path: Path) -> str:
    if not path.exists():
        return "(no existe)"
    c = collections.Counter(str(x) for x in np.load(str(path), allow_pickle=True)["names"])
    if not c:
        return "(vacía)"
    return (f"{len(c)} clases · {sum(c.values())} refs · "
            f"min {min(c.values())} max {max(c.values())}")


def _backup(path: Path) -> Path | None:
    """Copia de seguridad antes de pisar. Nunca se sobreescribe sin dejar rastro."""
    if not path.exists():
        return None
    dst = path.with_name(f"{path.stem}.backup_{date.today():%Y%m%d}_{os.getpid()}.npz")
    shutil.copy2(path, dst)
    return dst


def _desde_labeled(surface: str, dst: Path) -> int:
    if not _LABELED.is_dir():
        print(f"No existe {_LABELED} (corré extract_harvested primero)."); return 0
    m = AvatarMatcher()
    n_pj = n_ref = 0
    for pjdir in sorted(glob.glob(str(_LABELED / "*"))):
        name = os.path.basename(pjdir)
        crops = []
        for pat in _SURFACES[surface]["globs"]:
            crops += sorted(glob.glob(os.path.join(pjdir, pat)))
        if not crops:
            continue
        n_pj += 1
        for p in crops:
            img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None and m.add_reference(name, img, max_per_name=_MAX_PER_NAME):
                n_ref += 1
    if not n_ref:
        print("No se armó ninguna ref."); return 0
    m.save(dst)
    print(f"Reconstruidas {n_ref} refs de {n_pj} PJs desde recortes etiquetados.")
    return n_ref


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surface", choices=sorted(_SURFACES), default="grid")
    ap.add_argument("--source", choices=("snapshot", "labeled"), default="labeled")
    ap.add_argument("--snapshot", default=None, help="ruta del .npz a copiar (default: el de audit/)")
    ap.add_argument("--save-snapshot", action="store_true",
                    help="además, guardar el resultado como baseline versionado en audit/")
    args = ap.parse_args()

    cfg = _SURFACES[args.surface]
    dst = _default_library_path().with_name(cfg["npz"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"superficie : {args.surface}")
    print(f"destino    : {dst}")
    print(f"  ANTES    : {_cobertura(dst)}")

    bak = _backup(dst)
    if bak:
        print(f"  backup   : {bak.name}")

    if args.source == "snapshot":
        src = Path(args.snapshot) if args.snapshot else (
            _AUDIT / cfg["snapshot"] if cfg["snapshot"] else None)
        if src is None or not src.exists():
            print(f"⚠️  No hay snapshot para '{args.surface}'"
                  f"{f' en {src}' if src else ''} — usá --source labeled o pasá --snapshot.")
            return 1
        shutil.copy2(src, dst)
        print(f"  copiado  : {src.name}")
    else:
        if not _desde_labeled(args.surface, dst):
            return 1

    print(f"  DESPUÉS  : {_cobertura(dst)}")

    if args.save_snapshot:
        snap = _AUDIT / f"{dst.stem}_snapshot_{date.today():%Y%m%d}.npz"
        shutil.copy2(dst, snap)
        print(f"  snapshot : audit/{snap.name}  (baseline versionado)")

    print("\nVerificá con:  python tools/measure_badge_lib.py --against-labeled "
          f"--surface {args.surface}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

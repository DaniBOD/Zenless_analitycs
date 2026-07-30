"""Genera la librería de referencia de W-Engines para el matcher de identidad.

`AvatarMatcher.from_folders` lee `*.png` y los íconos oficiales son `.webp` de 400×400 con
alfa. Esta herramienta los aplana sobre un fondo oscuro —el mismo tono de la tarjeta del tile
in-game— y los deja en `app/resources/engine_refs/`, replicando el precedente de
`app/resources/avatar_refs/` para los agentes.

Idempotente y read-only respecto de la DB. Se vuelve a correr cuando entran íconos nuevos.

Uso:
    .venv\\Scripts\\python tools\\build_engine_refs.py
    .venv\\Scripts\\python tools\\build_engine_refs.py --only 29    # solo los rango B
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.asset_resolver import ENGINES_DIR  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "resources" / "engine_refs"

# Gris del fondo de la tarjeta del tile. Medido sobre los tiles de los grids: la tarjeta es un
# azul muy oscuro casi neutro. Aplanar contra esto (y no contra blanco o transparente) evita
# que el borde del ítem quede con un halo que el descriptor lea como color propio.
_BG = 40

# Lado al que se guardan las referencias. El descriptor reescala a 64×64 de todos modos, así
# que guardar los 400×400 originales es 8,5 MB de puro desperdicio en el repo; 128 deja margen
# de sobra y baja a ~400 KB. Verificado: el resultado del matcher no cambia.
_REF_SIDE = 128


def flatten(path: Path) -> np.ndarray | None:
    """Carga un .webp RGBA y lo aplana sobre el fondo oscuro. None si no se puede leer."""
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 2:
        return cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:
        a = im[:, :, 3:4].astype(np.float32) / 255.0
        return (im[:, :, :3].astype(np.float32) * a + (1.0 - a) * _BG).astype(np.uint8)
    return im[:, :, :3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None,
                    help="subcadena que debe estar en el nombre del archivo (p.ej. '29')")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    src = Path(ENGINES_DIR)
    if not src.is_dir():
        print(f"[refs] no encuentro {src}")
        return 1

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)

    # Solo los archivos con el nombre EN original (`W-Engine_*`). Los slugs en español son
    # copias del mismo arte: meterlos duplicaría cada referencia y arruinaría el margen de
    # abstención, que se calcula justamente contra el segundo mejor.
    files = sorted(p for p in src.glob("W-Engine_*.webp")
                   if args.only is None or args.only in p.name)
    if not files:
        print(f"[refs] no hay archivos que matcheen en {src}")
        return 1

    n = 0
    for p in files:
        img = flatten(p)
        if img is None:
            print(f"  !! ilegible: {p.name}")
            continue
        stem = p.stem[len("W-Engine_"):]
        img = cv2.resize(img, (_REF_SIDE, _REF_SIDE), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(dest / f"{stem}.png"), img)
        n += 1

    print(f"[refs] {n} referencias escritas en {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

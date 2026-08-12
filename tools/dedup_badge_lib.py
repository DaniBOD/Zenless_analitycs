"""Colapsa las referencias CLONADAS de una librería de badges.

Contexto (medido 2026-08-11, spec `Documentacion/Dev_IA/2026-08-11_SPEC_Dedup_Cosecha_Badges.md`):

    row     365 refs ->  62 distintas (17%)  ·  40 de 50 PJs con UNA sola imagen
    detail  193 refs ->  85 distintas (44%)  ·  22 de 50
    grid    486 refs -> 392 distintas (81%)  ·   6 de 56

La cosecha del flujo de discos llama a `learn` una vez por cada disco del PJ, pero el avatar del
panel de detalle (y el de la barra superior) NO cambia con el disco seleccionado: seis discos, seis
copias del mismo recorte. Una copia no agrega discriminación —la distancia de clase es un `min`—
pero sí gasta una de las 10 ranuras, y cuando se llenan el desalojo es FIFO: entran clones, se van
las refs diversas.

`BadgeSurface.learn` ya no admite clones nuevos. Esta herramienta limpia los que quedaron.

Uso:
    python tools/dedup_badge_lib.py --dry-run                  # las tres, solo reporta
    python tools/dedup_badge_lib.py --surface detail           # limpia una
    python tools/dedup_badge_lib.py --save-snapshot            # limpia y versiona el baseline
    python tools/dedup_badge_lib.py --npz <ruta>               # sobre un archivo suelto

Después:
    python tools/measure_badge_lib.py <ruta.npz>

    OJO: el leave-one-out VA A BAJAR (en `detail`, ~91% -> ~42%). No es una regresión: con clones
    adentro, sacar una ref dejaba a su gemela idéntica matcheando a 0.000, así que medía "¿quedó
    una copia mía?" en vez de discriminación. El indicador de salud es refs DISTINTAS.
"""
from __future__ import annotations

import argparse
import collections
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.agent_identifier import _default_library_path
from app.core.avatar_descriptor import AvatarDescriptor, descriptor_distance
from app.core.badge_surface import _CLON_MAX_DIST

_AUDIT = ROOT / "audit"


def _hoy() -> str:
    """Fecha LOCAL para nombrar archivos: es la que el usuario reconoce al mirar `audit/`."""
    return f"{date.today():%Y%m%d}"    # noqa: DTZ011

# El .npz que carga la app para cada superficie. `preseed_badge_lib` tiene un mapa parecido pero
# solo con grid y row; acá hacen falta las tres.
_NPZ = {
    "row": "avatar_row_v2.npz",
    "grid": "avatar_badge_v2.npz",
    "detail": "avatar_detbadge_v2.npz",
}
_CAMPOS = ("hist", "ncc", "regions", "gray", "is_gray")


def _descriptores(d) -> list[AvatarDescriptor]:
    return [AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i], d["gray"][i],
                             bool(d["is_gray"][i])) for i in range(len(d["names"]))]


def _backup(path: Path) -> Path | None:
    """Copia de seguridad antes de pisar. Nunca se sobreescribe sin dejar rastro."""
    if not path.exists():
        return None
    dst = path.with_name(f"{path.stem}.backup_{_hoy()}_{os.getpid()}.npz")
    shutil.copy2(path, dst)
    return dst


def planificar(path: Path) -> tuple[list[int], dict[str, tuple[int, int]]]:
    """Qué índices SOBREVIVEN y el antes/después por clase. No toca el archivo.

    Se conserva la PRIMERA de cada grupo de clones: es la más vieja, y en una librería cuyo
    desalojo es FIFO la más vieja es la que más veces sobrevivió a una poda — no hay razón para
    preferir una copia recién llegada de la misma imagen.
    """
    d = np.load(str(path), allow_pickle=True)
    names = [str(n) for n in d["names"]]
    descs = _descriptores(d)
    por_clase: dict[str, list[int]] = collections.defaultdict(list)
    for i, n in enumerate(names):
        por_clase[n].append(i)

    keep: list[int] = []
    resumen: dict[str, tuple[int, int]] = {}
    for clase, idx in por_clase.items():
        sobreviven: list[int] = []
        for i in idx:
            q = descs[i]
            # `None` = la misma regla de métrica que usa el matcher (relativa, no por el flag).
            if not any(descriptor_distance(q, descs[j], None, None) <= _CLON_MAX_DIST
                       for j in sobreviven):
                sobreviven.append(i)
        keep += sobreviven
        resumen[clase] = (len(idx), len(sobreviven))
    return sorted(keep), resumen


def escribir(path: Path, keep: list[int]) -> None:
    d = np.load(str(path), allow_pickle=True)
    np.savez(str(path),
             names=np.array([str(d["names"][i]) for i in keep], dtype=object),
             **{c: (np.stack([d[c][i] for i in keep]) if c != "is_gray"
                    else np.array([d[c][i] for i in keep], dtype=bool)) for c in _CAMPOS})


def procesar(path: Path, dry_run: bool, save_snapshot: bool) -> int:
    if not path.exists():
        print(f"⚠️  no existe: {path}")
        return 1
    keep, resumen = planificar(path)
    total = sum(a for a, _ in resumen.values())
    quedan = len(keep)
    print(f"\n{path.name}")
    print(f"  clases {len(resumen)} · refs {total} → {quedan} distintas "
          f"({100 * quedan / max(1, total):.0f}%)")
    colapsadas = {c: v for c, v in sorted(resumen.items()) if v[0] != v[1]}
    for clase, (antes, desp) in colapsadas.items():
        print(f"    {clase:<20} {antes} → {desp}")
    if not colapsadas:
        print("    (sin clones)")
    if dry_run:
        print("  --dry-run: no se escribió nada")
        return 0

    bak = _backup(path)
    if bak:
        print(f"  backup   : {bak.name}")
    escribir(path, keep)
    # Verificación dura: ninguna clase puede desaparecer. Perder una es peor que tener clones.
    despues = collections.Counter(str(x) for x in np.load(str(path), allow_pickle=True)["names"])
    faltan = set(resumen) - set(despues)
    if faltan:
        print(f"  ⚠️  ATENCIÓN: se perdieron clases: {sorted(faltan)}")
        return 1
    print(f"  escrito  : {sum(despues.values())} refs · {len(despues)} clases")

    if save_snapshot:
        snap = _AUDIT / f"{path.stem}_snapshot_{_hoy()}_dedup.npz"
        shutil.copy2(path, snap)
        print(f"  snapshot : audit/{snap.name}  (baseline versionado)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surface", choices=sorted(_NPZ), action="append",
                    help="superficie a limpiar (repetible). Por defecto: las tres.")
    ap.add_argument("--npz", help="limpiar un archivo suelto en vez de las librerías del runtime")
    ap.add_argument("--dry-run", action="store_true", help="solo reporta, no escribe")
    ap.add_argument("--save-snapshot", action="store_true",
                    help="copia el resultado a audit/ como baseline versionado")
    args = ap.parse_args()

    if args.npz:
        return procesar(Path(args.npz), args.dry_run, args.save_snapshot)

    base = _default_library_path()
    rc = 0
    for surface in (args.surface or sorted(_NPZ)):
        rc |= procesar(base.with_name(_NPZ[surface]), args.dry_run, args.save_snapshot)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

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
from app.core.agent_identifier import _BASELINES, _default_library_path  # noqa: E402
from app.core.detector import crop_grid_selected_badge, crop_selected_avatar  # noqa: E402

_LABELED = ROOT / "audit" / "labeled_badges"
_AUDIT = ROOT / "audit"

# Por superficie: nombre del .npz que carga la app y qué recortes etiquetados le corresponden.
# El BASELINE no se declara acá: es `agent_identifier._BASELINES`, el mismo que repone
# `BadgeSurface.load`. Esta tabla tenía su propia lista y para el 2026-08-19 discrepaban —
# apuntaba al snapshot de JUNIO, así que `--source snapshot --surface grid` reinstalaba una
# librería sin Aria y sin el dedup, distinta de la que la app repone sola. Dos autoridades
# para "cuál es el baseline" es una de más.
_SURFACES = {
    "grid": {
        "npz": "avatar_badge_v2.npz",
        "globs": ("S17_*.png",),
        "crop": crop_grid_selected_badge,
    },
    "row": {
        "npz": "avatar_row_v2.npz",
        "globs": ("S8_*.png", "S18_*.png"),
        "crop": crop_selected_avatar,
        # SOLO harvest: los S8/S18 pre-cortados de `labeled_badges` son 37×37 circulares y el
        # `crop_fn` de hoy da 52×52 cuadrados sobre una captura del mismo tamaño — otro encuadre.
        # Medido sobre frames reales: con los pre-cortados, Nangong Yu sale a 0.833 y Remielle Dan
        # (sin refs) sale como **Vivian a 0.550**; recortando los frames del harvest con la función
        # de la app, Nangong Yu sube a 0.958 y Remielle ABSTIENE. Mezclarlos metería un segundo
        # dominio a competir, que es exactamente lo que rompió el grid.
        "fuentes": ("harvest",),
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


def _canonizador():
    """Resolutor de label → nombre del roster, con reparación de mojibake.

    Canonizar acá NO es opcional: `BadgeSurface.learn` lo hace siempre desde la lección del
    2026-06-18 (una librería con claves no canónicas la vacía `prune_to_roster` al arrancar), y
    esta herramienta escribe la misma librería por otra puerta. Las fuentes traen labels crudos:
    carpetas con acentos, claves en minúscula del harvest (`anton`, `jufufu`) y alguna
    doble-codificada (`n.Âº11`).
    """
    from app.core.agent_identifier import AgentIdentifier
    from app.db.connection import get_connection
    roster = {r[0] for r in get_connection().execute("select nombre from agents")}
    # prune=False explícito: acá solo se usa el resolutor de nombres, no queremos que construir
    # el identificador toque librería alguna. (Con autoload=False la poda ya no corre, pero la
    # convención es decirlo — ver test_las_herramientas_de_tools_deciden_prune_explicitamente.)
    ai = AgentIdentifier(autoload=False, roster=roster, prune=False)
    return ai.resolve_to_roster


def _fuentes_harvest(surface: str) -> dict[str, list[str]]:
    """`audit/harvest/<pj>__<S8|S18|S17>__<n>.png`, etiquetados por el flujo-ancla.

    OJO: son **frames COMPLETOS** (1440×2560), no recortes — a diferencia de `labeled_badges`,
    que ya viene cortado. Hay que pasarles el `crop_fn`; meterlos enteros como refs es basura
    con nombre de PJ (me pasó al escribir esto).

    Que sean frames enteros es además una ventaja: recortarlos con la MISMA función que usa la
    app en vivo garantiza el like-with-like que pide la Fase 5R, cosa que los recortes ya
    guardados no garantizan (los S8 de `labeled_badges` son 37×37 circulares y el `crop_fn` de
    hoy da 52×52 cuadrados sobre una captura del mismo tamaño).
    """
    pats = tuple(g.split("_")[0] for g in _SURFACES[surface]["globs"])   # S8, S18 / S17
    out: dict[str, list[str]] = collections.defaultdict(list)
    for p in sorted((_AUDIT / "harvest").glob("*__*__*.png")):
        partes = p.name.split("__")
        if len(partes) >= 2 and partes[1] in pats:
            out[partes[0]].append(str(p))
    return out


def _desde_labeled(surface: str, dst: Path) -> int:
    """Reconstruye la superficie desde las fuentes etiquetadas que le correspondan.

    Cada fuente tiene su trato: `labeled_badges` ya viene recortado; `audit/harvest` son frames
    enteros que hay que cortar con el `crop_fn` de la app. Qué fuentes usa cada superficie se
    declara en `_SURFACES[...]["fuentes"]`, porque mezclar encuadres distintos dentro de una
    misma librería es el modo de falla que rompió el grid.
    """
    resolver = _canonizador()
    crop_fn = _SURFACES[surface]["crop"]
    usa = _SURFACES[surface].get("fuentes", ("labeled", "harvest"))
    # (clave, ruta, ¿hay que recortar?)
    fuentes: list[tuple[str, str, bool]] = []
    if "labeled" in usa and _LABELED.is_dir():
        for pjdir in sorted(glob.glob(str(_LABELED / "*"))):
            for pat in _SURFACES[surface]["globs"]:
                fuentes += [(os.path.basename(pjdir), p, False)
                            for p in sorted(glob.glob(os.path.join(pjdir, pat)))]
    if "harvest" in usa:
        for clave, frames in _fuentes_harvest(surface).items():
            fuentes += [(clave, p, True) for p in frames]
    if not fuentes:
        print("No hay fuentes etiquetadas."); return 0

    por_pj: dict[str, list[tuple[str, bool]]] = collections.defaultdict(list)
    sin_resolver = set()
    for clave, ruta, recortar in fuentes:
        canon = resolver(clave)
        if canon is None:
            sin_resolver.add(clave)         # se DECLARA: una ref muda es una ref perdida
            continue
        por_pj[canon].append((ruta, recortar))

    m = AvatarMatcher()
    n_ref = n_sin_crop = 0
    for canon, items in sorted(por_pj.items()):
        for ruta, recortar in items:
            img = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            if recortar:
                img = crop_fn(img)
                if img is None:
                    n_sin_crop += 1
                    continue
            if m.add_reference(canon, img, max_per_name=_MAX_PER_NAME):
                n_ref += 1
    if sin_resolver:
        print(f"⚠️  labels que no resuelven al roster (se descartan): {sorted(sin_resolver)}")
    if n_sin_crop:
        print(f"   ({n_sin_crop} frames del harvest no dieron recorte)")
    if not n_ref:
        print("No se armó ninguna ref."); return 0
    m.save(dst)
    print(f"Reconstruidas {n_ref} refs de {len(m._refs)} PJs.")
    return n_ref


def _desde_frame(surface: str, dst: Path, frame_path: Path, label: str) -> int:
    """Agrega refs de UN PJ desde screenshots completos, recortando como lo hace la app.

    La vía para tapar el hueco de un PJ nuevo sin cosechar en vivo: un patch trae PJs que
    ninguna librería tiene, y hasta que se cosechen el matcher los nombra como el vecino más
    parecido. Pasó con Remielle Dan, que salía como Vivian en toda su página de equipamiento.
    """
    resolver = _canonizador()
    canon = resolver(label)
    if canon is None:
        print(f"'{label}' no resuelve al roster."); return 0
    frames = sorted(frame_path.glob("*.png")) if frame_path.is_dir() else [frame_path]
    m = AvatarMatcher()
    m.load_merge(dst)                       # se SUMA a lo que ya hay, no lo reemplaza
    antes = len(m._refs.get(canon, []))
    for f in frames:
        img = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        crop = _SURFACES[surface]["crop"](img)
        if crop is None:
            print(f"  {f.name}: el recorte no salió"); continue
        if m.add_reference(canon, crop, max_per_name=_MAX_PER_NAME):
            print(f"  {f.name}: ref agregada a '{canon}'")
    n = len(m._refs.get(canon, [])) - antes
    if n:
        m.save(dst)
    print(f"'{canon}': {antes} -> {antes + n} refs")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surface", choices=sorted(_SURFACES), default="grid")
    ap.add_argument("--source", choices=("snapshot", "labeled", "frame"), default="labeled")
    ap.add_argument("--frame", default=None, help="PNG (o carpeta) de pantallas completas")
    ap.add_argument("--label", default=None, help="PJ al que pertenecen esas pantallas")
    ap.add_argument("--snapshot", default=None,
                    help="ruta del .npz a copiar (default: el baseline de app/resources/)")
    ap.add_argument("--save-snapshot", action="store_true",
                    help="además, archivar el resultado con fecha en audit/ (historia). Para que "
                         "la app lo REPONGA hay que copiarlo a app/resources/badge_baselines/ y "
                         "actualizar _BASELINES: promover es una decisión, no un efecto de costado")
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
        src = Path(args.snapshot) if args.snapshot else _BASELINES.get(args.surface)
        if src is None or not src.exists():
            print(f"⚠️  No hay baseline para '{args.surface}'"
                  f"{f' en {src}' if src else ''} — usá --source labeled o pasá --snapshot.")
            return 1
        shutil.copy2(src, dst)
        print(f"  copiado  : {src.name}")
    elif args.source == "frame":
        if not args.frame or not args.label:
            print("--source frame necesita --frame y --label."); return 1
        if not _desde_frame(args.surface, dst, Path(args.frame), args.label):
            return 1
    else:
        if not _desde_labeled(args.surface, dst):
            return 1

    print(f"  DESPUÉS  : {_cobertura(dst)}")

    if args.save_snapshot:
        snap = _AUDIT / f"{dst.stem}_snapshot_{date.today():%Y%m%d}.npz"
        shutil.copy2(dst, snap)
        print(f"  archivado: audit/{snap.name}")
        print("  ojo: esto NO cambia lo que la app repone. Para promoverlo, copiarlo a "
              "app/resources/badge_baselines/ y actualizar _BASELINES en agent_identifier.py.")

    print("\nVerificá con:  python tools/measure_badge_lib.py --against-labeled "
          f"--surface {args.surface}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

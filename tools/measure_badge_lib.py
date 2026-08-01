"""Fase 5R.C.5 — Medición GO/NO-GO de la librería de badges COMPLETA (47/47).

Leave-one-out directo sobre los descriptores del .npz cosechado (no requiere
re-extraer imágenes): por cada badge, se lo saca de las refs de su PJ y se
matchea contra el resto (otras refs del mismo PJ + -ico semilla + reject). Mide
discriminación inter-PJ con las refs ricas. Reporta top1/abstención/wrong global,
PJs que fallan, y matriz de confusión (look-alikes).

NOTA: esto mide sobre badges COSECHADOS (limpios, del flujo-ancla). Es optimista
respecto al gap "dueño incierto" en vivo (frames a mitad de scroll). El número
real-real sale del QA en vivo contra el equip_map. Esto da el techo de discriminación.

`--against-labeled` mide otra cosa, y es la que detectó el colapso del 2026-07-31: matchea los
badges REALES etiquetados de `audit/labeled_badges/<PJ>/` contra la librería que la app carga de
verdad. El leave-one-out no puede ver este fallo — mide un .npz contra sí mismo, así que una
librería vacía de cosecha (solo semilla `-ico`) le da bien. Contra los etiquetados dio **4.3%
top-1 y 14.6% wrong**, con Cissia ganando 14 discos ajenos: el modo de falla es que la clase con
la única ref del dominio correcto se lleva todo, porque la distancia de clase es un `min` sin
normalizar. Restaurado el snapshot: 93.3% / 2.4%.

Uso:
    python tools/measure_badge_lib.py                       # leave-one-out del snapshot del repo
    python tools/measure_badge_lib.py <ruta.npz>            # leave-one-out de otro .npz
    python tools/measure_badge_lib.py --against-labeled     # etiquetados vs librería RUNTIME
    python tools/measure_badge_lib.py --against-labeled --lib <ruta.npz>
    python tools/measure_badge_lib.py --against-labeled --surface row
"""
from __future__ import annotations
import argparse
import glob
import os
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import (  # noqa: E402
    AvatarMatcher, AvatarDescriptor, build_name_map,
)
from app.core.stats_vocab import _norm_key  # noqa: E402

_DEFAULT_NPZ = ROOT / "audit" / "avatar_badge_v2_snapshot_20260612_full47.npz"
_LABELED = ROOT / "audit" / "labeled_badges"
# Qué recortes etiquetados corresponden a cada superficie. El grid vive en S17 (columna de la
# grilla); el row, en las filas de S8/S18. Mezclarlos rompe la regla like-with-like.
_SURFACE_GLOBS = {"grid": ("S17_*.png",), "row": ("S8_*.png", "S18_*.png")}
_SURFACE_LIB = {"grid": "avatar_badge_v2.npz", "row": "avatar_row_v2.npz"}


def _demojibake(s: str) -> str:
    """Los nombres de carpeta se escribieron con UTF-8 leído como latin-1 ('n.Âº11')."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _seeded_matcher():
    """Matcher con la semilla `-ico` + rejects, igual que arranca la app."""
    from app.db.connection import get_connection
    con = get_connection(); roster = [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]; con.close()
    stems = [os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    nm = build_name_map(stems, roster)
    return AvatarMatcher.from_folders(ROOT / "app/resources/avatar_refs",
                                      ROOT / "app/resources/avatar_reject", name_map=nm)


def _load_into(m, npz_path: Path) -> int:
    d = np.load(str(npz_path), allow_pickle=True)
    for i, n in enumerate(d["names"]):
        desc = AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                d["gray"][i], bool(d["is_gray"][i]))
        m.add_reference(str(n), desc, max_per_name=99)   # todas, para medir
    return len(d["names"])


def against_labeled(lib_path: Path, surface: str, guard: float = 0.80) -> int:
    """Los badges REALES etiquetados contra la librería que la app carga.

    Es la medición que le falta al leave-one-out: acá el query viene de una imagen in-game y la
    librería es la del runtime, así que expone el caso 'la librería perdió su cosecha y quedó
    solo el arte -ico' — que al leave-one-out le da perfecto.
    """
    if not _LABELED.is_dir():
        print(f"No existe {_LABELED} (corré extract_harvested primero)."); return 1
    m = _seeded_matcher()
    n_lib = _load_into(m, lib_path) if lib_path.exists() else 0
    if not n_lib:
        print(f"⚠️  {lib_path} no existe o está vacía — se mide SOLO con la semilla -ico.")

    qs = []
    for folder in sorted(_LABELED.iterdir()):
        if not folder.is_dir():
            continue
        gt = _demojibake(folder.name)
        for pat in _SURFACE_GLOBS[surface]:
            for p in sorted(folder.glob(pat)):
                img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    qs.append((gt, img))
    if not qs:
        print(f"No hay recortes etiquetados para la superficie '{surface}'."); return 1

    ok = ab = wr = 0
    imanes = defaultdict(int); per_pj = defaultdict(lambda: [0, 0, 0])
    for gt, img in qs:
        r = m.match(img)
        if r.name is None or r.conf < guard:
            ab += 1; per_pj[gt][1] += 1
        elif _norm_key(r.name) == _norm_key(gt):
            ok += 1; per_pj[gt][0] += 1
        else:
            wr += 1; per_pj[gt][2] += 1; imanes[r.name] += 1

    t = len(qs)
    print(f"\n=== ETIQUETADOS vs librería '{surface}' (guard conf>={guard}) ===")
    print(f"  librería: {lib_path}")
    print(f"  refs: {sum(len(v) for v in m._refs.values())} en {len(m._refs)} clases "
          f"({n_lib} del .npz + semilla -ico)")
    print(f"  queries: {t}")
    print(f"  TOP-1: {ok}/{t} = {ok/t:.1%}  |  ABSTENCIÓN: {ab/t:.1%}  |  WRONG: {wr}/{t} = {wr/t:.1%}")
    if imanes:
        print("  IMANES (a quién van los wrong):",
              "  ".join(f"{k} x{v}" for k, v in sorted(imanes.items(), key=lambda kv: -kv[1])))
    malos = {pj: v for pj, v in sorted(per_pj.items()) if v[1] or v[2]}
    if malos:
        print("  PJs con abstención o wrong:",
              "  ".join(f"{pj}(ok={v[0]},ab={v[1]},wr={v[2]})" for pj, v in malos.items()))
    return 0


def leave_one_out(npz_path: Path) -> int:
    if not npz_path.exists():
        print(f"No existe el npz: {npz_path}")
        return 1

    m = _seeded_matcher()

    # Reconstruir descriptores del npz y agruparlos por PJ.
    d = np.load(str(npz_path), allow_pickle=True)
    names = [str(x) for x in d["names"]]
    by_pj: dict[str, list] = defaultdict(list)
    for i, nm_i in enumerate(names):
        desc = AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                d["gray"][i], bool(d["is_gray"][i]))
        by_pj[nm_i].append(desc)
        m.add_reference(nm_i, desc, max_per_name=99)   # cargar TODAS para la medición

    n = sum(len(v) for v in by_pj.values())
    print(f"npz: {npz_path.name} | PJs: {len(by_pj)} | refs cosechadas: {n} "
          f"| refs totales matcher (con -ico): {len(m.names)}\n")

    # Recolectar (gt, pred, conf, rejected) por badge con leave-one-out.
    results = []   # (pj, pred_name|None, conf)
    for pj, descs in by_pj.items():
        lst = m._refs.get(pj)
        if lst is None:
            continue
        for desc in descs:
            idx = next((j for j, x in enumerate(lst) if x is desc), None)
            held = lst.pop(idx) if idx is not None else None
            r = m.match(desc)
            if held is not None:
                lst.insert(idx, held)
            results.append((pj, r.name, r.conf))

    def report(guard: float, title: str):
        """Acepta el match solo si conf >= guard (None o conf bajo → abstención)."""
        ok = ab = wr = 0
        conf = defaultdict(int)
        per_pj = defaultdict(lambda: [0, 0, 0])
        for pj, pred, c in results:
            if pred is None or c < guard:
                ab += 1; per_pj[pj][1] += 1
            elif _norm_key(pred) == _norm_key(pj):
                ok += 1; per_pj[pj][0] += 1
            else:
                wr += 1; per_pj[pj][2] += 1; conf[(pj, pred)] += 1
        t = max(1, ok + ab + wr)
        print(f"\n=== {title} (guard conf>={guard}) ===")
        print(f"  TOP-1: {ok}/{t} = {ok/t:.1%}  |  ABSTENCIÓN: {ab}/{t} = {ab/t:.1%}  "
              f"|  WRONG: {wr}/{t} = {wr/t:.1%}")
        if conf:
            print("  Wrongs:", "  ".join(f"{a}->{b} x{c}" for (a, b), c in
                                          sorted(conf.items(), key=lambda kv: -kv[1])))
        return per_pj

    report(0.0, "Gate base match() — sin guard extra")
    per_pj = report(0.80, "GUARD S17 LIVE (s17_match _S17_GUARD_DEFAULT)")

    fails = {pj: v for pj, v in per_pj.items() if v[2]}   # solo wrongs bajo guard live
    # Sin emoji: la consola de Windows es cp1252 y un '✅' acá tiraba UnicodeEncodeError
    # justo en el caso bueno (0 wrongs), que es el único que llega a imprimirlo.
    print("\nPJs con WRONG bajo guard 0.80 (RNF-02 - foco):",
          ", ".join(f"{pj}(w={v[2]})" for pj, v in fails.items()) or "NINGUNO")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("npz", nargs="?", default=None, help="npz para el leave-one-out")
    ap.add_argument("--against-labeled", action="store_true",
                    help="mide los etiquetados de audit/labeled_badges contra la librería runtime")
    ap.add_argument("--surface", choices=sorted(_SURFACE_GLOBS), default="grid")
    ap.add_argument("--lib", default=None, help="librería a medir (default: la del runtime)")
    ap.add_argument("--guard", type=float, default=0.80)
    args = ap.parse_args()

    if args.against_labeled:
        from app.core.agent_identifier import _default_library_path
        lib = Path(args.lib) if args.lib else _default_library_path().with_name(
            _SURFACE_LIB[args.surface])
        return against_labeled(lib, args.surface, args.guard)
    return leave_one_out(Path(args.npz) if args.npz else _DEFAULT_NPZ)


if __name__ == "__main__":
    raise SystemExit(main())

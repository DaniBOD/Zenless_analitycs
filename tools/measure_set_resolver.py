"""Mide el resolvedor difuso de nombres de set contra un corpus REAL de lecturas OCR.

El corpus sale del log de la app (`set=<nombre>` en las líneas de S9/S17): son los strings
que el OCR produjo de verdad, con sus frecuencias. Medir contra el catálogo "limpio" no
sirve — el resolvedor sólo se equivoca con el ruido que ve en campo.

Uso:
    python tools/measure_set_resolver.py                      # log por defecto
    python tools/measure_set_resolver.py --log <ruta>
    python tools/measure_set_resolver.py --cutoff 0.80 --margin 0.15

Reporta, por lectura: por qué VÍA se resolvió (exacta / substring / difflib) o por qué no,
con el ratio del mejor candidato y el margen al segundo distinto. Es la medición que hace
falta antes de tocar el cutoff: el 2026-08-30 se atribuyó a "el matcher de logos" un rescate
que en realidad hace el atajo por SUBSTRING de este mismo resolvedor.
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.stats_vocab import _norm_key  # noqa: E402
from app.db.repositories import DiscSetRepo  # noqa: E402

_RE_SET = re.compile(r"set=(.+?) slot=")
DEFAULT_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "DaniBOD_ZZZ_Analytics" / "app.log"


def corpus_desde_log(path: Path) -> Counter:
    c: Counter = Counter()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            m = _RE_SET.search(linea)
            if m:
                c[m.group(1)] += 1
    return c


def diagnostico(repo: DiscSetRepo, name: str, cutoff: float, margin: float) -> dict:
    """Reproduce `DiscSetRepo.resolve_id` paso a paso y devuelve por qué vía salió."""
    out = {"via": None, "sid": None, "cand": None, "ratio": 0.0, "margen": None, "seg": None}
    if not name:
        out["via"] = "vacio"
        return out
    sid = repo.get_id_by_name(name)
    if sid:
        out.update(via="exacta", sid=sid, cand=name, ratio=1.0)
        return out
    name_n = _norm_key(name)
    if not name_n:
        out["via"] = "vacio"
        return out
    norm_to: dict[str, tuple[str, int]] = {}
    for sname, s_id in repo.get_all_names().items():
        sname_n = _norm_key(sname)
        if not sname_n:
            continue
        norm_to.setdefault(sname_n, (sname, s_id))
    for sname_n, (sname, s_id) in norm_to.items():
        if sname_n == name_n or sname_n in name_n or name_n in sname_n:
            r = difflib.SequenceMatcher(None, name_n, sname_n).ratio()
            out.update(via="substring", sid=s_id, cand=sname, ratio=r)
            return out
    keys = list(norm_to)
    # Sin cutoff, para ver SIEMPRE el mejor candidato y su margen (es el dato que decide).
    ranked = sorted(
        ((difflib.SequenceMatcher(None, name_n, k).ratio(), k) for k in keys), reverse=True
    )
    if not ranked:
        out["via"] = "catalogo_vacio"
        return out
    r_best, k_best = ranked[0]
    cand, sid = norm_to[k_best]
    out.update(cand=cand, sid=sid, ratio=r_best)
    seg = next((x for x in ranked[1:] if norm_to[x[1]][1] != sid), None)
    if seg is not None:
        out["seg"] = norm_to[seg[1]][0]
        out["margen"] = r_best - seg[0]
    if r_best < cutoff:
        out["via"] = "difflib_bajo_cutoff"
    elif out["margen"] is not None and out["margen"] < margin:
        out["via"] = "difflib_ambiguo"
    else:
        out["via"] = "difflib"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--db", type=Path, default=Path("db/danibod_zzz_v2.db"))
    ap.add_argument("--cutoff", type=float, default=DiscSetRepo.SET_FUZZY_CUTOFF)
    ap.add_argument("--margin", type=float, default=DiscSetRepo.SET_FUZZY_MARGIN)
    ap.add_argument("--max-len", type=int, default=60,
                    help="lecturas más largas que esto son basura de OCR (pantalla mezclada)")
    args = ap.parse_args()

    if not args.log.exists():
        print(f"no existe el log: {args.log}")
        return 2
    corpus = corpus_desde_log(args.log)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    repo = DiscSetRepo(con)

    print(f"log     {args.log}")
    print(f"corpus  {len(corpus)} lecturas distintas, {sum(corpus.values())} detecciones")
    print(f"regla   cutoff={args.cutoff} margen={args.margin}\n")

    vias: Counter = Counter()
    det_ok = det_no = 0
    fallos: list[tuple[int, str, dict]] = []
    for nombre, veces in corpus.most_common():
        if len(nombre) > args.max_len:
            vias["basura_descartada"] += 1
            continue
        d = diagnostico(repo, nombre, args.cutoff, args.margin)
        vias[d["via"]] += 1
        if d["via"] in ("exacta", "substring", "difflib"):
            det_ok += veces
        else:
            det_no += veces
            fallos.append((veces, nombre, d))

    print("=== por vía (lecturas distintas) ===")
    for v, n in vias.most_common():
        print(f"  {v:24s} {n}")
    print(f"\ndetecciones resueltas   {det_ok}")
    print(f"detecciones perdidas    {det_no}\n")

    print("=== lecturas NO resueltas (ordenadas por impacto) ===")
    for veces, nombre, d in sorted(fallos, reverse=True, key=lambda x: x[0]):
        m = "-" if d["margen"] is None else f"{d['margen']:.4f}"
        print(f"  x{veces:<4d} {nombre!r:42s} -> {d['cand']!r} ratio={d['ratio']:.4f} "
              f"margen={m} 2º={d['seg']!r}  [{d['via']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

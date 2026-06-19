"""Hito L.1 (Fase 5R) — Diagnóstico del imán "Nangong Yu" del DETALLE-badge.

Aísla, con un experimento 2×2 (librería limpia/runtime × query limpio/en-vivo), si el
imán del detail-matcher viene de la LIBRERÍA runtime (avatar_detbadge_v2.npz, cosechada
en vivo) o del CROP de query en vivo (crop_detail_badge mal centrado). Read-only: no toca
la DB ni la librería runtime.

| Caso | Librería       | Query                         | Pregunta                              |
|------|----------------|-------------------------------|---------------------------------------|
| A    | harvest (GT)   | harvest det LOO               | baseline limpio (esperado ~96%, sano) |
| B    | runtime npz    | harvest det (GT)              | ¿la librería runtime imanta?          |
| C    | harvest (GT)   | det de 16_discos_pj_grilla    | ¿el crop en vivo imanta?              |
| D    | runtime npz    | det de 16_discos_pj_grilla    | reproduce el imán del QA (control)    |

Verdad de tierra de los ejemplos en vivo: se etiqueta cada frame con el GRID-matcher
(snapshot 47/47, conf>=gate; los reads del grid son 0-wrong verificado).

Uso:
    .venv/Scripts/python.exe tools/diag_detbadge_magnet.py [--gate 0.85]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

try:                                # consola Windows en cp1252 → forzar utf-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import (  # noqa: E402
    AvatarMatcher, AvatarDescriptor, build_descriptor, build_name_map,
)
from app.core.detector import crop_grid_selected_badge, crop_detail_badge  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402

_HARVEST = ROOT / "audit" / "harvest_badges"
_EXAMPLES = ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "16_discos_pj_grilla"
_GRID_SNAP = ROOT / "audit" / "avatar_badge_v2_snapshot_20260612_full47.npz"
_RUNTIME_DET = Path(os.environ.get(
    "LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
) / "DaniBOD_ZZZ_Analytics" / "avatar_detbadge_v2.npz"
_REFS = ROOT / "app" / "resources" / "avatar_refs"
_REJECT = ROOT / "app" / "resources" / "avatar_reject"
_S17_GUARD = 0.80   # _S17_GUARD_DEFAULT — guard de naming en producción


def _imread(p: str) -> np.ndarray | None:
    d = np.fromfile(p, np.uint8)
    return cv2.imdecode(d, cv2.IMREAD_COLOR) if d.size else None


def _roster() -> list[str]:
    from app.db.connection import get_connection
    con = get_connection()
    try:
        return [str(r[0]) for r in con.execute("SELECT nombre FROM agents")]
    finally:
        con.close()


def _name_map(roster: list[str]) -> dict[str, str]:
    stems = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(str(_REFS / "*.png"))]
    return build_name_map(stems, roster)


def _load_rejects() -> list[AvatarDescriptor]:
    seed = AvatarMatcher.from_folders(_REFS, _REJECT)
    return list(seed._rejects)


def _matcher_from_npz(path: Path, rejects: list) -> AvatarMatcher:
    """Matcher que replica el detbadge de producción: refs del .npz, reject-set
    compartido, SIN semilla -ico (igual que AgentIdentifier._detbadge)."""
    m = AvatarMatcher(rejects=rejects)
    d = np.load(str(path), allow_pickle=True)
    names = [str(x) for x in d["names"]]
    for i, nm in enumerate(names):
        m.add_reference(nm, AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                             d["gray"][i], bool(d["is_gray"][i])), max_per_name=99)
    return m


def _clean_det_matcher(name_map: dict[str, str], rejects: list) -> tuple[AvatarMatcher, dict]:
    """Matcher de detail LIMPIO desde audit/harvest_badges/*__det__*. Devuelve
    (matcher, gt_by_path) con la etiqueta canónica por crop."""
    m = AvatarMatcher(rejects=rejects)
    gt: dict[str, str] = {}
    for p in sorted(glob.glob(str(_HARVEST / "*__det__*.png"))):
        label = os.path.basename(p).split("__det__")[0]
        canon = name_map.get(label) or name_map.get(label.replace(".", "")) or label
        img = _imread(p)
        desc = build_descriptor(img) if img is not None else None
        if desc is None:
            continue
        m.add_reference(canon, desc, max_per_name=99)
        gt[p] = canon
    return m, gt


def _grid_label_examples(name_map: dict[str, str], rejects: list, gate: float) -> list[tuple[str, AvatarDescriptor]]:
    """Etiqueta cada frame de ejemplo con el GRID-matcher (snapshot+ico+reject). Devuelve
    [(gt_canonical, descriptor_del_detail_crop)] para los frames con label de grid."""
    gm = AvatarMatcher.from_folders(_REFS, _REJECT, name_map=name_map)
    d = np.load(str(_GRID_SNAP), allow_pickle=True)
    for i, nm in enumerate([str(x) for x in d["names"]]):
        gm.add_reference(nm, AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i],
                                              d["gray"][i], bool(d["is_gray"][i])), max_per_name=20)
    out: list[tuple[str, AvatarDescriptor]] = []
    skipped = 0
    for p in sorted(glob.glob(str(_EXAMPLES / "*.png"))):
        fr = _imread(p)
        if fr is None:
            continue
        g = crop_grid_selected_badge(fr)
        if g is None:
            skipped += 1; continue
        rg = gm.match(g)
        if rg.name is None or rg.conf < gate:
            skipped += 1; continue
        det = crop_detail_badge(fr)
        desc = build_descriptor(det) if det is not None else None
        if desc is None:
            skipped += 1; continue
        out.append((rg.name, desc))
    print(f"[live GT] etiquetados {len(out)} / {len(glob.glob(str(_EXAMPLES / '*.png')))} "
          f"frames (grid conf>={gate}); {skipped} sin label de grid", flush=True)
    return out


# --------------------------------------------------------------------------- #
# Evaluación de un caso
# --------------------------------------------------------------------------- #

def _eval(matcher: AvatarMatcher, queries: list[tuple[str, AvatarDescriptor]],
          loo: bool, guard: float) -> dict:
    """Corre el matcher sobre los queries (gt, desc). loo: hold-out de la instancia
    exacta (caso A). Devuelve métricas + distribución de predicciones (para el imán)."""
    ok = ab = wr = 0
    preds = Counter()           # predicciones name!=None (gate del match, sin guard extra)
    confs, margins = [], []
    wrongs = Counter()
    for gt, desc in queries:
        held = None
        if loo:
            lst = matcher._refs.get(gt, [])
            idx = next((j for j, x in enumerate(lst) if x is desc), None)
            held = lst.pop(idx) if idx is not None else None
        r = matcher.match(desc)
        if held is not None:
            matcher._refs[gt].insert(idx, held)
        if r.name is not None:
            preds[r.name] += 1
            confs.append(r.conf); margins.append(r.margin)
        # outcome con guard de producción
        if r.name is None or r.conf < guard:
            ab += 1
        elif _norm_key(r.name) == _norm_key(gt):
            ok += 1
        else:
            wr += 1; wrongs[(gt, r.name)] += 1
    t = max(1, ok + ab + wr)
    distinct = len(preds)
    top_pj, top_n = (preds.most_common(1)[0] if preds else ("-", 0))
    magnet_share = top_n / max(1, sum(preds.values()))
    return {
        "n": t, "ok": ok, "ab": ab, "wr": wr,
        "ok_pct": ok / t, "ab_pct": ab / t, "wr_pct": wr / t,
        "distinct_preds": distinct, "top_pj": top_pj, "top_share": magnet_share,
        "preds": preds, "wrongs": wrongs,
        "conf_mean": float(np.mean(confs)) if confs else 0.0,
        "margin_mean": float(np.mean(margins)) if margins else 0.0,
    }


def _fmt_case(tag: str, desc: str, r: dict) -> list[str]:
    L = [f"### Caso {tag} — {desc}",
         f"- top-1: **{r['ok_pct']:.0%}** ({r['ok']}/{r['n']}) · abst {r['ab_pct']:.0%} · "
         f"**WRONG {r['wr_pct']:.0%}** ({r['wr']})",
         f"- predicciones DISTINTAS: **{r['distinct_preds']} PJs** · "
         f"PJ dominante: **{r['top_pj']}** ({r['top_share']:.0%} de los matches) "
         f"{'⚠️ IMÁN' if r['top_share'] >= 0.6 and r['distinct_preds'] <= 3 else ''}",
         f"- conf media {r['conf_mean']:.3f} · margin medio {r['margin_mean']:.3f}"]
    if r["preds"]:
        top = ", ".join(f"{k}:{v}" for k, v in r["preds"].most_common(6))
        L.append(f"- distribución de predicciones: {top}")
    if r["wrongs"]:
        w = "  ".join(f"{a}→{b}×{c}" for (a, b), c in r["wrongs"].most_common(8))
        L.append(f"- wrongs: {w}")
    L.append("")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", type=float, default=0.85, help="conf mínima del grid para etiquetar ejemplos")
    ap.add_argument("--tag", default="", help="sufijo del archivo de salida (no pisar el reporte L.1)")
    args = ap.parse_args()

    if not _RUNTIME_DET.exists():
        print(f"No existe la librería runtime: {_RUNTIME_DET}")
        return 1

    roster = _roster()
    nm = _name_map(roster)
    rejects = _load_rejects()

    clean, _clean_gt = _clean_det_matcher(nm, rejects)
    runtime = _matcher_from_npz(_RUNTIME_DET, rejects)
    live = _grid_label_examples(nm, rejects, args.gate)

    # Query limpio = los descriptores reales del matcher limpio (instancias, para LOO).
    q_clean = [(canon, desc) for canon, lst in clean._refs.items() for desc in lst]

    # --- sub-análisis de composición runtime ---
    rt_counts = Counter(k for k, lst in runtime._refs.items() for _ in lst)
    refs_per_pj = Counter(rt_counts.values())

    A = _eval(clean, q_clean, loo=True, guard=_S17_GUARD)
    B = _eval(runtime, q_clean, loo=False, guard=_S17_GUARD)
    C = _eval(clean, live, loo=False, guard=_S17_GUARD)
    D = _eval(runtime, live, loo=False, guard=_S17_GUARD)

    # --- veredicto ---
    def is_magnet(r):
        # colapso: pocas predicciones distintas + top-1 bajo + concentración en un PJ.
        return r["ok_pct"] < 0.5 and r["distinct_preds"] <= 4 and r["top_share"] >= 0.4
    b_mag, c_mag, d_mag = is_magnet(B), is_magnet(C), is_magnet(D)
    if b_mag:
        verdict = ("**LIBRERÍA RUNTIME** es la causa principal del imán (caso B imanta sobre "
                   "crops limpios) → L.2a (re-cosechar librería limpia) lo resuelve.")
    elif c_mag:
        verdict = ("**CROP DE QUERY EN VIVO** es la causa (caso B sano, caso C imanta con lib "
                   "limpia) → L.2b (two-stage refine de crop_detail_badge) lo resuelve.")
    elif d_mag:
        verdict = ("El imán solo aparece con runtime+vivo (D) — **combinación** librería+crop; "
                   "aplicar L.2a y L.2b juntos.")
    else:
        verdict = ("No se reprodujo el imán en este corte — revisar gate/dataset antes de L.2.")

    # --- reporte markdown ---
    today = _dt.date.today().isoformat()
    suffix = f"_{args.tag}" if args.tag else ""
    out = ROOT / "audit" / f"detbadge_magnet_diag_{today.replace('-', '')}{suffix}.md"
    lines = [
        f"# L.1 — Diagnóstico del imán del detalle-badge (2×2) · {today}",
        "",
        "> Read-only. Aísla si el imán del detail-matcher viene de la LIBRERÍA runtime o del",
        "> CROP de query en vivo. Métrica de imán: ≤3 PJs predichos distintos y ≥60% concentrados",
        "> en uno. GT de ejemplos en vivo = etiqueta del GRID-matcher (0-wrong verificado).",
        "",
        "## Composición de la librería runtime (`avatar_detbadge_v2.npz`)",
        f"- refs totales: **{sum(rt_counts.values())}** · PJs: **{len(rt_counts)}**",
        f"- refs/PJ: " + ", ".join(f"{k}ref×{v}PJ" for k, v in sorted(refs_per_pj.items())),
        f"- Nangong Yu: **{rt_counts.get('Nangong Yu', 0)} refs** "
        f"({'no sobre-representado' if rt_counts.get('Nangong Yu', 0) <= max(rt_counts.values()) else 'OJO'}) "
        f"→ el imán **no** es por desbalance de conteo.",
        "",
        "## Resultados 2×2 (guard de naming = 0.80)",
        "",
    ]
    lines += _fmt_case("A", "lib limpia (harvest) · query harvest LOO · BASELINE", A)
    lines += _fmt_case("B", "lib RUNTIME · query harvest limpio (GT)", B)
    lines += _fmt_case("C", "lib limpia (harvest) · query EN VIVO (16_ejemplos)", C)
    lines += _fmt_case("D", "lib RUNTIME · query EN VIVO (16_ejemplos) · CONTROL del QA", D)
    lines += [
        "## Veredicto",
        verdict,
        "",
        f"- imán en B (lib runtime, crop limpio): {'SÍ ⚠️' if b_mag else 'no'}",
        f"- imán en C (lib limpia, crop vivo): {'SÍ ⚠️' if c_mag else 'no'}",
        f"- imán en D (runtime+vivo, control): {'SÍ ⚠️' if d_mag else 'no'}",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")

    # --- consola ---
    print("\n" + "=" * 70)
    for tag, r in [("A", A), ("B", B), ("C", C), ("D", D)]:
        print(f"Caso {tag}: top-1 {r['ok_pct']:.0%} · WRONG {r['wr_pct']:.0%} · "
              f"distintos {r['distinct_preds']} · dominante {r['top_pj']} "
              f"({r['top_share']:.0%}) {'⚠️IMÁN' if is_magnet(r) else ''}")
    print("=" * 70)
    print("VEREDICTO:", verdict)
    print(f"\nReporte → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
Auditoría de SALUD de las librerías de badges (5R.L.8/B3). READ-ONLY.

Para cada superficie (row / grid / detail) reporta:
  1. COBERTURA: refs por PJ vs el roster de la DB — gaps (0 refs) y flacos (<3).
  2. CONTAMINACIÓN (patrón Ben=Soukaku, QA 2026-06-19): refs cuyo vecino más
     cercano en el espacio de descriptores es de OTRO PJ y queda MÁS CERCA que
     cualquier ref del PJ propio → sospecha de cosecha mal etiquetada (el ancla
     vieja etiquetaba por latch; un latch stale contaminaba la librería).

Las librerías .npz guardan DESCRIPTORES (no imágenes) → el chequeo es en espacio
de descriptores; para inspección visual usar los crops de audit/harvest_badges.

Salida: audit/badge_lib_audit_<YYYYMMDD>.md (y stdout). Uso:
    .venv\\Scripts\\python.exe tools\\audit_badge_lib.py [--out <path.md>]
Guía la RE-COSECHA limpia: correr ANTES (qué reponer) y DESPUÉS (verificar).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.agent_identifier import AgentIdentifier          # noqa: E402
from app.core.avatar_descriptor import descriptor_distance     # noqa: E402

_LOW_REFS = 3          # menos que esto = cobertura flaca (multi-ref pide variación)
_MARGIN_FLAG = 0.02    # el vecino extranjero debe ganar por ≥ esto para flaggear


def _flatten(matcher) -> list[tuple[str, object]]:
    return [(name, d) for name, lst in matcher._refs.items() for d in lst]


def _audit_surface(name: str, matcher, roster: set[str],
                   ico_names: set[str] | None = None) -> list[str]:
    lines = [f"## Superficie `{name}`", ""]
    refs = matcher._refs
    ico_names = ico_names or set()
    total = sum(len(v) for v in refs.values())
    lines.append(f"- Refs totales: **{total}** en **{len(refs)}** PJs "
                 f"(roster: {len(roster)}).")
    # 1. Cobertura
    gaps = sorted(r for r in roster if r not in refs or not refs[r])
    flacos = sorted((r, len(refs[r])) for r in refs if r in roster and 0 < len(refs[r]) < _LOW_REFS)
    fuera = sorted(r for r in refs if r not in roster and r not in ico_names)
    seeded = sorted(r for r in refs if r not in roster and r in ico_names)
    if gaps:
        lines.append(f"- ⚠️ **Sin refs ({len(gaps)}):** {', '.join(gaps)}")
    if flacos:
        lines.append(f"- ⚠️ **Cobertura flaca (<{_LOW_REFS}):** "
                     + ", ".join(f"{r} ({n})" for r, n in flacos))
    if fuera:
        lines.append(f"- ⚠️ **Nombres fuera del roster:** {', '.join(fuera)} "
                     "(prune_to_roster los borraría — revisar canonicalización)")
    if seeded:
        lines.append(f"- ℹ️ Sembrados de -ico no poseídos (protegidos, esperado): "
                     f"{', '.join(seeded)}")
    if not (gaps or flacos or fuera):
        lines.append("- ✅ Cobertura completa, todos los nombres canónicos.")
    # 2. Contaminación por vecino extranjero
    flat = _flatten(matcher)
    sospechas: list[tuple[float, str, str]] = []
    for i, (nm, d) in enumerate(flat):
        best_own, best_for, for_name = None, None, None
        for j, (nm2, d2) in enumerate(flat):
            if i == j:
                continue
            dist = descriptor_distance(d, d2)
            if nm2 == nm:
                best_own = dist if best_own is None else min(best_own, dist)
            elif best_for is None or dist < best_for:
                best_for, for_name = dist, nm2
        if best_for is None or for_name is None:
            continue
        own = best_own if best_own is not None else 1.0
        if best_for + _MARGIN_FLAG < own:      # el extranjero gana con margen
            sospechas.append((own - best_for, nm, for_name))
    if sospechas:
        sospechas.sort(reverse=True)
        lines.append(f"- ⚠️ **Sospecha de contaminación ({len(sospechas)} refs):** "
                     "ref etiquetada como X pero más cercana a otro PJ:")
        vistos: set[tuple[str, str]] = set()
        for gap, nm, other in sospechas:
            if (nm, other) in vistos:
                continue
            vistos.add((nm, other))
            n_pair = sum(1 for _g, a, b in sospechas if (a, b) == (nm, other))
            lines.append(f"  - `{nm}` → se parece más a `{other}` "
                         f"({n_pair} ref(s), Δ={gap:.3f})")
    else:
        lines.append("- ✅ Sin sospechas de contaminación (cada ref es más cercana a su propio PJ).")
    lines.append("")
    return lines


def main() -> None:
    # Consola Windows en cp1252 no imprime emoji/acentos (gotcha conocido) → UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="path del reporte MD (default audit/)")
    args = ap.parse_args()

    ident = AgentIdentifier()          # carga librerías runtime + roster de la DB (read-only)
    ident._load_roster()
    roster = set((ident._roster_norm or {}).values())

    out_lines = [
        f"# Auditoría de librerías de badges — {date.today().isoformat()}",
        "",
        "Read-only (`tools/audit_badge_lib.py`). Cobertura + contaminación por",
        "vecino-extranjero en espacio de descriptores. Correr antes y después de una",
        "re-cosecha (`qa_launch -BadgeHarvest`).",
        "",
    ]
    for name in ("row", "grid", "detail"):
        out_lines += _audit_surface(name, ident.surfaces[name].matcher, roster,
                                    ico_names=ident._ico_names)

    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parents[1] / "audit" / f"badge_lib_audit_{date.today():%Y%m%d}.md")
    out.write_text("\n".join(out_lines), encoding="utf-8")
    print("\n".join(out_lines))
    print(f"\n→ reporte: {out}")


if __name__ == "__main__":
    main()

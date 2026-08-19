"""Audita las DOS superficies que nombran al dueño de un disco en S9: grilla y detalle.

Existe porque esta verificación depende de los DATOS —las refs cosechadas en
`%LOCALAPPDATA%`— y no del código, así que no puede vivir en la suite: `conftest`
redirige la librería de avatares a un temp para que ningún test toque la del usuario.
Mismo motivo por el que existe `measure_badge_lib.py`.

Responde tres preguntas, y la segunda es la que importa:

  1. ¿cuántos discos nombra cada superficie por su cuenta?
  2. cuando las DOS hablan, ¿dicen lo mismo? Un desacuerdo significa que una está
     nombrando mal con confianza, que es peor que abstenerse.
  3. ¿cuántos RESCATA el detalle? (tile no localizado, o abstención por look-alike)

Uso:
    .venv/Scripts/python.exe tools/audit_s9_surfaces.py
    .venv/Scripts/python.exe tools/audit_s9_surfaces.py <carpeta con .png>
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_DEFAULT = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"


def _nombre(res):
    """`s17_match*` devuelve tuplas de 3 o 4 campos según la superficie."""
    if res is None:
        return None, 0.0
    if isinstance(res, tuple):
        return res[0], (res[1] if len(res) > 1 else 0.0)
    return res.name, res.conf


def main() -> int:
    from app.core.agent_identifier import AgentIdentifier
    from app.core.detector import (
        BADGE_LIBRE,
        crop_s9_detail_badge,
        read_s9_selected_badge,
    )

    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT
    frames = sorted(carpeta.glob("*.png"))
    if not frames:
        print(f"sin capturas en {carpeta}")
        return 1

    # `prune=False`: construir sin esto PODA Y PERSISTE la librería del usuario, o sea que
    # esta auditoría mutaría lo que vino a medir. Misma lección que `audit_badge_lib`, que
    # borró 4 refs de "N.º 11" solo por mirarlas (2026-08).
    ident = AgentIdentifier(prune=False)
    n_grid = n_det = acuerdos = desacuerdos = rescates = libres = 0
    conflictos: list[str] = []

    print(f"{'captura':<14} {'GRILLA':<24} {'DETALLE':<24} veredicto")
    print("-" * 78)
    for p in frames:
        f = cv2.imread(str(p))
        if f is None:
            continue
        g = read_s9_selected_badge(f)
        ng, cg = _nombre(ident.s17_match(g.crop)) if g.crop is not None else (None, 0.0)
        txt_g = (f"{ng} ({cg:.2f})" if ng else
                 ("LIBRE" if g.estado == BADGE_LIBRE else
                  ("sin tile" if g.crop is None else f"abstiene ({cg:.2f})")))

        crop = crop_s9_detail_badge(f)
        nd, cd = _nombre(ident.s17_match_detail(crop)) if crop is not None else (None, 0.0)
        txt_d = (f"{nd} ({cd:.2f})" if nd else
                 ("sin avatar" if crop is None else f"abstiene ({cd:.2f})"))

        if ng:
            n_grid += 1
        if nd:
            n_det += 1
        if ng and nd:
            if ng == nd:
                acuerdos += 1
                veredicto = "coinciden"
            else:
                desacuerdos += 1
                veredicto = "*** DESACUERDO ***"
                conflictos.append(f"{p.stem}: grilla={ng!r} detalle={nd!r}")
        elif nd and not ng:
            rescates += 1
            veredicto = "RESCATE del detalle"
        elif ng and not nd:
            veredicto = "solo la grilla"
        elif g.estado == BADGE_LIBRE and crop is None:
            libres += 1
            veredicto = "libre (las dos)"
        else:
            veredicto = "sin resolver"
        print(f"{p.stem:<14} {txt_g:<24} {txt_d:<24} {veredicto}")

    total = len(frames)
    print(f"\nnombrados: grilla {n_grid}/{total} · detalle {n_det}/{total}")
    print(f"acuerdos {acuerdos} · DESACUERDOS {desacuerdos} · rescates del detalle {rescates} "
          f"· libres coincidentes {libres}")
    if desacuerdos:
        print("\n⚠️  las dos superficies se contradicen — una está nombrando mal con confianza:")
        for c in conflictos:
            print(f"   {c}")
    return 1 if desacuerdos else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verifica que los enlaces markdown relativos de la documentación resuelvan a un archivo real.

Existe por la mudanza de `Dev_IA/` a `documentacion_cruda/YYYY-MM/` (2026-09-08): bajar los
documentos dos niveles cambia toda ruta relativa, y sin una medición ANTES no hay forma de
distinguir un enlace que rompí de uno que ya estaba roto. Es C1 — medir contra un baseline
validado, antes y después.

Read-only. No escribe nada.

    python tools/check_doc_links.py            # resumen
    python tools/check_doc_links.py --list     # además, cada enlace roto
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Sólo enlaces relativos: los http(s), mailto y anclas puras no se pueden verificar acá.
_RE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")


def _es_relativo(destino: str) -> bool:
    return not (
        destino.startswith(("http://", "https://", "mailto:", "#"))
        or destino.startswith("//")
    )


def revisar(raiz: Path) -> tuple[int, int, list[tuple[Path, str]]]:
    """Devuelve (archivos, enlaces relativos, rotos)."""
    rotos: list[tuple[Path, str]] = []
    n_links = 0
    archivos = sorted(raiz.rglob("*.md"))
    for md in archivos:
        try:
            txt = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for destino in _RE_LINK.findall(txt):
            if not _es_relativo(destino):
                continue
            n_links += 1
            # El ancla no forma parte del path del archivo.
            camino = destino.split("#", 1)[0]
            if not camino:            # enlace sólo-ancla dentro del mismo doc
                continue
            if not (md.parent / camino).resolve().exists():
                rotos.append((md, destino))
    return len(archivos), n_links, rotos


def main() -> int:
    detallar = "--list" in sys.argv
    archivos, n_links, rotos = revisar(RAIZ / "Documentacion")
    # Los dos de la raíz que apuntan a la documentación.
    extra_archivos = 0
    for suelto in ("CLAUDE.md", "project-context-IA.md", "README.md"):
        p = RAIZ / suelto
        if not p.exists():
            continue
        extra_archivos += 1
        for destino in _RE_LINK.findall(p.read_text(encoding="utf-8")):
            if not _es_relativo(destino):
                continue
            n_links += 1
            camino = destino.split("#", 1)[0]
            if camino and not (p.parent / camino).resolve().exists():
                rotos.append((p, destino))

    print(f"archivos revisados : {archivos + extra_archivos}")
    print(f"enlaces relativos  : {n_links}")
    print(f"ROTOS              : {len(rotos)}")
    if detallar:
        for md, destino in rotos:
            print(f"  {md.relative_to(RAIZ)}  ->  {destino}")
    total = len(rotos)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

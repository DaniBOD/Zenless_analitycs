# -*- coding: utf-8 -*-
"""
Regresión 2026-07-31 — `tools/audit_badge_lib.py` se documenta READ-ONLY pero MUTABA
las librerías que audita.

Causa: construía `AgentIdentifier()` con `autoload=True`, y `__init__` corre
`prune_to_roster()`, que persiste (`save*()`) cuando removió algo. Correr el audit
sobre `avatar_detbadge_v2.npz` borró en silencio las 4 refs de la clave doble-codificada
`'n.\\xc2\\xba11'` (mojibake de 'N.º 11'): 39 clases/155 refs → 38/151. El reporte
listó al PJ como "sin refs" — describiendo un estado que el propio audit causó.

Dos invariantes acá:
  1. El audit NO toca sus archivos (sha256 idéntico antes/después).
  2. `prune_to_roster` canonicaliza (y repara mojibake) ANTES de podar: una clave
     recuperable se RENOMBRA, no se tira. Podar es para basura de OCR, no para
     cosecha con la etiqueta mal codificada.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]

from app.core.agent_identifier import AgentIdentifier          # noqa: E402
from app.core.avatar_descriptor import AvatarMatcher           # noqa: E402

# La clave exacta observada en la librería runtime: los bytes UTF-8 de 'º'
# (0xC2 0xBA) leídos como latin-1. Canonicalizar NO alcanza (NFD tira el acento
# de 'Â' → 'a'); hace falta re-decodificar.
MOJIBAKE_N11 = "n.\xc2\xba11"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descs(n: int) -> list:
    """`n` descriptores distintos (imágenes sintéticas, shapes reales)."""
    m = AvatarMatcher()
    for i in range(n):
        rng = np.random.default_rng(1000 + i)
        m.add_reference("x", rng.integers(0, 256, (48, 48, 3), dtype=np.uint8))
    return list(m._refs["x"])


def _write_lib(path: Path, refs: dict[str, int]) -> None:
    m = AvatarMatcher()
    m._refs = {name: _descs(n) for name, n in refs.items()}
    m.save(path)


@pytest.fixture
def roster_db(tmp_path, monkeypatch) -> Path:
    """DB temp con solo `agents` — el roster que ve `_load_roster()`."""
    p = tmp_path / "roster.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE)")
    con.executemany("INSERT INTO agents (nombre) VALUES (?)",
                    [("Ellen",), ("Lucía",), ("N.º 11",)])
    con.commit()
    con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(p))
    return p


def test_audit_badge_lib_no_muta_las_librerias(tmp_path, monkeypatch, roster_db):
    """El audit es READ-ONLY: sha256 de las 3 librerías idéntico antes y después.

    Las fixtures traen a propósito claves que `prune_to_roster` tocaría —
    una mojibake (recuperable) y una basura de OCR (borrable) — para que el test
    falle si el audit poda/persiste por cualquiera de los dos caminos.
    """
    base = tmp_path / "avatar_library.npz"
    monkeypatch.setenv("DANIBOD_AVATAR_LIB", str(base))
    libs = ("avatar_row_v2.npz", "avatar_badge_v2.npz", "avatar_detbadge_v2.npz")
    antes = {}
    for fname in libs:
        p = base.with_name(fname)
        _write_lib(p, {"Ellen": 2, MOJIBAKE_N11: 4, "Permiso": 1})
        antes[fname] = _sha256(p)

    sys.path.insert(0, str(REPO / "tools"))
    try:
        import audit_badge_lib
    finally:
        sys.path.remove(str(REPO / "tools"))
    monkeypatch.setattr(sys, "argv",
                        ["audit_badge_lib.py", "--out", str(tmp_path / "rep.md")])
    audit_badge_lib.main()

    for fname, sha in antes.items():
        assert _sha256(base.with_name(fname)) == sha, \
            f"el audit MUTÓ {fname} — se documenta READ-ONLY"

    # Que NO mute no puede deberse a que no leyó nada: el reporte tiene que probar
    # que vio las librerías, y explicar la clave rota en vez de dejar al PJ como
    # un hueco inexplicado (que fue justo lo que confundió el 2026-07-31).
    rep = (tmp_path / "rep.md").read_text(encoding="utf-8")
    assert "Ellen" in rep, "el audit no llegó a leer las librerías"
    assert "RENOMBRA" in rep and "N.º 11" in rep, \
        "el reporte no avisa que la clave mojibake es recuperable"
    assert "BORRA" in rep and "Permiso" in rep, \
        "el reporte no avisa qué claves sí se van a podar"


def test_las_herramientas_de_tools_deciden_prune_explicitamente():
    """`AgentIdentifier()` a secas PODA Y PERSISTE — una herramienta de diagnóstico que
    lo construye así modifica la librería solo por mirarla, en silencio. Toda tool debe
    escribir `prune=` a mano (False para inspeccionar, True si de verdad quiere podar)."""
    culpables = []
    for py in sorted((REPO / "tools").glob("*.py")):
        txt = py.read_text(encoding="utf-8", errors="replace")
        for i, linea in enumerate(txt.splitlines(), 1):
            if "AgentIdentifier(" in linea and "prune=" not in linea:
                culpables.append(f"{py.name}:{i}")
    assert not culpables, (
        "construyen AgentIdentifier sin decidir prune= (podan+persisten al arrancar): "
        + ", ".join(culpables))


def test_prune_to_roster_repara_mojibake_en_vez_de_borrar(tmp_path):
    """Una clave doble-codificada es cosecha VÁLIDA mal etiquetada: se renombra al
    canónico (las 4 refs sobreviven), no se poda."""
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Ellen", "N.º 11"})
    ident._detbadge._refs = {"Ellen": _descs(1), MOJIBAKE_N11: _descs(4)}
    ident.prune_to_roster()
    assert MOJIBAKE_N11 not in ident._detbadge._refs
    assert len(ident._detbadge._refs.get("N.º 11", [])) == 4, \
        "se perdieron las refs del PJ en vez de reetiquetarlas"


def test_prune_to_roster_canonicaliza_antes_de_podar(tmp_path):
    """Una clave no canónica que el roster resuelve ('Lucia' sin tilde, espaciado
    distinto) se renombra; sus refs se fusionan con las que ya haya del canónico."""
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Lucía", "N.º 11"})
    ident._badge._refs = {"Lucía": _descs(1), "Lucia": _descs(2), "N.º11": _descs(3)}
    ident.prune_to_roster()
    assert sorted(ident._badge._refs) == ["Lucía", "N.º 11"]
    assert len(ident._badge._refs["Lucía"]) == 3      # 1 canónica + 2 fusionadas
    assert len(ident._badge._refs["N.º 11"]) == 3


def test_prune_to_roster_sigue_borrando_basura_de_ocr(tmp_path):
    """La poda sigue haciendo su trabajo con lo irrecuperable (RNF-02: nada de
    inventar un PJ para una clave que el roster no resuelve)."""
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Ellen"})
    ident._row._refs = {"Ellen": _descs(1), "Permiso": _descs(1)}
    ident._badge._refs = {"Sporos_bogus": _descs(1)}
    assert ident.prune_to_roster() == 2
    assert ident.names == ["Ellen"] and ident.names_s17 == []

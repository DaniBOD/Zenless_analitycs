"""`tokens.ELEMENTO_COLOR` — una sola paleta de elementos para toda la interfaz.

Había dos que no coincidían (la tabla vieja del roster y el `elemColor` del mockup): B1, dos
autoridades para la misma pregunta. Desde la fase 2 el color de acento del modal de PJ SALE del
elemento (decisión de Daniel, 2026-09-13), así que un elemento sin color deja un modal gris.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.ui import tokens as T

DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


def test_cada_elemento_del_roster_tiene_color():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        elementos = {r[0] for r in con.execute("SELECT DISTINCT elemento FROM agents")}
    finally:
        con.close()
    faltan = sorted(e for e in elementos if e not in T.ELEMENTO_COLOR)
    assert not faltan, f"elementos sin color en tokens.ELEMENTO_COLOR: {faltan}"


def test_un_elemento_desconocido_cae_a_neutro_sin_romper():
    assert T.color_elemento("Plasma") == T.ELEMENTO_NEUTRO
    assert T.color_elemento(None) == T.ELEMENTO_NEUTRO
    assert T.color_elemento("Fuego") == T.ELEMENTO_COLOR["Fuego"]


def test_la_vista_roster_no_tiene_su_propia_paleta():
    """La tabla vieja vivía en `views/roster.py`. Si vuelve, hay dos autoridades otra vez."""
    fuente = (Path(__file__).resolve().parents[2] / "ui" / "views" / "roster.py").read_text(encoding="utf-8")
    assert "#4a9eff" not in fuente and "elem_colors" not in fuente

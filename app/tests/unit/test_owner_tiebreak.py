"""Desempate de dueño por CONTEXTO (build) — `OwnerTiebreaker`.

Cuando el matcher de badges se abstiene por margen chico entre look-alikes, el build
(set firma 4pc/2pc en la DB) confirma el top-1 visual SOLO si lo distingue del top-2.
Tests herméticos: DB sqlite temporal con una tabla `agents` mínima + un resolutor de
set fake (no depende del fuzzy real de disc_sets). RNF-02: cero asignaciones MAL.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.owner_tiebreak import OwnerTiebreaker


# set_id de juguete: 100=Punk (firma de César), 200=Floración (compartido), 300=Monarca.
_SET_BY_NAME = {"punk": 100, "floracion": 200, "monarca": 300}


def _resolve_set_id_fake(disc) -> int | None:
    raw = (getattr(disc, "set_name_raw", "") or "").lower()
    for key, sid in _SET_BY_NAME.items():
        if key in raw:
            return sid
    return None


class _Disc:
    def __init__(self, set_name_raw):
        self.set_name_raw = set_name_raw
        self.set_name_canon = None


@pytest.fixture
def tb(tmp_path: Path) -> OwnerTiebreaker:
    db = tmp_path / "roster.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE agents (nombre TEXT, set_4p_id INT, set_2p_id INT);
        INSERT INTO agents VALUES ('César', 100, 999);   -- corre Punk (4p)
        INSERT INTO agents VALUES ('Lucía', 200, 100);   -- corre Floración + Punk (2p)
        INSERT INTO agents VALUES ('Velina', NULL, NULL); -- recién onboardeada, sin build
        INSERT INTO agents VALUES ('Sporos', 200, NULL); -- corre Floración
        """
    )
    con.commit()
    con.close()
    return OwnerTiebreaker(db_path=db, resolve_set_id=_resolve_set_id_fake)


def test_confirma_top1_si_distingue(tb):
    # Punk distingue a César (lo corre) de Velina (sin build) → confirma César.
    r = tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10), ("Velina", 0.13)])
    assert r == ("César", "build")


def test_no_promueve_top2(tb):
    # top-1 Velina (sin build), top-2 César (corre Punk): NUNCA promueve el top-2.
    assert tb.resolve(_Disc("Punk Primitivo"), [("Velina", 0.10), ("César", 0.13)]) is None


def test_abstiene_si_ambos_corren_el_set(tb):
    # Floración la corren Sporos y Lucía → no distingue → abstención.
    assert tb.resolve(_Disc("Floración del alba"), [("Sporos", 0.10), ("Lucía", 0.13)]) is None


def test_abstiene_si_top2_tambien_corre_punk(tb):
    # Punk: top-1 César (4p) y top-2 Lucía (2p) ambos lo corren → no distingue.
    assert tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10), ("Lucía", 0.13)]) is None


def test_abstiene_si_ninguno_corre_el_set(tb):
    # Monarca (filler): ni César ni Velina lo tienen como firma → abstención.
    assert tb.resolve(_Disc("Monarca del Pináculo"), [("César", 0.10), ("Velina", 0.13)]) is None


def test_abstiene_si_set_no_resuelve(tb):
    assert tb.resolve(_Disc("basura ocr xyz"), [("César", 0.10), ("Velina", 0.13)]) is None


def test_abstiene_con_menos_de_dos_candidatos(tb):
    assert tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10)]) is None
    assert tb.resolve(_Disc("Punk Primitivo"), []) is None


def test_acentos_y_normalizacion(tb):
    # Los nombres del matcher pueden venir con acentos/casing distintos; _norm_key alinea.
    assert tb.resolve(_Disc("Punk Primitivo"), [("cesar", 0.10), ("velina", 0.13)]) == ("cesar", "build")

"""Alta de Fortuna felina (Catty Luck), el primer W-Engine de Armero — migración 39.

Lo que se verifica no es que la fila exista (eso lo hacen los smoke checks de la migración), sino
lo que la fila HABILITA, que es por lo que se dio de alta:

1. que el nombre que S30 lee ROTO (`Fortunafelina -01+`, censo del 2026-09-17) matchee el
   catálogo — si no, la próxima pasada lo vuelve a reportar fuera de catálogo y la fila de
   inventario de Claret no se escribe nunca;
2. que el ícono resuelva por el `nombre_en` de la DB — sin él, `engine_icon_path` se abstiene y la
   pantalla Armas dibuja un hueco;
3. que entre con el atributo principal bien rotulado (DEF), que es por lo que esperó a la mig 37.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.asset_resolver import engine_icon_path
from app.core.parser_weapon_s26 import match_catalogo

DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
APP = Path(__file__).resolve().parents[2]

#: Lo que leyó S30 en vivo el 2026-09-17, tal cual (log del censo de armas).
LEIDO_EN_S30 = "Fortunafelina -01+"


def _db_real() -> sqlite3.Connection:
    if not DB.exists():
        pytest.skip("sin DB de dominio")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _fila():
    con = _db_real()
    try:
        return con.execute("SELECT * FROM weapons WHERE nombre = 'Fortuna felina'").fetchone()
    finally:
        con.close()


def _catalogo() -> list[str]:
    con = _db_real()
    try:
        return [r[0] for r in con.execute("SELECT nombre FROM weapons")]
    finally:
        con.close()


def test_el_nombre_roto_de_s30_matchea_el_catalogo_real():
    """El `-01+` sigue saliendo del camino de S30 (bug aparte). Con la fila en el catálogo el fuzzy
    lo absorbe; sin ella, el arma se reporta fuera de catálogo en cada pasada."""
    assert match_catalogo(LEIDO_EN_S30, _catalogo()) == "Fortuna felina"


def test_el_icono_resuelve_por_el_nombre_ingles_de_la_db():
    fila = _fila()
    assert fila is not None, "la mig 39 no está aplicada"
    p = engine_icon_path(fila["nombre"], fila["nombre_en"])
    assert p is not None, "sin ícono la pantalla Armas dibuja un hueco"
    assert p.exists()
    assert APP in p.resolve().parents, "D1: lo que la app lee vive dentro de app/"


def test_entra_con_el_atributo_principal_rotulado_como_DEF():
    """Esperó a la mig 37 justamente para esto: antes su 356 habría entrado a `atk_base`."""
    fila = _fila()
    assert (fila["tipo_especialidad"], fila["stat_base_tipo"], fila["stat_base_valor"]) == (
        "Armero", "DEF", 356)


def test_el_valor_del_catalogo_es_el_de_nivel_60_no_el_de_la_pantalla():
    """La pantalla dijo 297 a Nv 50/50. El catálogo guarda el de nivel 60 (Gachabase + Game8)."""
    assert _fila()["stat_base_valor"] != 297

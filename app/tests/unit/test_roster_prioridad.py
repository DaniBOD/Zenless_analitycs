"""La prioridad de buildeo en la pantalla Roster: marca, filtro y leyenda (handoff design_v3).

- **La celda**: sólo alta y baja se pintan. Alta = barra superior lima + pestaña; baja = sólo la
  pestaña, pizarra. Se verifica lo que queda PINTADO (una captura de la celda), no un atributo: esta
  pantalla ya tuvo casilleros de discos de 0 px con los tests en verde.
- **El logo de facción se corre** para que la pestaña no lo tape.
- **El filtro** por prioridad y sus conteos (sobre el roster completo).
- **La leyenda** suma alta y baja sólo cuando hay alguna declarada.
- La fuente es `PrioridadRepo` (la misma que usa el motor): sin la tabla, todos en normal.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtGui import QColor                      # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

from app.ui import tokens as T                        # noqa: E402
from app.ui.roster.celda import CeldaRoster           # noqa: E402
from app.ui.roster.datos import CeldaPJ, conteos_prioridad, filtrar, leer_roster  # noqa: E402
from app.ui.roster.view import RosterView            # noqa: E402

_ESQUEMA = """
    CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rango TEXT, nivel INTEGER,
        mindscape INTEGER, elemento TEXT, rol TEXT, faccion TEXT);
    CREATE TABLE agent_thresholds (id INTEGER PRIMARY KEY, agente_id INTEGER, stat TEXT);
    CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
        equipado INTEGER, descartado INTEGER);
    CREATE TABLE inventory_weapons (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
        equipado INTEGER, descartado INTEGER);
    INSERT INTO agents VALUES
        (1, 'Claret Flint', 'S', 60, 0, 'Eléctrico', 'Armero', 'Taller Flint'),
        (2, 'Piper', 'A', 60, 0, 'Físico', 'Anomalía', 'Sons of Calydon'),
        (3, 'Lycaon', 'S', 60, 0, 'Hielo', 'Aturdimiento', 'Victoria Housekeeping');
    INSERT INTO agent_thresholds (agente_id, stat) VALUES (1,'x'),(2,'x'),(3,'x');
"""
_MIG42 = """
    CREATE TABLE ajustes_usuario_prioridad (agente_id INTEGER PRIMARY KEY, prioridad TEXT NOT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP);
"""


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


def _con(prioridades: dict[int, str] | None):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_ESQUEMA)
    if prioridades is not None:
        c.executescript(_MIG42)
        c.executemany("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, ?)",
                      prioridades.items())
    return c


def _celda(nombre="X", prioridad="normal", faccion="Taller Flint"):
    return CeldaPJ(id=9, nombre=nombre, rango="S", elemento="Eléctrico", rol="Ataque",
                   faccion=faccion, mindscape=0, nivel=60, discos=6, tiene_arma=True,
                   sin_thresholds=False, variante_de=None, prioridad=prioridad)


# --- datos ---------------------------------------------------------------------------------------

def test_sin_la_tabla_todos_en_normal():
    assert {c.prioridad for c in leer_roster(_con(None))} == {"normal"}


def test_la_prioridad_llega_a_la_celda():
    p = {c.nombre: c.prioridad for c in leer_roster(_con({1: "alta", 2: "baja"}))}
    assert p == {"Claret Flint": "alta", "Piper": "baja", "Lycaon": "normal"}


def test_conteos_y_filtro():
    celdas = leer_roster(_con({1: "alta", 2: "baja"}))
    assert conteos_prioridad(celdas) == {"alta": 1, "normal": 1, "baja": 1}
    assert [c.nombre for c in filtrar(celdas, {"prioridad": {"alta"}})] == ["Claret Flint"]
    assert {c.nombre for c in filtrar(celdas, {"prioridad": {"alta", "baja"}})} == {"Claret Flint", "Piper"}


# --- la celda: lo que queda pintado ------------------------------------------------------------

def _captura(qapp, celda: CeldaPJ):
    w = CeldaRoster(celda)
    w.resize(122, 96)
    w.layout().activate()
    img = w.grab().toImage()
    return w, img


def _es(img, x, y, color: str, tol=24) -> bool:
    c, obj = QColor(img.pixel(x, y)), QColor(color)
    return all(abs(a - b) <= tol for a, b in ((c.red(), obj.red()), (c.green(), obj.green()),
                                              (c.blue(), obj.blue())))


def test_alta_pinta_la_barra_lima_de_lado_a_lado(qapp):
    _, img = _captura(qapp, _celda(prioridad="alta"))
    assert _es(img, 60, 1, T.PRIO_ALTA) and _es(img, 115, 1, T.PRIO_ALTA)


def test_el_halo_de_la_barra_es_lima_no_rojo(qapp):
    """Qt lee "#C4F03A40" como #AARRGGBB: sumar el alfa al string pintaba una línea ROJA bajo la
    barra (se vio en la primera captura). Debajo de la barra el verde tiene que ganarle al rojo."""
    _, img = _captura(qapp, _celda(prioridad="alta"))
    halo = QColor(img.pixel(60, 3))
    assert halo.green() > halo.red(), halo.name()


def test_baja_no_tiene_barra_pero_si_pestana(qapp):
    _, img = _captura(qapp, _celda(prioridad="baja"))
    assert not _es(img, 60, 1, T.PRIO_ALTA), "baja no lleva barra"
    assert _es(img, 5, 2, T.PRIO_BAJA_FONDO), "pestaña pizarra arriba a la izquierda"


def test_normal_no_se_pinta(qapp):
    _, img = _captura(qapp, _celda(prioridad="normal"))
    assert not _es(img, 60, 1, T.PRIO_ALTA) and not _es(img, 5, 2, T.PRIO_BAJA_FONDO)
    assert not _es(img, 5, 2, T.PRIO_ALTA)


@pytest.mark.parametrize("prioridad", ["alta", "baja"])
def test_el_logo_de_faccion_queda_a_la_derecha_de_la_pestana(qapp, prioridad):
    w, _ = _captura(qapp, _celda(prioridad=prioridad))
    assert w._faccion.geometry().x() >= 3 + 17


def test_sin_prioridad_el_logo_no_se_corre(qapp):
    w, _ = _captura(qapp, _celda(prioridad="normal"))
    assert w._faccion.geometry().x() < 3 + 17


def test_agrandada_la_pestana_sigue_sin_tapar_el_logo(qapp):
    w = CeldaRoster(_celda(prioridad="alta"))
    w.resize(round(122 * 2.2), round(96 * 2.2))
    w.set_escala(2.2)
    w.layout().activate()
    assert w._faccion.geometry().x() >= round((3 + 17) * 2.2)


# --- la vista ------------------------------------------------------------------------------------

def test_los_chips_del_filtro_cuentan_y_filtran(qapp):
    v = RosterView(_con({1: "alta", 2: "baja"}))
    v.resize(1300, 800)
    assert v.filtros.chip("prioridad", "alta").text() == "▲ Alta 1"
    assert v.filtros.chip("prioridad", "normal").text() == "Normal 1"
    assert v.filtros.chip("prioridad", "baja").text() == "▼ Baja 1"
    v.filtros.chip("prioridad", "alta").setChecked(True)
    assert [c.celda.nombre for c in v.celdas() if not c.isHidden()] == ["Claret Flint"]


def test_la_leyenda_suma_alta_y_baja_solo_si_hay_alguna(qapp):
    sin = RosterView(_con(None))
    con = RosterView(_con({2: "baja"}))
    assert all(i.isHidden() for i in sin._leyenda_prio.values())
    assert not any(i.isHidden() for i in con._leyenda_prio.values())

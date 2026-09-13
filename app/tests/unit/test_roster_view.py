"""La pantalla Roster (Parte B del diseño v1) — offscreen, afirmando sobre lo que quedó a la vista.

Garantías:

1. **El cuerpo nunca scrollea**: no hay `QScrollArea`, y las celdas visibles entran en el cuerpo.
2. **Un nivel sin leer dice "sin leer"**, no un número (la DB está vacía de stats desde el 17/08).
3. **Las marcas se ven**: el atuendo trae su badge y la esquina ámbar sale sólo en los que no tienen
   umbrales.
4. **Los filtros ocultan celdas** y el header dice los conteos de la DB.
5. **Click en una celda pide la ficha de ESE PJ** (el modal lo abre la ventana).
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt                # noqa: E402
from PySide6.QtTest import QTest                     # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea   # noqa: E402

from app.ui.roster.view import RosterView            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row          # como `get_connection()` de la app
    c.executescript("""
        CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rango TEXT, nivel INTEGER,
            mindscape INTEGER, elemento TEXT, rol TEXT, faccion TEXT);
        CREATE TABLE agent_thresholds (id INTEGER PRIMARY KEY, agente_id INTEGER, stat TEXT);
        CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
            equipado INTEGER, descartado INTEGER);
        CREATE TABLE inventory_weapons (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
            equipado INTEGER, descartado INTEGER);
        CREATE TABLE roster_declarations (id INTEGER PRIMARY KEY, ts TEXT, nombre TEXT,
            poseido INTEGER, fuente TEXT);
        INSERT INTO agents VALUES
            (1, 'Yanagi', 'S', 60, 0, 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6'),
            (2, 'Billy', 'A', NULL, 6, 'Físico', 'Ataque', 'Cunning Hares'),
            (3, 'Billy Estelar', 'S', NULL, 0, 'Físico', 'Disruptivos', 'Cunning Hares'),
            (4, 'Pyrois', '∞', 40, 0, 'Éter', 'Ataque', 'Faetón');
        INSERT INTO agent_thresholds (agente_id, stat) VALUES (1,'x'),(2,'x'),(3,'x');
        INSERT INTO roster_declarations (ts, nombre, poseido, fuente) VALUES
            ('2026-08-18', 'Norma', 0, 'usuario'), ('2026-08-18', 'Yanagi', 1, 'usuario');
    """)
    yield c
    c.close()


@pytest.fixture
def vista(qapp, con):
    v = RosterView(con)
    v.resize(1100, 756)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def _visibles(v):
    return [c for c in v.celdas() if c.isVisible()]


def test_no_hay_scroll_y_las_celdas_entran_en_el_cuerpo(vista):
    assert not vista.findChildren(QScrollArea)
    cuerpo = vista.cuerpo.rect()
    for c in _visibles(vista):
        assert cuerpo.contains(c.geometry()), f"{c.celda.nombre} se sale del cuerpo"


def test_la_vista_entra_en_la_ventana_minima(qapp):
    """Con la DB REAL (51 PJs, 16 facciones): ninguna banda puede pedir más ancho que el área de
    vistas de la ventana mínima, 1320 − 220 de sidebar = 1100. Pasó: una fila de chips estiraba la
    vista entera a 2549 px y la mitad de la grilla quedaba fuera de pantalla.

    Se mide con las fuentes REALES de Windows: el offscreen sin fuentes dibuja cada letra como un
    cuadrado más ancho que el glifo y el ancho medido no se parece al de la app."""
    import glob
    from pathlib import Path

    from PySide6.QtGui import QFontDatabase
    fuentes = glob.glob(r"C:\Windows\Fonts\*.ttf")
    if not fuentes:
        pytest.skip("sin fuentes de Windows: el ancho medido no sería el real")
    for f in fuentes:
        QFontDatabase.addApplicationFont(f)
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        v = RosterView(c)
        assert v.minimumSizeHint().width() <= 1100, v.minimumSizeHint()
        v.resize(1100, 756)
        v.show()
        qapp.processEvents()
        assert v.cuerpo.width() <= 1100
        v.close()
    finally:
        c.close()


def test_nivel_sin_leer_y_nivel_leido(vista):
    textos = {c.celda.nombre: c.textos_visibles() for c in vista.celdas()}
    assert "sin leer" in textos["Billy"]
    assert "Nv 40" in textos["Pyrois"]
    assert not any(t.startswith("Nv") for t in textos["Billy"])


def test_marcas_atuendo_y_faltan_datos(vista):
    c = {x.celda.nombre: x for x in vista.celdas()}
    assert "ATUENDO · Billy" in c["Billy Estelar"].textos_visibles()
    assert not any("ATUENDO" in t for t in c["Billy"].textos_visibles())
    assert c["Pyrois"].marca_faltan_datos and not c["Yanagi"].marca_faltan_datos


def test_header_con_los_conteos(vista):
    h = vista.texto_header()
    for fragmento in ("4 filas", "1 atuendo", "3 distintos", "1 no obtenidos", "4 conocidos",
                      "1 sin umbrales"):
        assert fragmento in h, (fragmento, h)


def test_un_filtro_oculta_celdas_y_limpiarlo_las_devuelve(vista, qapp):
    assert len(_visibles(vista)) == 4
    vista.filtros.chip("elemento", "Físico").click()
    qapp.processEvents()
    assert {c.celda.nombre for c in _visibles(vista)} == {"Billy", "Billy Estelar"}
    vista.filtros.chip("estado", "faltan_datos").click()
    qapp.processEvents()
    assert _visibles(vista) == [], "Físico Y le faltan datos: ninguno"
    vista.filtros.limpiar()
    qapp.processEvents()
    assert len(_visibles(vista)) == 4


def test_click_en_una_celda_pide_la_ficha_de_ese_pj(vista, qapp):
    pedidos = []
    vista.ficha_pedida.connect(pedidos.append)
    celda = next(c for c in vista.celdas() if c.celda.nombre == "Pyrois")
    QTest.mouseClick(celda, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    qapp.processEvents()
    assert pedidos == [4]


def test_los_casilleros_de_discos_tienen_tamano(vista):
    """Un widget pintado a mano sin tamaño declarado queda en 0 px y no se ve, con los textos bien."""
    from app.ui.roster.celda import _Discos
    for c in vista.celdas():
        (d,) = c.findChildren(_Discos)
        assert d.width() >= 40 and d.height() > 0, c.celda.nombre


def test_infinito_va_primero(vista):
    orden = [c.celda.nombre for c in vista.celdas()]
    assert orden[0] == "Pyrois"

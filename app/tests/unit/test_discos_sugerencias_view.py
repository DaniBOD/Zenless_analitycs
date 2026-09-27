"""Las sugerencias del motor en la pantalla Discos (SPEC 2026-09-27) — offscreen.

- la columna dice "…" mientras el motor calcula y se completa cuando llega el resultado (por el
  hilo de verdad, no a mano);
- el filtro y el recuadro del lateral filtran por tipo;
- una sugerencia en conflicto se ve apagada y su tooltip dice con qué choca;
- el disco que repone en un "mover" lo dice;
- con la DB real, cada sugerencia propia del reporte está en su fila.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from app.core.sugerencias import SugerenciaDisco             # noqa: E402
from app.tests.unit.test_discos_datos import _disco           # noqa: E402
from app.ui.discos.servicio_sugerencias import ServicioSugerencias  # noqa: E402
from app.ui.discos.tabla import CALCULANDO                   # noqa: E402
from app.ui.discos.view import DiscosView                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO disc_sets (id, nombre, nombre_en) VALUES
            (1, 'Jazz Caótico', 'Chaos Jazz'), (2, 'Blues Libre', 'Freedom Blues');
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0);
    """)
    _disco(c, 10, 1, 4, agente=1, equipado=1)
    _disco(c, 11, 1, 4, nivel=9)
    _disco(c, 12, 2, 1)
    _disco(c, 14, 1, 5, agente=1, equipado=1)
    return c


MOVER = {"tipo": "mover", "disc_id": 10, "destino": "Anby", "origen": "Yanagi", "reemplazo_id": 12,
         "delta": 2.53, "conflicto": None}
MEJORAR = {"tipo": "mejorar", "disc_id": 11, "destino": "Yanagi", "delta": None, "conflicto": None}
EQUIPAR_CONF = {"tipo": "equipar", "disc_id": 12, "destino": "Lucy", "delta": 0.57,
                "conflicto": "ese slot ya lo toma el disco #7"}
SUGS = {10: SugerenciaDisco(MOVER), 11: SugerenciaDisco(MEJORAR),
        12: SugerenciaDisco(EQUIPAR_CONF, (("repone", MOVER),))}


def _esperar(qapp, cond, tope=5.0):
    fin = time.monotonic() + tope
    while not cond() and time.monotonic() < fin:
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


@pytest.fixture
def vista(qapp, con):
    import threading
    liberar = threading.Event()

    def calcular(_p):
        liberar.wait(5)
        return SUGS

    svc = ServicioSugerencias("fake.db", calcular=calcular)
    v = DiscosView(con, servicio=svc)
    v.resize(1100, 756)
    v.show()
    qapp.processEvents()
    v._liberar = liberar
    yield v
    liberar.set()
    v.close()


def _celda(vista, disco_id, rol=Qt.ItemDataRole.DisplayRole):
    m = vista.tabla.model()
    col = vista.columnas().index("SUGERENCIA")
    fila = vista.ids_visibles().index(disco_id)
    return m.data(m.index(fila, col), rol)


def test_calculando_y_despues_la_columna_completa(vista, qapp):
    assert _celda(vista, 10) == CALCULANDO and "calculando" in vista._estado_sug.text()
    repintadas = []
    vista.tabla.model().dataChanged.connect(lambda a, b, *_: repintadas.append((a.column(), b.column())))
    vista.tabla.model().modelReset.connect(lambda: repintadas.append("reset"))
    vista._liberar.set()
    assert _esperar(qapp, lambda: _celda(vista, 10) != CALCULANDO)
    assert _celda(vista, 10) == "MOVER → Anby +2,53"
    assert _celda(vista, 11) == "MEJORAR → Yanagi"
    assert _celda(vista, 14) == ""                                      # sin nada que hacer
    assert vista._estado_sug.text() == ""
    col = vista.columnas().index("SUGERENCIA")
    assert "reset" in repintadas or (col, col) in repintadas, "la tabla no se entera: no se repinta"


def test_el_filtro_y_el_lateral_filtran_por_tipo(vista, qapp):
    vista._liberar.set()
    assert _esperar(qapp, lambda: vista.servicio.ultimo is not None)
    qapp.processEvents()
    vista.filtros.elegir("sugerencia", "mejorar")
    qapp.processEvents()
    assert vista.ids_visibles() == [11]
    vista.filtros.limpiar()
    vista.lateral.boton_sugerencia("mover").click()
    qapp.processEvents()
    assert vista.ids_visibles() == [10]
    vista.filtros.elegir("sugerencia", "sin_cambio")
    qapp.processEvents()
    assert vista.ids_visibles() == [14]


def test_en_conflicto_se_apaga_y_dice_con_que_choca(vista, qapp):
    vista._liberar.set()
    assert _esperar(qapp, lambda: vista.servicio.ultimo is not None)
    qapp.processEvents()
    assert _celda(vista, 12) == "EQUIPAR → Lucy +0,57"
    assert _celda(vista, 12, Qt.ItemDataRole.ForegroundRole).color().alpha() < 255
    assert "ese slot ya lo toma el disco #7" in _celda(vista, 12, Qt.ItemDataRole.ToolTipRole)
    assert _celda(vista, 10, Qt.ItemDataRole.ForegroundRole).color().alpha() == 255


def test_el_que_repone_lo_dice(vista, qapp):
    """#12 tiene su propia sugerencia: manda la propia en la celda. Sin propia, dice que repone."""
    from app.ui.discos.datos import texto_sugerencia
    texto, tipo, _conf, tip = texto_sugerencia(SugerenciaDisco(None, (("repone", MOVER),)))
    assert texto == "↳ repone a #10" and tipo == "mover" and "Anby" in tip


def test_ordenar_por_sugerencia(vista, qapp):
    vista._liberar.set()
    assert _esperar(qapp, lambda: vista.servicio.ultimo is not None)
    qapp.processEvents()
    vista.tabla.sortByColumn(vista.columnas().index("SUGERENCIA"), Qt.SortOrder.AscendingOrder)
    qapp.processEvents()
    assert vista.ids_visibles() == [10, 12, 11, 14]         # mover, equipar, mejorar, sin nada


def test_con_la_db_real_cada_sugerencia_esta_en_su_fila(qapp):
    """El reporte y la pantalla con la MISMA función: cada disco con sugerencia propia la muestra."""
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not db.is_file():
        pytest.skip("sin la DB de dominio")
    from app.core.sugerencias import generar
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        svc = ServicioSugerencias(db)
        v = DiscosView(c, servicio=svc)
        assert _esperar(qapp, lambda: svc.ultimo is not None, tope=30)
        qapp.processEvents()
        rep = generar(db)
        propias = {s["disc_id"] for lista in rep["sugerencias"].values() for s in lista}
        con_texto = {i for i in v.ids_visibles()
                     if _celda(v, i) and not _celda(v, i).startswith("↳")}
        assert con_texto == propias
        v.close()
    finally:
        c.close()

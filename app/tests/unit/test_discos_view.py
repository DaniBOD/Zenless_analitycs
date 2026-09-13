"""La pantalla Discos — offscreen, afirmando sobre lo que quedó a la vista.

Garantías:

1. **La tabla tiene todos los discos activos** (la vieja cortaba en 200) y **no tiene columna Score**.
2. **Un filtro reduce las filas** y el header dice cuántas quedan visibles.
3. **Click en una fila pide ESE disco** — también después de ordenar y filtrar, que es cuando un
   índice de fila deja de coincidir con la posición en la lista original.
4. **Click en un set del lateral lo filtra.**
5. Con la DB real, la vista entra en el ancho de la ventana mínima.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt                                # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

from app.tests.unit.test_discos_datos import _disco           # noqa: E402
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
    _disco(c, 13, 2, 2, descartado=1)
    _disco(c, 14, 1, 5, agente=1, equipado=1)
    return c


@pytest.fixture
def vista(qapp, con):
    v = DiscosView(con)
    v.resize(1100, 756)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def test_todas_las_filas_activas_y_sin_columna_score(vista):
    assert sorted(vista.ids_visibles()) == [10, 11, 12, 14]
    cabeceras = [h.upper() for h in vista.columnas()]
    assert not any("SCORE" in h for h in cabeceras), cabeceras
    for esperada in ("#ID", "SET", "SL", "MAIN", "SUBS", "NV", "ASIGNADO A", "ESTADO"):
        assert esperada in cabeceras


def test_orden_inicial_por_set_y_slot(vista):
    """Activar el orden en Qt ordena por la columna 0 descendente y pisaba el orden de diseño."""
    ids = vista.ids_visibles()
    assert ids == [12, 10, 11, 14], "Blues Libre (slot 1) primero, después Jazz Caótico por slot"


def test_header_dice_totales_y_visibles(vista, qapp):
    assert "4 discos" in vista.texto_header() and "2 equipados" in vista.texto_header()
    assert "2 libres" in vista.texto_header() and "4 visibles" in vista.texto_header()
    vista.filtros.chip("estado", "libre").click()
    qapp.processEvents()
    assert sorted(vista.ids_visibles()) == [11, 12]
    assert "2 visibles" in vista.texto_header()
    vista.filtros.limpiar()
    qapp.processEvents()
    assert len(vista.ids_visibles()) == 4


def test_filtros_combinados_con_combo(vista, qapp):
    vista.filtros.elegir("set", "Jazz Caótico")
    vista.filtros.chip("slot", 4).click()
    qapp.processEvents()
    assert sorted(vista.ids_visibles()) == [10, 11]


def test_click_en_fila_pide_ese_disco_despues_de_ordenar_y_filtrar(vista, qapp):
    pedidos = []
    vista.disco_pedido.connect(pedidos.append)
    vista.tabla.sortByColumn(vista.columnas().index("NV"), Qt.SortOrder.AscendingOrder)
    vista.filtros.chip("slot", 4).click()
    qapp.processEvents()
    ids = vista.ids_visibles()
    assert ids[0] == 11, "Nv 9 va primero al ordenar por nivel ascendente"
    vista.tabla.clicked.emit(vista.tabla.model().index(0, 0))
    qapp.processEvents()
    assert pedidos == [11]


def test_click_en_un_set_del_lateral_lo_filtra(vista, qapp):
    vista.lateral.boton_set("Blues Libre").click()
    qapp.processEvents()
    assert vista.ids_visibles() == [12]
    assert vista.filtros.seleccion()["set"] == {"Blues Libre"}


def test_libres_por_slot_en_el_lateral(vista):
    t = vista.lateral.textos_libres()
    assert t[4] == 1 and t[1] == 1 and t[5] == 0


def test_nivel_distinto_de_15_se_tine(vista):
    from app.ui.discos.tabla import AMBAR_NIVEL
    m = vista.tabla.model()
    col = vista.columnas().index("NV")
    for fila in range(m.rowCount()):
        disco_id = m.fila(fila).id
        color = m.data(m.index(fila, col), Qt.ItemDataRole.ForegroundRole)
        if disco_id == 11:
            assert color is not None and color.color().name().lower() == AMBAR_NIVEL.lower()


def test_la_vista_entra_en_la_ventana_minima(qapp):
    import glob
    from PySide6.QtGui import QFontDatabase
    fuentes = glob.glob(r"C:\Windows\Fonts\*.ttf")
    if not fuentes:
        pytest.skip("sin fuentes de Windows: el ancho medido no sería el real")
    for f in fuentes:
        QFontDatabase.addApplicationFont(f)
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        v = DiscosView(c)
        # 1320×820 menos sidebar (220), barra de título (40) y barra inferior (24) = 1100×756.
        # El alto también: la primera versión medía 1106 px porque el lateral listaba los 28 sets.
        assert v.minimumSizeHint().width() <= 1100, v.minimumSizeHint()
        assert v.minimumSizeHint().height() <= 756, v.minimumSizeHint()
        assert len(v.ids_visibles()) > 200, "la DB real tiene más de 200 activos: no hay tope"
        v.close()
    finally:
        c.close()

"""La pantalla Armas — offscreen, afirmando sobre lo que quedó a la vista.

Garantías:

1. **Una celda por arma física**, con el `×n` de copias del modelo.
2. **Refinamiento con mínimo 1** y, sin lectura, texto explícito: nunca cinco estrellas vacías.
3. **"Sin leer" y "por subir" son chips distintos** y no se suman entre sí.
4. Click en una celda la selecciona; click en el dueño pide su ficha.
5. El chip de auditoría "PJs sin arma" cambia el cuerpo por las tarjetas de esos PJs.
6. La vista entra en la ventana mínima (1100×756) con la DB real.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt                       # noqa: E402
from PySide6.QtTest import QTest                            # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea     # noqa: E402

from app.tests.unit.test_armas_datos import _arma            # noqa: E402
from app.ui.armas.view import ArmasView                      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO weapons (id, nombre, nombre_en, rareza, tipo_especialidad) VALUES
            (1, 'Llanto mielgo', 'Weeping Gemini', 'A', 'Anomalía'),
            (2, 'Sol exuvia', 'Sol Exuvia', 'S', 'Ataque');
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0),
            (3, 'Anby', 'A', 'Eléctrico', 'Aturdimiento', 'Cunning Hares', 0);
    """)
    _arma(c, 10, 1, agente=1, equipado=1)
    _arma(c, 11, 1, nivel=30, refin=2)
    _arma(c, 12, 2, nivel=None, refin=None)
    return c


@pytest.fixture
def vista(qapp, con):
    v = ArmasView(con)
    v.resize(1100, 756)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def _visibles(v):
    return [c for c in v.celdas() if c.isVisible()]


def test_una_celda_por_arma_fisica_con_sus_copias(vista):
    assert [c.fila.id for c in vista.celdas()] == [12, 10, 11], "S primero; después las dos copias"
    copias = {c.fila.id: c.textos_visibles() for c in vista.celdas()}
    assert "×2" in copias[10] and "×2" in copias[11], "dos copias del mismo modelo"
    assert "×2" not in copias[12]
    assert not vista.findChildren(QScrollArea), "la grilla se comprime, no scrollea"


def test_refinamiento_nunca_cinco_estrellas_vacias(vista):
    from app.ui.armas.celda import Refinamiento
    por_id = {c.fila.id: c for c in vista.celdas()}
    leido = por_id[11].findChild(Refinamiento)
    assert leido is not None and leido.refinamiento == 2 and leido.isVisibleTo(por_id[11])
    sin_leer = por_id[12].findChild(Refinamiento)
    assert sin_leer is None or not sin_leer.isVisibleTo(por_id[12])
    assert "P SIN LEER" in [t.upper() for t in por_id[12].textos_visibles()]
    assert "Nv sin leer" in por_id[12].textos_visibles()


def test_header_y_chips_separan_sin_leer_de_por_subir(vista):
    h = vista.texto_header()
    for frag in ("3 armas", "2 modelos", "1 equipada", "2 libres"):
        assert frag in h, (frag, h)
    assert vista.filtros.chip("auditoria", "nivel_bajo").text().endswith("1"), "sólo el Nv 30 leído"
    assert vista.filtros.chip("auditoria", "nivel_sin_leer").text().endswith("1")
    assert vista.filtros.chip("auditoria", "refin_bajo").text().endswith("1")


def test_un_filtro_oculta_celdas(vista, qapp):
    vista.filtros.chip("rareza", "A").click()
    qapp.processEvents()
    assert {c.fila.id for c in _visibles(vista)} == {10, 11}
    vista.filtros.chip("estado", "libre").click()
    qapp.processEvents()
    assert {c.fila.id for c in _visibles(vista)} == {11}
    vista.filtros.limpiar()
    qapp.processEvents()
    assert len(_visibles(vista)) == 3


def test_auditoria_nivel_sin_leer_no_trae_las_de_nivel_bajo(vista, qapp):
    vista.filtros.chip("auditoria", "nivel_sin_leer").click()
    qapp.processEvents()
    assert {c.fila.id for c in _visibles(vista)} == {12}


def test_click_en_celda_y_en_el_dueno(vista, qapp):
    elegidas, pjs = [], []
    vista.arma_elegida.connect(elegidas.append)
    vista.pj_pedido.connect(pjs.append)
    celda = next(c for c in vista.celdas() if c.fila.id == 11)
    QTest.mouseClick(celda, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    qapp.processEvents()
    assert elegidas == [11] and celda.seleccionada
    equipada = next(c for c in vista.celdas() if c.fila.id == 10)
    equipada.boton_dueno.click()
    qapp.processEvents()
    assert pjs == [1]


def test_el_chip_de_pjs_sin_arma_cambia_el_cuerpo(vista, qapp):
    assert vista.modo() == "grilla"
    vista.filtros.chip("auditoria", "pjs_sin_arma").click()
    qapp.processEvents()
    assert vista.modo() == "pjs"
    nombres = vista.textos_de_pjs()
    assert "Anby" in nombres, nombres
    assert _visibles(vista) == [], "la grilla de armas no se dibuja en este modo"
    vista.filtros.limpiar()
    qapp.processEvents()
    assert vista.modo() == "grilla" and len(_visibles(vista)) == 3


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
        v = ArmasView(c)
        assert v.minimumSizeHint().width() <= 1100, v.minimumSizeHint()
        assert v.minimumSizeHint().height() <= 756, v.minimumSizeHint()
        v.resize(1100, 756)
        v.show()
        qapp.processEvents()
        assert len(v.celdas()) == 56, "las 56 armas físicas"
        cuerpo = v.cuerpo.rect()
        for c_ in _visibles(v):
            assert cuerpo.contains(c_.geometry()), f"{c_.fila.nombre} se sale del cuerpo"
        v.close()
    finally:
        c.close()

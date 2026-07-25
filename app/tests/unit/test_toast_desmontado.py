"""Toast de tanda de desmontaje (variante 'desmontado').

Pedido explícito del usuario: **un solo toast al cerrar la tanda**, no uno por disco — "para que
el usuario sepa que el sistema está en armonía con lo que él realiza en el juego". En una limpieza
de 50 discos, 50 toasts serían inusables.

Va en la familia VIOLETA (confirmaciones pasivas): reporta algo que ya pasó, sin score ni
countdown, y **no afirma que la DB se haya escrito** — la bitácora va a un archivo y el feature es
observacional.

Muestra el desglose `N discos · M con datos` porque el hueco es información, no un detalle a
esconder: si el usuario clickeó rápido o usó selección masiva, tiene que ver que faltan stats.
"""
from __future__ import annotations

import os

import pytest

from app.ui import tokens as T


def test_la_variante_esta_configurada():
    v = T.variant("desmontado")
    assert v["label"] == "DESMONTADOS"
    assert v["color"] == T.PURPLE, "va en la familia de confirmaciones pasivas"
    assert v["icon"] == "trash"


def test_no_se_confunde_con_la_recomendacion_de_descartar():
    """`descartar` es un CONSEJO ("te conviene tirarlo"); `desmontado` es un HECHO observado ("ya
    los tiraste"). Si comparten color o label, el usuario no puede distinguirlos de un vistazo."""
    rec = T.variant("descartar")
    obs = T.variant("desmontado")
    assert rec["color"] != obs["color"]
    assert rec["label"] != obs["label"]


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    existing = QCoreApplication.instance()
    if existing is not None and not isinstance(existing, QApplication):
        pytest.skip("ya hay una QCoreApplication no-QApplication en el proceso")
    app = existing or QApplication([])
    yield app


def _data(total=7, known=5):
    from app.ui.toast import ToastData
    d = ToastData(set_name="—", slot=0, rarity="S")
    d.teardown_total = total
    d.teardown_known = known
    return d


def test_show_teardown_no_crashea(qapp):
    from app.ui.toast import DiscToast
    w = DiscToast()
    w.show_teardown(_data())
    assert w._data.variant == "desmontado"
    assert w.isVisible()
    w.repaint()               # fuerza el body
    w.hide()


def test_toast_sin_ninguno_con_datos(qapp):
    """Caso de selección masiva: 31 desmontados y 0 con datos. Tiene que pintarse igual."""
    from app.ui.toast import DiscToast
    w = DiscToast()
    w.show_teardown(_data(total=31, known=0))
    w.repaint()
    w.hide()

"""Toast REEMPLAZADO (swap de disco entre PJs): variante 'reemplazado' + `show_replacement`.

El body es propio (origen → disco → destino, sin score ni countdown, acento violeta). Smoke de
render con plataforma Qt offscreen; el chequeo de config del variant es puro.
"""
from __future__ import annotations

import os

import pytest


def test_variant_reemplazado_configurado():
    """La variante existe con el acento violeta e ícono swap (sin depender de Qt gráfico)."""
    from app.ui import tokens as T
    v = T.variant("reemplazado")
    assert v["label"] == "REEMPLAZADO"
    assert v["color"] == T.PURPLE
    assert v["icon"] == "swap"


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication
    inst = QCoreApplication.instance()
    # Un proceso puede tener QCoreApplication O QApplication, no ambas. Si otro test del suite ya
    # creó una QCoreApplication (p.ej. test_controller_graceful), no se puede crear una QApplication
    # de widgets acá → el smoke de render se saltea (corre igual standalone). Sin esto, la suite
    # completa crashea al finalizar (Qt widgets sobre una QCoreApplication → abort en teardown).
    if inst is not None and not isinstance(inst, QApplication):
        pytest.skip("ya existe una QCoreApplication en el proceso → no se puede crear QApplication de widgets")
    yield inst or QApplication([])


def test_show_replacement_no_crashea(qapp):
    """Smoke: mostrar el toast de swap no lanza y queda en variante 'reemplazado'."""
    from app.ui.toast import DiscToast, ToastData
    toast = DiscToast()
    data = ToastData(
        variant="reemplazado", set_name="Balada de la rama y la espada", slot=2, rarity="S",
        from_agent="Yixuan", target_agent="Nangong Yu", timeout_secs=3.0,
    )
    toast.show_replacement(data)
    assert toast._data.variant == "reemplazado"
    assert toast.isVisible()
    # Forzar un ciclo de pintado (el body de reemplazo) sin excepción.
    toast.repaint()
    toast.hide()


def test_show_replacement_sin_avatares_ni_logo(qapp):
    """Degradación: sin avatares/logo (assets faltantes) igual renderiza (placeholders)."""
    from app.ui.toast import DiscToast, ToastData
    toast = DiscToast()
    toast.show_replacement(ToastData(variant="reemplazado", set_name="X", slot=6,
                                     from_agent="A", target_agent="B"))
    toast.repaint()
    toast.hide()

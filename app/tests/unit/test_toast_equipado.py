"""Toast "AHORA EN" (disco LIBRE equipado a un PJ): variante 'equipado' + `show_equipped`.

Hermano de `test_toast_reemplazado`. Comparten familia visual (violeta, sin score ni countdown)
porque los dos reportan algo que YA pasó; se distinguen por el body — el reemplazo tiene dos PJs
y este uno solo, porque el disco no era de nadie.

La etiqueta NO es "EQUIPADO": en un toast de 380 px, esa palabra y "EQUIPAR" (la recomendación)
difieren en dos letras. "AHORA EN" describe el resultado y es imposible de confundir con un
consejo. El nombre del PJ va en el body, no en el header — ahí desbordaba contra el micro-badge
con nombres largos.
"""
from __future__ import annotations

import os

import pytest


def test_variant_equipado_configurado():
    """Misma familia violeta que REEMPLAZADO, etiqueta distinta (sin depender de Qt gráfico)."""
    from app.ui import tokens as T
    v = T.variant("equipado")
    assert v["label"] == "AHORA EN"
    assert v["color"] == T.PURPLE


def test_no_se_confunde_con_la_recomendacion_equipar():
    """El punto de todo el diseño: 'equipar' ACONSEJA, 'equipado' REPORTA. Distinto color y
    distinta etiqueta — si alguien iguala una a la otra, este test lo frena."""
    from app.ui import tokens as T
    rec, obs = T.variant("equipar"), T.variant("equipado")
    assert rec["color"] != obs["color"]
    assert rec["label"] != obs["label"]
    assert "EQUIPAD" not in obs["label"]     # ni siquiera parecida de lejos


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication
    inst = QCoreApplication.instance()
    # Ver la nota extensa en test_toast_reemplazado: QCoreApplication y QApplication no coexisten.
    if inst is not None and not isinstance(inst, QApplication):
        pytest.skip("ya existe una QCoreApplication en el proceso → no se puede crear QApplication de widgets")
    yield inst or QApplication([])


def test_show_equipped_no_crashea(qapp):
    from app.ui.toast import DiscToast, ToastData
    toast = DiscToast()
    toast.show_equipped(ToastData(
        set_name="Balada de la rama y la espada", slot=2, rarity="S",
        target_agent="Nangong Yu", timeout_secs=3.0,
    ))
    assert toast._data.variant == "equipado"
    assert toast.isVisible()
    toast.repaint()          # fuerza el body de 'equipado'
    toast.hide()


def test_show_equipped_sin_avatar_ni_logo(qapp):
    """Degradación: sin assets igual renderiza (placeholders)."""
    from app.ui.toast import DiscToast, ToastData
    toast = DiscToast()
    toast.show_equipped(ToastData(set_name="X", slot=6, target_agent="B"))
    toast.repaint()
    toast.hide()


def test_nombre_largo_no_rompe_el_render(qapp):
    """El motivo de dejar el nombre fuera del header: en el body se elide, en el label no."""
    from app.ui.toast import DiscToast, ToastData
    toast = DiscToast()
    toast.show_equipped(ToastData(set_name="Balada de la rama y la espada", slot=1,
                                  target_agent="Orfia y Magas"))
    toast.repaint()
    toast.hide()

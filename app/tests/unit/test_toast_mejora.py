"""Paso 8 (SPEC 2026-10-01): el toast de la sugerencia muestra la MEJORA real y sale sólo si mejora.

- Con `delta`: "MEJORA +0,57" (el formato de la columna de Discos), sin barra de URGENCIA ni `thr`,
  que salían del scoring sin calibrar.
- `MainWindow._on_disc_show_toast` no muestra nada si la sugerencia no pide toast.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from app.ui.toast import ToastData, bloque_puntaje, usa_urgencia


def test_con_mejora_el_bloque_dice_la_mejora_y_no_hay_urgencia():
    d = ToastData(variant="equipar", delta=0.57)
    assert bloque_puntaje(d) == ("MEJORA", "+0,57")
    assert not usa_urgencia(d)


def test_sin_mejora_queda_lo_de_antes():
    d = ToastData(variant="reserva", score=61.2)
    assert bloque_puntaje(d) == ("SCORE", "61.2")
    assert usa_urgencia(d)


class _ToastEspia:
    def __init__(self):
        self.mostrados = []

    def show_recommendation(self, td):
        self.mostrados.append(td)


def _main(payload):
    from app.main import MainWindow
    yo = SimpleNamespace(_toast=_ToastEspia())
    MainWindow._on_disc_show_toast(yo, payload)
    return yo._toast.mostrados


def test_sin_toast_en_la_sugerencia_no_se_muestra_nada():
    assert _main({"variant": "descartar", "sugerencia": {"toast": False, "tipo": "descartar"}}) == []
    assert _main({"variant": "reserva"}) == [], "un payload sin sugerencia tampoco interrumpe"


def test_con_toast_se_muestra_con_la_mejora():
    td, = _main({"variant": "equipar", "target": "Anby", "set": "Monarca del Pináculo", "slot": 4,
                 "sugerencia": {"toast": True, "tipo": "equipar", "mejora": 0.57, "destino": "Anby"}})
    assert (td.variant, td.target_agent, td.delta) == ("equipar", "Anby", 0.57)


# --- render ------------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    inst = QCoreApplication.instance()
    if inst is not None and not isinstance(inst, QApplication):
        pytest.skip("ya existe una QCoreApplication en el proceso → no se puede crear QApplication de widgets")
    yield inst or QApplication([])


def test_el_toast_con_mejora_se_pinta(qapp):
    from app.ui.toast import DiscToast
    toast = DiscToast()
    toast.show_recommendation(ToastData(variant="equipar", set_name="Monarca del Pináculo", slot=4,
                                        target_agent="Anby", delta=0.57, timeout_secs=3.0))
    assert toast.isVisible()
    toast.repaint()
    toast.hide()


def test_el_paint_usa_el_pie_sin_urgencia_cuando_hay_mejora(qapp, monkeypatch):
    """La función pura no alcanza: hay que ver que `paintEvent` la usa (A3)."""
    from app.ui.toast import DiscToast
    pintados = []
    monkeypatch.setattr(DiscToast, "_paint_footer", lambda self, *a: pintados.append("urgencia"))
    monkeypatch.setattr(DiscToast, "_paint_footer_static", lambda self, *a: pintados.append(a[4]))
    for delta in (0.57, None):
        toast = DiscToast()
        toast.show_recommendation(ToastData(variant="equipar", target_agent="Anby", delta=delta,
                                            timeout_secs=3.0))
        toast.grab()             # fuerza el paintEvent (repaint no pinta en offscreen)
        toast.hide()
    assert pintados[0] == "SUGERENCIA DEL MOTOR" and "urgencia" in pintados[1:]

"""Toast de W-Engine observado (variante 'arma_vista') — RF-15.

Va en la familia VIOLETA (confirmaciones pasivas): reporta algo que se vio en pantalla, sin score
ni countdown. El label dice **VISTO** y no "REGISTRADO" a propósito — este hito es observación pura
y no escribe la DB; un toast que insinuara lo contrario haría creer que el arma ya quedó
sincronizada.

El nombre puede venir CRUDO del OCR: `weapons` tiene 42 armas de menos, así que un arma sin
canonizar es el caso normal, no un error. Se muestra igual, porque el usuario reconoce el arma que
acaba de abrir.
"""
from __future__ import annotations

import os

import pytest

from app.ui import tokens as T


def test_la_variante_esta_configurada():
    v = T.variant("arma_vista")
    assert v["label"] == "W-ENGINE VISTO"
    assert v["color"] == T.PURPLE, "va en la familia de confirmaciones pasivas"


def test_el_label_no_afirma_que_se_registro():
    """La palabra importa. Este hito NO escribe la DB, y el toast sale igual en read-only."""
    label = T.variant("arma_vista")["label"].upper()
    for prohibida in ("REGISTRAD", "SINCRONIZ", "GUARDAD", "IMPORTAD"):
        assert prohibida not in label, f"'{prohibida}' promete una escritura que no ocurre"


def test_no_se_confunde_con_las_recomendaciones():
    """Las 4 variantes de recomendación aconsejan; esta reporta. Si comparten color, el usuario no
    las distingue de un vistazo."""
    obs = T.variant("arma_vista")
    for rec in ("equipar", "mejorar", "reserva", "descartar"):
        assert T.variant(rec)["color"] != obs["color"]
        assert T.variant(rec)["label"] != obs["label"]


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


def _data(nombre="Petrazufre", rareza="S", nivel="60/60", refin=1, stat="ATK% 30 %"):
    from app.ui.toast import ToastData
    d = ToastData(set_name="—", slot=0, rarity=rareza)
    d.weapon_name = nombre
    d.weapon_level = nivel
    d.weapon_refine = refin
    d.weapon_stat = stat
    return d


def test_show_weapon_no_crashea(qapp):
    from app.ui.toast import DiscToast
    w = DiscToast()
    w.show_weapon(_data())
    assert w._data.variant == "arma_vista"
    assert w.isVisible()
    w.repaint()               # fuerza el body
    w.hide()


def test_refinamiento_no_leido_no_pinta_estrellas_vacias(qapp):
    """Refinamiento 0 no existe en el juego (el mínimo es 1), así que 0 significa "no se pudo
    leer". Pintar cinco estrellas vacías se leería como refinamiento 0 y sería mentira."""
    from app.ui.toast import DiscToast
    w = DiscToast()
    w.show_weapon(_data(refin=0))
    w.repaint()
    assert w._data.weapon_refine == 0
    w.hide()


def test_nombre_crudo_y_campos_faltantes_no_crashean(qapp):
    """El caso normal de un arma fuera del catálogo, y el peor caso de OCR parcial."""
    from app.ui.toast import DiscToast
    w = DiscToast()
    w.show_weapon(_data(nombre="Arma Rara (sin catálogo)", rareza="?", nivel="", refin=0, stat=""))
    w.repaint()
    w.hide()

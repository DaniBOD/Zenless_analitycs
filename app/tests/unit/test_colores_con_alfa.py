"""Las marcas translúcidas se pintan del color que dicen, no de otro.

Qt lee un hex de 8 dígitos como `#AARRGGBB` (el alfa PRIMERO), también dentro de un stylesheet.
Pegarle el alfa al final (`AMBAR + "40"`, `{AMBAR}88`) no da "el mismo ámbar, translúcido": da
alfa F0 y color AA3C40, un rojo casi opaco. Ver
`Dev_IA/documentacion_cruda/2026-09/2026-09-24_FIX_El_alfa_pegado_al_hex_pinta_otro_color.md`.

Cada test captura el widget y compara el píxel de la marca contra la mezcla esperada: el color con
su alfa sobre el fondo que se MIDE al lado de la marca, no sobre uno supuesto.
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtGui import QColor                      # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

from app.ui.roster import celda as celda_roster       # noqa: E402
from app.ui.roster.celda import CeldaRoster           # noqa: E402
from app.ui.roster.datos import CeldaPJ               # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


def _mezcla(color: str, alfa: int, fondo: QColor) -> QColor:
    """`color` con opacidad `alfa` (0-255) sobre `fondo`, como compone Qt."""
    c, a = QColor(color), alfa / 255
    return QColor(*(round(a * x + (1 - a) * y) for x, y in
                    ((c.red(), fondo.red()), (c.green(), fondo.green()), (c.blue(), fondo.blue()))))


def _cerca(px: QColor, obj: QColor, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in ((px.red(), obj.red()), (px.green(), obj.green()),
                                              (px.blue(), obj.blue())))


def _relleno_de_la_esquina(img, lado: int) -> QColor:
    """El relleno de la esquina rayada (triángulo arriba a la derecha): entre raya y raya, el píxel
    más oscuro del interior. Se dejan afuera los bordes del triángulo y el borde del widget."""
    w = img.width()
    interior = [QColor(img.pixel(x, y)) for y in range(1, lado - 3)
                for x in range(w - lado + y + 2, w - 1)]
    return min(interior, key=lambda c: c.red() + c.green() + c.blue())


# --- Roster ------------------------------------------------------------------------------------

def _celda_pj(**kw) -> CeldaPJ:
    base = dict(id=9, nombre="X", rango="S", elemento="Eléctrico", rol="Ataque",
                faccion="Taller Flint", mindscape=0, nivel=60, discos=6, tiene_arma=True,
                sin_thresholds=False, variante_de=None, prioridad="normal")
    base.update(kw)
    return CeldaPJ(**base)


def _captura_roster(celda: CeldaPJ):
    w = CeldaRoster(celda)
    w.resize(122, 96)
    w.layout().activate()
    return w, w.grab().toImage()


def test_roster_la_esquina_de_faltan_datos_es_ambar_no_roja(qapp):
    _, img = _captura_roster(_celda_pj(sin_thresholds=True))
    lado = 13
    fondo = QColor(img.pixel(img.width() - lado - 2, 2))
    relleno = _relleno_de_la_esquina(img, lado)
    esperado = _mezcla(celda_roster.AMBAR, 0x40, fondo)
    assert _cerca(relleno, esperado), (relleno.name(), esperado.name())

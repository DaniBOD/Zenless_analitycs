"""`hit_test` — qué parte de la ventana frameless es borde, arrastre o contenido.

Es la única decisión del marco nativo que se puede testear sin Windows, y por eso se separó del
`nativeEvent`: si esta función se equivoca, la ventana no se deja redimensionar por una esquina o se
arrastra al hacer clic en un botón. El resto —que Windows respete lo que devuelve— se prueba a mano.
"""
from __future__ import annotations

import pytest

from app.ui.shell.window import (
    HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT, HTCAPTION, HTCLIENT, HTLEFT, HTRIGHT, HTTOP,
    HTTOPLEFT, HTTOPRIGHT, hit_test,
)

W, H, B = 1320, 820, 6


@pytest.mark.parametrize("x,y,esperado", [
    (0, 0, HTTOPLEFT), (W - 1, 0, HTTOPRIGHT), (0, H - 1, HTBOTTOMLEFT), (W - 1, H - 1, HTBOTTOMRIGHT),
    (0, 400, HTLEFT), (W - 1, 400, HTRIGHT), (600, 0, HTTOP), (600, H - 1, HTBOTTOM),
])
def test_bordes_y_esquinas(x, y, esperado):
    assert hit_test(x, y, W, H, border=B, maximized=False, en_caption=False) == esperado


def test_la_esquina_gana_al_lado():
    """Si el lado ganara, agarrar la esquina redimensionaría en un solo eje."""
    assert hit_test(2, 3, W, H, border=B, maximized=False, en_caption=True) == HTTOPLEFT


def test_el_borde_superior_gana_a_la_barra_de_titulo():
    """Los primeros px de arriba son resize aunque estén dentro de la barra: si no, no hay forma de
    estirar la ventana hacia arriba."""
    assert hit_test(600, 2, W, H, border=B, maximized=False, en_caption=True) == HTTOP


def test_la_barra_arrastra_y_el_contenido_no():
    assert hit_test(600, 20, W, H, border=B, maximized=False, en_caption=True) == HTCAPTION
    assert hit_test(600, 400, W, H, border=B, maximized=False, en_caption=False) == HTCLIENT


def test_maximizada_no_hay_bordes_de_resize():
    """Windows tampoco los ofrece; con bordes, el borde de arriba no dejaría arrastrar para
    des-maximizar."""
    assert hit_test(0, 0, W, H, border=B, maximized=True, en_caption=True) == HTCAPTION
    assert hit_test(0, 400, W, H, border=B, maximized=True, en_caption=False) == HTCLIENT

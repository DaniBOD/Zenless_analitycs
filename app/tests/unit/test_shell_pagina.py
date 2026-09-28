"""Una página fuera del sidebar en el shell (SPEC 2026-09-28, página del PJ).

La página del PJ no es una pestaña: tapa la vista activa hasta que se vuelve, y el sidebar sigue
mandando (tocar cualquier ítem, incluido el activo, la suelta). Hay una sola página a la vez.
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def ventana(qapp):
    from app.ui.shell.window import ShellWindow
    w = ShellWindow(install_native_frame=False)
    vistas = {k: QWidget() for k in ("roster", "armas")}
    for k, v in vistas.items():
        w.add_view(k, v)
    w.sidebar.select("roster")
    yield w, vistas
    w.close()


def _en_stack(w, widget) -> bool:
    return w.stack.indexOf(widget) != -1


def test_la_pagina_tapa_la_vista_y_volver_la_suelta(ventana):
    w, vistas = ventana
    p = QWidget()
    w.mostrar_pagina(p)
    assert w.current_view() is p and w.pagina_actual() is p
    w.volver()
    assert w.current_view() is vistas["roster"]
    assert w.pagina_actual() is None and not _en_stack(w, p)


def test_una_sola_pagina_a_la_vez(ventana):
    w, _ = ventana
    p1, p2 = QWidget(), QWidget()
    w.mostrar_pagina(p1)
    w.mostrar_pagina(p2)
    assert w.current_view() is p2 and not _en_stack(w, p1)


def test_el_sidebar_suelta_la_pagina(ventana):
    w, vistas = ventana
    p = QWidget()
    w.mostrar_pagina(p)
    w.sidebar.select("armas")
    assert w.current_view() is vistas["armas"]
    assert w.pagina_actual() is None and not _en_stack(w, p)


def test_tocar_el_item_activo_tambien_vuelve(ventana):
    w, vistas = ventana
    w.mostrar_pagina(QWidget())
    w.sidebar.select("roster")
    assert w.current_view() is vistas["roster"] and w.pagina_actual() is None

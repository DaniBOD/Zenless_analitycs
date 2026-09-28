"""El recuadro "Asesor" del modal de PJ (SPEC 2026-09-28) — datos y widget.

- Los avisos salen de `avisos_de` (la misma función que `ficha_pj.foto`), los "aviso" primero.
- Si el cálculo falla, la ficha lo dice ("no se pudieron calcular"): NO es lo mismo que no tener
  avisos (A2).
- Un "aviso" pinta el borde naranja; sólo "info", gris. Sin avisos: "Sin avisos.".
"""
from __future__ import annotations

import dataclasses
import logging
import os
import sys

import pytest

from app.core.coherencia import AVISO, INFO, Aviso
from app.tests.unit.test_pj_modal import con  # noqa: F401  (la misma DB de prueba)
from app.ui.pj_modal.datos import ficha_pj

A_DEF = Aviso(AVISO, "substat_no_te_beneficia", "DEF% no le suma nada a Yanagi.")
I_SET = Aviso(INFO, "set_fuera_de_guia", "El 4pc de Blues Libre está fuera de la guía de Yanagi.")


def test_sin_fijos_ni_guia_no_hay_avisos(con):  # noqa: F811
    assert ficha_pj(con, 1).avisos == ()


def test_un_fijo_sin_cumplir_llega_a_la_ficha(con):  # noqa: F811
    con.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (1, 'prob_critico', 50)")
    avisos = ficha_pj(con, 1).avisos
    assert [(a.severidad, a.tipo) for a in avisos] == [(INFO, "fijo_se_busca")]
    assert avisos[0].texto == "Prob. Crítica: 21,8 de 50 (faltan 28,2). El motor lo busca."


def test_los_avisos_van_antes_que_los_info(con, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.core.ficha_pj.avisos_de", lambda _c, _a: [I_SET, A_DEF])
    assert ficha_pj(con, 1).avisos == (A_DEF, I_SET)


def test_si_el_calculo_falla_la_ficha_lo_dice(con, monkeypatch, caplog):  # noqa: F811
    def rompe(_c, _a):
        raise RuntimeError("roto a propósito")
    monkeypatch.setattr("app.core.ficha_pj.avisos_de", rompe)
    with caplog.at_level(logging.ERROR):
        f = ficha_pj(con, 1)
    assert f is not None and f.avisos is None                # la ficha se arma igual
    assert "no se pudieron calcular los avisos" in caplog.text


# --- widget ------------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication(sys.argv)


def _modal(con, avisos):  # noqa: F811
    from app.ui.pj_modal.modal import PjModal
    return PjModal(dataclasses.replace(ficha_pj(con, 1), avisos=avisos))


def test_el_recuadro_con_avisos(qapp, con):  # noqa: F811
    from app.ui import tokens as T
    m = _modal(con, (A_DEF, I_SET))
    textos = m.textos_visibles()
    assert "Asesor · 2" in textos
    assert A_DEF.texto in textos and I_SET.texto in textos
    assert textos.index(A_DEF.texto) < textos.index(I_SET.texto)
    assert T.WARNING in m.caja_asesor.styleSheet()           # hay un "aviso": borde naranja
    m.close()


def test_solo_info_va_en_gris(qapp, con):  # noqa: F811
    from app.ui import tokens as T
    m = _modal(con, (I_SET,))
    assert "Asesor · 1" in m.textos_visibles()
    assert T.WARNING not in m.caja_asesor.styleSheet()
    m.close()


def test_sin_avisos_y_sin_calcular(qapp, con):  # noqa: F811
    m = _modal(con, ())
    assert "Asesor" in m.textos_visibles() and "Sin avisos." in m.textos_visibles()
    m.close()
    m = _modal(con, None)
    assert "no se pudieron calcular" in m.textos_visibles()
    assert "Sin avisos." not in m.textos_visibles()
    m.close()

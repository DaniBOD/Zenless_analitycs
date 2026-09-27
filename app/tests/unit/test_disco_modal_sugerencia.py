"""El recuadro "Sugerencia del motor" del modal de disco (SPEC 2026-09-27) — datos y widget.

Va donde el mockup tenía "Recomendación final", arriba de los otros discos del mismo set y slot:

- equipar: contra el disco que el PJ lleva HOY en ese slot, con sus datos;
- mover: de quién sale, quién repone y a quién va (con lo que lleva);
- cambiar 2pc: la nota y las dos piezas;
- reserva / guardar / descartar: el porqué;
- un disco que otra sugerencia nombra lo dice; sin nada: "está bien donde está".
"""
from __future__ import annotations

import os
import sys

import pytest

from app.core.sugerencias import SugerenciaDisco
from app.tests.unit.test_disco_modal import con  # noqa: F401  (la misma DB de prueba)
from app.ui.disco_modal.datos import PORQUE, detalle_sugerencia

EQUIPAR = {"tipo": "equipar", "disc_id": 12, "destino": "Yanagi", "destino_id": 1, "slot": 4,
           "delta": 0.57, "conflicto": None}
MOVER = {"tipo": "mover", "disc_id": 10, "destino": "Yanagi", "destino_id": 1, "slot": 4,
         "origen": "Lucy", "reemplazo_id": 11, "delta": 2.5, "conflicto": None}
PAR = {"tipo": "armar_2pc", "disc_id": 12, "disc_id_2": 15, "destino": "Anby", "destino_id": 1,
       "slot": 4, "delta": 1.0, "conflicto": None,
       "nota": "cambia tu 2pc de Disco Sacudestrellas por Jazz Oscilante para llegar a Prob. Crítica 50"}


def test_equipar_contra_lo_que_lleva_hoy(con):  # noqa: F811
    lineas = detalle_sugerencia(con, SugerenciaDisco(EQUIPAR))
    assert lineas[0].startswith("Hoy Yanagi lleva en el slot 4: #00010 Jazz Caótico")


def test_mover_de_quien_a_quien(con):  # noqa: F811
    lineas = detalle_sugerencia(con, SugerenciaDisco(MOVER))
    assert lineas[0].startswith("Sale de Lucy; lo repone #00011")
    assert lineas[1].startswith("Va a Yanagi, que hoy lleva: #00010")


def test_el_par_con_su_nota_y_sus_piezas(con):  # noqa: F811
    lineas = detalle_sugerencia(con, SugerenciaDisco(PAR))
    assert lineas[0].startswith("Cambia tu 2pc de Disco Sacudestrellas")      # sólo la 1.ª letra
    assert [l[:13] for l in lineas[1:]] == ["Pieza: #00012", "Pieza: #00015"]


@pytest.mark.parametrize("tipo", ["reserva", "guardar", "descartar"])
def test_el_porque_de_los_que_no_tienen_destino(con, tipo):  # noqa: F811
    s = {"tipo": tipo, "disc_id": 15, "conflicto": None}
    assert detalle_sugerencia(con, SugerenciaDisco(s)) == [PORQUE[tipo]]


def test_conflicto_y_lo_que_lo_nombra(con):  # noqa: F811
    conf = dict(EQUIPAR, conflicto="ese slot ya lo toma el disco #7")
    lineas = detalle_sugerencia(con, SugerenciaDisco(conf, (("repone", MOVER),)))
    assert "En conflicto: ese slot ya lo toma el disco #7." in lineas
    assert any("si #10 se mueve a Yanagi" in l for l in lineas)


# --- widget ------------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication(sys.argv)


class _Servicio:
    def __init__(self, ultimo):
        self.ultimo = ultimo


def _modal(con, disco_id, servicio):  # noqa: F811
    from app.ui.disco_modal.modal import DiscoModal
    return DiscoModal(con, disco_id, servicio=servicio)


def test_el_recuadro_con_la_sugerencia(qapp, con):  # noqa: F811
    m = _modal(con, 12, _Servicio({12: SugerenciaDisco(EQUIPAR)}))
    textos = m.textos_visibles()
    assert m.caja_sugerencia is not None
    assert "EQUIPAR → Yanagi +0,57" in textos
    assert any(t.startswith("Hoy Yanagi lleva en el slot 4") for t in textos)
    assert "Otros discos · slot 4 · Jazz Caótico".upper() in textos      # siguen abajo


def test_calculando_y_nada_que_hacer(qapp, con):  # noqa: F811
    assert "calculando…" in _modal(con, 12, _Servicio(None)).textos_visibles()
    assert any("está bien donde está" in t for t in _modal(con, 14, _Servicio({})).textos_visibles())


def test_sin_servicio_no_hay_recuadro(qapp, con):  # noqa: F811
    m = _modal(con, 12, None)
    assert m.caja_sugerencia is None
    assert not any("Sugerencia del motor".upper() in t for t in m.textos_visibles())


def test_al_cambiar_de_disco_cambia_la_sugerencia(qapp, con):  # noqa: F811
    m = _modal(con, 10, _Servicio({10: SugerenciaDisco(MOVER), 12: SugerenciaDisco(EQUIPAR)}))
    assert any(t.startswith("MOVER") for t in m.textos_visibles())
    m.boton_alternativa(12).click()
    assert any(t.startswith("EQUIPAR") for t in m.textos_visibles())
    assert not any(t.startswith("MOVER") for t in m.textos_visibles())

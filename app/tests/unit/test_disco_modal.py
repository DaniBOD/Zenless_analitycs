"""El modal de disco (mockup `23-modal-disco-detalle.png`) — datos y widget.

Decisiones de Daniel (2026-09-13) que se hacen cumplir:

- **Sólo informa**: sin chip de score, sin "PJs compatibles ranked", sin arquetipo, score
  proyectado, recomendación final ni historial, y sin los 5 botones del pie.
- **Columna 2 = el dueño con su build** y este slot destacado; un disco libre dice "LIBRE" y no
  dibuja hexágono (no hay build de nadie que mostrar).
- **Columna 3 = otros discos del mismo set y slot**, clickeables, sin score.
"""
from __future__ import annotations

import os
import sys

import pytest

from app.tests.unit.test_discos_datos import _disco
from app.ui.disco_modal.datos import FichaDisco, ficha_disco


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO disc_sets (id, nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc) VALUES
            (1, 'Jazz Caótico', 'Chaos Jazz', 'Maestría de Anomalía', '+30', 'Al activar Disorder genera energía.'),
            (2, 'Blues Libre', 'Freedom Blues', 'Maestría de Anomalía', '+30', 'Texto 4pc Blues');
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0);
    """)
    _disco(c, 10, 1, 4, agente=1, equipado=1)
    _disco(c, 11, 1, 4, nivel=9)
    _disco(c, 12, 1, 4)
    _disco(c, 14, 1, 5, agente=1, equipado=1)
    _disco(c, 15, 2, 4, subs=3)
    return c


# --- datos -------------------------------------------------------------------------------------

def test_ficha_de_un_disco_equipado(con):
    f = ficha_disco(con, 10)
    assert isinstance(f, FichaDisco)
    assert f.disco.id == 10 and f.disco.dueno == "Yanagi"
    assert f.bono_2p == "Maestría de Anomalía +30"
    assert f.bono_4p == "Al activar Disorder genera energía."
    assert sorted(f.build) == [4, 5], "el build del dueño sale de la misma fuente que el hexágono"
    assert [a.id for a in f.alternativas] == [12, 11]


def test_ficha_de_un_disco_libre_de_tres_subs(con):
    f = ficha_disco(con, 15)
    assert f.disco.dueno is None and f.build == {}
    assert len(f.disco.subs) == 3
    assert f.alternativas == []


def test_disco_inexistente_o_descartado(con):
    assert ficha_disco(con, 999) is None
    con.execute("UPDATE inventory_discs SET descartado = 1 WHERE id = 12")
    assert ficha_disco(con, 12) is None


# --- widget ------------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication(sys.argv)


def _modal(con, disco_id):
    from app.ui.disco_modal.modal import DiscoModal
    return DiscoModal(con, disco_id)


def test_sin_scoring_y_sin_botones_de_accion(qapp, con):
    from PySide6.QtWidgets import QPushButton
    m = _modal(con, 10)
    textos = " ".join(m.textos_visibles()).upper()
    for prohibido in ("SCORE", "RECOMENDACIÓN", "COMPATIBLES", "ARQUETIPO", "PROYECTADO", "HISTORIAL",
                      "BLOQUEAR", "DESCARTAR", "REASIGNAR", "MEJORAR", "CONFIRMAR"):
        assert prohibido not in textos, prohibido
    # Los únicos botones son: cerrar, el dueño (abre su ficha) y las alternativas (cambian de disco).
    acciones = [b.text() for b in m.findChildren(QPushButton)
                if b.objectName() not in ("alternativa", "dueno")]
    assert acciones == ["×"], acciones
    m.close()


def test_identidad_subs_y_efectos_del_set(qapp, con):
    m = _modal(con, 10)
    textos = m.textos_visibles()
    junto = " ".join(textos)
    assert "JAZZ CAÓTICO" in junto.upper() and "SLOT 4" in junto.upper()
    assert "EQUIPADO · Yanagi" in textos
    assert "Prob. Crítica" in textos and "2.4%" in textos
    assert "SUBSTATS · 4 ROLLS" in junto.upper()
    assert "Maestría de Anomalía +30" in junto and "Al activar Disorder genera energía." in junto
    m.close()


def test_equipado_dibuja_el_build_con_este_slot_destacado(qapp, con):
    m = _modal(con, 10)
    assert m.hexagono is not None and m.hexagono.isVisibleTo(m)
    assert m.hexagono.destacado() == 4
    assert sorted(m.hexagono.slots()) == [4, 5]
    m.close()


def test_libre_dice_libre_y_no_dibuja_hexagono(qapp, con):
    m = _modal(con, 15)
    assert "LIBRE" in m.textos_visibles()
    assert m.hexagono is None or not m.hexagono.isVisibleTo(m)
    assert "no hay otros discos de este set en este slot" in m.textos_visibles()
    subs = [t for t in m.textos_visibles() if t in ("Prob. Crítica", "ATK", "Perforación", "Daño Crítico")]
    assert subs == ["Prob. Crítica", "ATK", "Perforación"], "tres substats, no una cuarta fila vacía"
    m.close()


def test_click_en_una_alternativa_cambia_el_disco(qapp, con):
    m = _modal(con, 10)
    assert m.disco_id() == 10
    m.boton_alternativa(12).click()
    qapp.processEvents()
    assert m.disco_id() == 12
    assert "LIBRE" in m.textos_visibles()
    m.close()


def test_click_en_el_dueno_pide_su_ficha(qapp, con):
    m = _modal(con, 10)
    pedidos = []
    m.pj_pedido.connect(pedidos.append)
    m.boton_dueno.click()
    assert pedidos == [1]
    m.close()


def test_escape_cierra(qapp, con):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    m = _modal(con, 10)
    m.show()
    qapp.processEvents()
    QTest.keyClick(m, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not m.isVisible()

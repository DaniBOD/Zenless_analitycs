"""El modal de PJ (mockup `24-modal-pj-yanagi.png`, `pj-modal.jsx`) — datos y widget.

Decisiones de Daniel (2026-09-13) que estos tests hacen cumplir:

- **Sólo informa**: sin "Build completion %" y sin los 4 botones de acción. Los dos salen de un
  scoring que no está calibrado.
- **Stats vacías dicen "sin leer"**: desde la reconstrucción de la DB (17/08) están en NULL para los
  51 PJs. Un 0 o un número de ejemplo del mockup sería inventar (RNF-02).
- **El acento sale del elemento** (`tokens.color_elemento`).

La DB de prueba se arma con el ESQUEMA REAL (sólo los CREATE de `db/danibod_zzz_v2.db`) y filas
propias: así el test no depende de qué stats haya capturado Daniel hoy, pero sí se rompe si una
columna que el modal lee cambia de nombre.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

from app.ui.pj_modal.datos import FichaPJ, ficha_pj, formatear_stat, sets_de_build

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO disc_sets (id, nombre, nombre_en) VALUES
            (1, 'Jazz Caótico', 'Chaos Jazz'), (2, 'Blues Libre', 'Freedom Blues'),
            (3, 'Punk Primitivo', 'Proto Punk');
        INSERT INTO weapons (id, nombre, nombre_en, rareza) VALUES (7, 'Llanto mielgo', 'Weeping Gemini', 'S');
        INSERT INTO agents (id, nombre, rango, mindscape, elemento, rol, faccion, prob_critico,
                            dano_critico, pv, rec_energia, bono_dano_elemento, protected_build)
        VALUES
            (1, 'Yanagi', 'S', 0, 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6',
             21.8, 64.4, 10680, 1.2, 30.0, 0),
            (2, 'Nekomata', 'S', 2, 'Físico', 'Ataque', 'Cunning Hares',
             NULL, NULL, NULL, NULL, NULL, 0);
        INSERT INTO inventory_weapons (weapon_id, nivel, refinamiento, agente_asignado, equipado, descartado)
            VALUES (7, 60, 5, 1, 1, 0);
        INSERT INTO agent_awakenings (agente_id, nivel, nombre, activo) VALUES (1, 4, 'Boiling Point Party', 1);
    """)
    for slot, set_id in ((1, 2), (2, 2), (3, 1), (4, 1), (5, 1), (6, 1)):
        c.execute("INSERT INTO inventory_discs (set_id, slot, main_stat, nivel, agente_asignado,"
                  " equipado, descartado) VALUES (?, ?, 'x', 15, 1, 1, 0)", (set_id, slot))
    for slot in (1, 2, 3, 4, 5):                       # Nekomata: 5 discos sueltos
        c.execute("INSERT INTO inventory_discs (set_id, slot, main_stat, nivel, agente_asignado,"
                  " equipado, descartado) VALUES (?, ?, 'x', 9, 2, 1, 0)", ((slot % 3) + 1, slot))
    return c


# --- datos -------------------------------------------------------------------------------------

def test_sets_de_build_cuenta_piezas_sin_forzar():
    s = lambda *nombres: {i + 1: {"set": n} for i, n in enumerate(nombres)}   # noqa: E731
    assert sets_de_build(s("A", "A", "B", "A", "A", "B")) == [("A", 4), ("B", 2)]
    assert sets_de_build(s("A", "B", "C", "D", "E", "F")) == [], "6 sueltos: no hay bonus que mostrar"
    assert sets_de_build(s("A", "A", "A", "A", "B")) == [("A", 4)], "5 discos: la pieza suelta no es un set"
    assert sets_de_build(s("A", "A", "B", "B", "C", "C")) == [("A", 2), ("B", 2), ("C", 2)]
    assert sets_de_build({1: {"set": None}, 2: {"set": None}}) == []


def test_formatear_stat_nunca_inventa():
    assert formatear_stat("prob_critico", None) is None
    assert formatear_stat("prob_critico", 21.8) == "21.8%"
    assert formatear_stat("pv", 10680) == "10.680"
    assert formatear_stat("rec_energia", 1.2) == "1.20"


def test_ficha_de_un_pj_con_build_arma_y_despertar(con):
    f = ficha_pj(con, 1)
    assert isinstance(f, FichaPJ)
    assert f.nombre == "Yanagi" and f.mindscape == 0
    assert sorted(f.slots) == [1, 2, 3, 4, 5, 6]
    assert f.sets == [("Jazz Caótico", 4), ("Blues Libre", 2)]
    assert f.arma is not None and (f.arma.nombre, f.arma.nivel, f.arma.refinamiento) == ("Llanto mielgo", 60, 5)
    assert f.despertar == 4
    assert dict(f.stats)["Prob. Crítico"] == "21.8%"
    assert f.bono == "Bono Eléctrico 30%"


def test_ficha_de_un_pj_sin_stats_sin_arma_sin_despertar(con):
    f = ficha_pj(con, 2)
    assert all(v is None for _k, v in f.stats), "sin leer, no ceros"
    assert f.arma is None
    assert f.despertar is None, "sin fila ≠ nivel 0"
    assert f.bono is None
    assert len(f.slots) == 5
    # 2 Blues + 2 Punk + 1 Jazz: los dos pares SON bonos de 2 piezas; la pieza suelta no aparece.
    assert f.sets == [("Blues Libre", 2), ("Punk Primitivo", 2)]


def test_pj_inexistente_devuelve_none(con):
    assert ficha_pj(con, 999) is None


def test_el_armero_muestra_laceracion_y_afiladura_en_vez_de_atk_y_er(con):
    """Claret Flint (v3.2): su ficha no tiene ATK ni Recup. Energía. Mostrar esas filas vacías
    diría "sin leer" de dos stats que el PJ no tiene."""
    con.execute("INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, pv, "
                "dano_laceracion, acumulacion_afiladura, protected_build) VALUES "
                "(3, 'Claret Flint', 'S', 'Eléctrico', 'Armero', 'Flint Workshop', 8360, 150.0, 1.5, 0)")
    f = ficha_pj(con, 3)
    etiquetas = dict(f.stats)
    assert etiquetas["Laceración"] == "150.0%"
    assert etiquetas["Afiladura"] == "1.50"
    assert "Ataque" not in etiquetas and "Recup. Energía" not in etiquetas
    assert f.stats_crudos["dano_laceracion"] == 150.0


# --- widget ------------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication(sys.argv)


def test_el_modal_no_muestra_scoring_ni_botones_de_accion(qapp, con):
    from PySide6.QtWidgets import QPushButton
    from app.ui.pj_modal.modal import PjModal
    m = PjModal(ficha_pj(con, 1))
    textos = " ".join(m.textos_visibles()).upper()
    for prohibido in ("BUILD COMPLETION", "OPTIMIZAR", "SUGERIR EQUIPO", "VER RUNS", "% COMPLETION"):
        assert prohibido not in textos
    botones = [b.text() for b in m.findChildren(QPushButton)]
    # Cerrar y, desde la mig 42, los tres segmentos del selector de prioridad (Daniel, 2026-09-24:
    # la prioridad se edita en la app). Ningún botón de acción del mockup.
    assert botones == ["×", "▲ Alta", "Normal", "▼ Baja"], f"sólo cerrar y la prioridad: {botones}"
    assert "YANAGI" in textos and "LLANTO MIELGO" in textos and "P5" in textos
    assert "4 PIEZAS" in textos and "2 PIEZAS" in textos
    m.close()


def test_stats_vacias_dicen_sin_leer_y_ningun_numero(qapp, con):
    from app.ui.pj_modal.modal import PjModal
    m = PjModal(ficha_pj(con, 2))
    stats = m.textos_de_stats()
    assert stats and all(v == "sin leer" for v in stats.values()), stats
    textos = m.textos_visibles()
    assert "sin arma equipada" in textos
    assert "sin registro" in textos
    m.close()


def test_el_modal_del_armero_dibuja_sus_filas(qapp, con):
    from app.ui.pj_modal.modal import PjModal
    con.execute("INSERT INTO agents (id, nombre, rango, elemento, rol, protected_build, "
                "dano_laceracion, acumulacion_afiladura) VALUES "
                "(3, 'Claret Flint', 'S', 'Eléctrico', 'Armero', 0, 150.0, 1.5)")
    m = PjModal(ficha_pj(con, 3))
    stats = m.textos_de_stats()
    assert stats.get("Laceración") == "150.0%" and stats.get("Afiladura") == "1.50", stats
    m.close()


def test_la_x_y_escape_cierran(qapp, con):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from app.ui.pj_modal.modal import PjModal
    m = PjModal(ficha_pj(con, 1))
    m.show()
    qapp.processEvents()
    m.btn_cerrar.click()
    qapp.processEvents()
    assert not m.isVisible()
    m2 = PjModal(ficha_pj(con, 1))
    m2.show()
    qapp.processEvents()
    QTest.keyClick(m2, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not m2.isVisible()


def test_el_acento_sale_del_elemento(qapp, con):
    from app.ui import tokens as T
    from app.ui.pj_modal.modal import PjModal
    m = PjModal(ficha_pj(con, 1))
    assert m.acento == T.color_elemento("Eléctrico")
    m.close()

"""La página del PJ (SPEC 2026-09-28) — la build declarada, sus avisos y la navegación.

Sobre una COPIA de la DB de dominio (los PJs con guía son los reales; lo que escribe va a la copia).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFrame, QLabel   # noqa: E402

from app.core.coherencia import AVISO, INFO, Aviso    # noqa: E402
from app.core.ficha_pj import EditorFichaPJ, leer_eleccion_pj  # noqa: E402
from app.db.repositories import agentes_cambiaron     # noqa: E402
from app.ui.pj_pagina.datos import BLOQUE_DE_AVISO, BLOQUES, avisos_por_bloque, pagina_pj  # noqa: E402
from app.ui.pj_pagina.pagina import PjPagina          # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    p = tmp_path / "copia.db"
    shutil.copy(DB_REAL, p)
    agentes_cambiaron()
    yield p
    agentes_cambiaron()


@pytest.fixture
def con(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _id(con, nombre):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


def _pagina(con, db, nombre, **kw):
    pid = _id(con, nombre)
    return PjPagina(lambda: pagina_pj(con, pid), editor=EditorFichaPJ(db), db_path=db, **kw)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- los avisos por bloque ---------------------------------------------------------------------

def test_cada_tipo_del_asesor_tiene_su_bloque():
    fuente = (RAIZ / "app" / "core" / "coherencia.py").read_text(encoding="utf-8")
    tipos = set(re.findall(r'Aviso\([A-Z]+, "([a-z0-9_]+)"', fuente))
    assert tipos and tipos <= set(BLOQUE_DE_AVISO), tipos - set(BLOQUE_DE_AVISO)


def test_un_tipo_desconocido_va_a_otros_y_no_se_pierde():
    a = Aviso(INFO, "tipo_que_no_existe", "x")
    b = Aviso(AVISO, "substat_no_te_beneficia", "y")
    por = avisos_por_bloque([a, b])
    assert set(por) == set(BLOQUES)
    assert por["otros"] == [a] and por["secundarios"] == [b]
    assert sum(len(v) for v in por.values()) == 2


# --- la página ---------------------------------------------------------------------------------

def test_anby_su_build_declarada_y_los_avisos_debajo_de_fijos(qapp, con, db):
    m = _pagina(con, db, "Anby")
    textos = m.textos_visibles()
    assert "← Roster" == m.btn_volver.text()
    assert "Hoy en el juego" in textos and "Build declarada" in textos
    assert any(t.startswith("4pc Monarca del Pináculo") for t in textos)
    assert "ℹ 2" in textos
    assert set(m.boton_editar) == {"sets", "principales", "secundarios", "fijos"}
    en_fijos = [l.text() for l in m.findChild(QFrame, "bloque_fijos").findChildren(QLabel)]
    assert any("Prob. Crítica: 48,2 de 50" in t and "el motor lo busca" in t for t in en_fijos)
    assert any(t.startswith("Prob. Crítica: 48,2 de 50 (faltan 1,8)") for t in en_fijos)
    m.close()


def test_si_la_build_declarada_falla_la_pagina_se_arma_y_lo_dice(qapp, con, db, monkeypatch, caplog):
    def rompe(_c, _i):
        raise RuntimeError("roto a propósito")
    monkeypatch.setattr("app.ui.pj_pagina.datos.foto", rompe)
    with caplog.at_level(logging.ERROR):
        m = _pagina(con, db, "Anby")
    assert m.datos.foto is None
    assert any("No se pudo leer la build declarada" in t for t in m.textos_visibles())
    assert "no se pudo leer la build declarada" in caplog.text
    assert m.textos_de_stats()                                  # lo de hoy está igual
    m.close()


def test_todo_a_la_guia_pide_confirmacion(qapp, con, db):
    a = _id(con, "Ellen")
    EditorFichaPJ(db).nivel_substat(a, "DEF%", 1)
    antes = _sha(db)
    m = _pagina(con, db, "Ellen", confirmar=lambda: False)
    m.btn_todo_guia.click()
    assert _sha(db) == antes and leer_eleccion_pj(con, a).niveles == {"DEF%": 1}
    m.close()
    m = _pagina(con, db, "Ellen", confirmar=lambda: True)
    assert any("DEF% (tuyo)" in t for t in m.textos_visibles())
    m.btn_todo_guia.click()
    assert leer_eleccion_pj(con, a).niveles == {}
    assert not any("DEF% (tuyo)" in t for t in m.textos_visibles()), "la página se refrescó"
    m.close()


def test_en_solo_lectura_todo_a_la_guia_no_se_puede_tocar(qapp, con, db, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    m = _pagina(con, db, "Ellen", confirmar=lambda: True)
    assert not m.btn_todo_guia.isEnabled()
    m.close()


def test_un_pj_sin_guia_lo_dice(qapp, con, db):
    """Hoy los 52 tienen guía: se le borra la suya a Anby en la copia (un PJ recién salido)."""
    a = _id(con, "Anby")
    for tabla in ("pj_stats_recomendados", "pj_sets_2pc", "pj_sets_4pc"):
        con.execute(f"DELETE FROM {tabla} WHERE agente_id = ?", (a,))
    con.commit()
    agentes_cambiaron()
    m = _pagina(con, db, "Anby")
    assert "Sin guía todavía: se puede declarar igual." in m.textos_visibles()
    assert any(t.startswith("Slot 4: ") for t in m.textos_visibles())
    m.close()


# --- navegación en la ventana (MainWindow verdadera, sólo lectura) -----------------------------

def test_desde_el_modal_del_disco_se_cierra_el_modal_y_vuelve_a_discos(qapp, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    monkeypatch.setenv("DANIBOD_NO_AUTOSTART", "1")
    from app.ui.disco_modal import modal as DM
    cerrados = []

    def exec_simulado(self):
        self.accepted.connect(lambda: cerrados.append(True))
        self.pj_pedido.emit(self._ficha.disco.dueno_id)
        return 0
    monkeypatch.setattr(DM.DiscoModal, "exec", exec_simulado)
    from app.main import MainWindow
    w = MainWindow()
    try:
        w.show_view("discos")
        c = sqlite3.connect(f"file:{DB_REAL.as_posix()}?mode=ro", uri=True)
        disco = c.execute("SELECT id FROM inventory_discs WHERE equipado = 1 AND descartado = 0 "
                          "AND agente_asignado IS NOT NULL LIMIT 1").fetchone()[0]
        c.close()
        w._abrir_ficha_disco(disco)
        assert cerrados == [True]
        pagina = w.pagina_actual()
        assert isinstance(pagina, PjPagina) and pagina.btn_volver.text() == "← Discos"
        pagina.volver_pedido.emit()
        assert w.current_view() is w._discos_view
    finally:
        w._tray.hide()
        w.close()
        w.deleteLater()


def test_el_origen_de_los_sets_dice_de_donde_sale_el_2pc(qapp, con, db):
    """Con el 4pc equipado, el motor toma el 2pc equipado o, si no hay uno completo puesto, el
    recomendado de la guía. Ellen lleva los dos; Anby lleva Monarca sin un 2pc completo."""
    ellen = _pagina(con, db, "Ellen")
    assert "los dos, los que tiene equipados" in ellen.textos_visibles()
    anby = _pagina(con, db, "Anby")
    assert "el 4pc que tiene equipado · el 2pc, el recomendado de la guía" in anby.textos_visibles()
    ellen.close()
    anby.close()

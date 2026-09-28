"""El selector de prioridad en la ficha del PJ (paso 5; handoff design_v3).

Desde el 2026-09-28 la ficha es una PÁGINA (el modal se retiró): el selector sigue arriba a la
derecha de la portada.

- Arriba a la derecha de la portada.
- Muestra la prioridad guardada y la nota de qué implica.
- Un click guarda (en la DB, con `EditorPrioridades`: un backup por ficha abierta) y avisa
  `prioridad_cambiada`; el Roster actualiza esa celda en el lugar.
- Si no se guardó, el segmento no queda tildado. En solo lectura, no se puede tocar.

Sobre una COPIA de la DB de dominio, en archivo (el editor escribe con su propia conexión).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication            # noqa: E402

from app.ui.pj_pagina.datos import pagina_pj         # noqa: E402
from app.ui.pj_pagina.hoy import PRIO_NOTA            # noqa: E402
from app.ui.pj_pagina.pagina import PjPagina          # noqa: E402

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    p = tmp_path / "copia.db"
    shutil.copy(DB_REAL, p)
    c = sqlite3.connect(p)
    c.execute("DELETE FROM ajustes_usuario_prioridad")
    c.commit()
    c.close()
    return p


@pytest.fixture
def con(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _id(con, nombre):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


def _en_db(db):
    c = sqlite3.connect(db)
    try:
        return dict(c.execute("SELECT agente_id, prioridad FROM ajustes_usuario_prioridad"))
    finally:
        c.close()


def _modal(con, db, nombre="Claret Flint"):
    pid = _id(con, nombre)
    return PjPagina(lambda: pagina_pj(con, pid), db_path=db)


def _tildados(m):
    return [k for k, b in m.selector_prioridad.botones.items() if b.isChecked()]


def test_la_ficha_lee_la_prioridad_guardada(qapp, con, db):
    con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, 'alta')",
                (_id(con, "Claret Flint"),))
    con.commit()
    m = _modal(con, db)
    assert m.ficha.prioridad == "alta" and _tildados(m) == ["alta"]
    assert m.selector_prioridad.nota.text() == PRIO_NOTA["alta"]


def test_va_arriba_a_la_derecha_de_la_portada(qapp, con, db):
    m = _modal(con, db)
    m.resize(1100, 740)
    m.show()
    qapp.processEvents()
    sel, portada = m.selector_prioridad.geometry(), m.portada.rect()
    assert portada.right() - sel.right() == 14 and sel.top() == 14
    m.close()


def test_un_click_guarda_avisa_y_dice_que_se_recalculo(qapp, con, db):
    m = _modal(con, db, "Piper")
    avisos = []
    m.prioridad_cambiada.connect(lambda i, p: avisos.append((i, p)))
    m.selector_prioridad.botones["baja"].click()
    pid = _id(con, "Piper")
    assert _en_db(db) == {pid: "baja"} and avisos == [(pid, "baja")]
    assert _tildados(m) == ["baja"] and "recalculadas" in m.selector_prioridad.nota.text()
    m.selector_prioridad.botones["normal"].click()
    assert _en_db(db) == {} and avisos[-1] == (pid, "normal")


def test_un_backup_por_ficha_abierta_y_nada_si_no_cambia(qapp, con, db):
    m = _modal(con, db, "Piper")
    m.selector_prioridad.botones["normal"].click()           # ya era normal: no escribe
    assert list(db.parent.glob("copia.backup_preprioridad_*.db")) == []
    m.selector_prioridad.botones["alta"].click()
    m.selector_prioridad.botones["baja"].click()
    assert len(list(db.parent.glob("copia.backup_preprioridad_*.db"))) == 1


def test_si_no_se_guardo_no_queda_tildado(qapp, con, db, monkeypatch):
    m = _modal(con, db, "Piper")
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    m.selector_prioridad.botones["alta"].click()
    assert _en_db(db) == {} and _tildados(m) == ["normal"]
    assert "No se guardó" in m.selector_prioridad.nota.text()


def test_en_solo_lectura_no_se_puede_tocar(qapp, con, db, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    m = _modal(con, db, "Piper")
    assert not any(b.isEnabled() for b in m.selector_prioridad.botones.values())
    assert "solo lectura" in m.selector_prioridad.nota.text()


def test_la_ventana_engancha_la_pagina_al_roster_y_vuelve(qapp, monkeypatch):
    """`MainWindow._abrir_ficha_pj` VERDADERO: abre la página, que tiene que llegar al Roster, y
    "←" vuelve. Solo lectura (el cambio de prioridad se simula con la señal)."""
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    monkeypatch.setenv("DANIBOD_NO_AUTOSTART", "1")
    from app.main import MainWindow
    w = MainWindow()
    try:
        w.show_view("roster")
        celda = next(c for c in w._roster_view.celdas() if c.celda.prioridad == "normal")
        w._abrir_ficha_pj(celda.celda.id)
        pagina = w.pagina_actual()
        assert isinstance(pagina, PjPagina) and w.current_view() is pagina
        assert pagina.btn_volver.text() == "← Roster"
        pagina.prioridad_cambiada.emit(celda.celda.id, "alta")
        assert celda.prioridad == "alta"
        pagina.volver_pedido.emit()
        assert w.current_view() is w._roster_view and w.pagina_actual() is None
    finally:
        w._tray.hide()
        w.close()
        w.deleteLater()


def test_el_roster_actualiza_la_celda_cuando_cambia_en_la_ficha(qapp, con, db):
    """Lo que hace la ventana (`main._abrir_ficha_pj`): conecta la ficha al Roster."""
    from app.ui.roster.view import RosterView
    v = RosterView(con, db_path=db)
    v.filtros.chip("elemento", "Físico").setChecked(True)
    m = _modal(con, db, "Piper")
    m.prioridad_cambiada.connect(v.prioridad_actualizada)
    celda = next(c for c in v.celdas() if c.celda.nombre == "Piper")
    m.selector_prioridad.botones["baja"].click()
    assert celda.prioridad == "baja" and next(c for c in v.celdas() if c.celda.nombre == "Piper") is celda
    assert v.filtros.chip("prioridad", "baja").text() == "▼ Baja 1"
    assert v.filtros.chip("elemento", "Físico").isChecked(), "no se perdió el filtro"

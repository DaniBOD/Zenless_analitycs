"""El modo "Editar prioridades" del Roster (handoff design_v3) — offscreen, sobre una DB en archivo.

- **Estado vacío**: el chip "Sin declarar · Marcar ▸", la etiqueta NUEVO y la nota de la leyenda
  dicen que la función existe; el chip entra al modo edición.
- **En modo edición**: el header cambia (obvio en qué modo estás), la botonera reemplaza nivel y
  discos, y el click en la celda NO pide la ficha. Se sale con Listo o Esc.
- **Un click guarda al momento** (en la DB, no sólo en pantalla) y la celda, los conteos, el filtro
  y la leyenda se actualizan EN EL LUGAR: los filtros elegidos no se pierden.
- **Si no se guardó** (solo lectura), la celda no muestra un valor que no quedó en la DB.
- **Solo lectura**: el botón no deja entrar.
- **El ancho**: con prioridades y en modo edición la vista sigue entrando en 1100 px.
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt                 # noqa: E402
from PySide6.QtTest import QTest                      # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from app.ui.roster.view import RosterView            # noqa: E402

_ESQUEMA = """
    CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rango TEXT, nivel INTEGER,
        mindscape INTEGER, elemento TEXT, rol TEXT, faccion TEXT);
    CREATE TABLE agent_thresholds (id INTEGER PRIMARY KEY, agente_id INTEGER, stat TEXT);
    CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
        equipado INTEGER, descartado INTEGER);
    CREATE TABLE inventory_weapons (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
        equipado INTEGER, descartado INTEGER);
    CREATE TABLE ajustes_usuario_prioridad (
        agente_id INTEGER PRIMARY KEY REFERENCES agents(id),
        prioridad TEXT NOT NULL CHECK (prioridad IN ('alta', 'baja')),
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP);
    INSERT INTO agents VALUES
        (1, 'Claret Flint', 'S', 60, 0, 'Eléctrico', 'Armero', 'Taller Flint'),
        (2, 'Piper', 'A', 60, 0, 'Físico', 'Anomalía', 'Sons of Calydon'),
        (3, 'Lycaon', 'S', 60, 0, 'Hielo', 'Aturdimiento', 'Victoria Housekeeping');
    INSERT INTO agent_thresholds (agente_id, stat) VALUES (1,'x'),(2,'x'),(3,'x');
"""


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    p = tmp_path / "roster.db"
    c = sqlite3.connect(p)
    c.executescript(_ESQUEMA)
    c.commit()
    c.close()
    return p


@pytest.fixture
def vista(qapp, db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    v = RosterView(con, db_path=db)
    v.resize(1300, 800)
    v.show()
    qapp.processEvents()
    yield v
    v.close()
    con.close()


def _celda(v, nombre):
    return next(c for c in v.celdas() if c.celda.nombre == nombre)


def _en_db(db):
    c = sqlite3.connect(db)
    try:
        return dict(c.execute("SELECT agente_id, prioridad FROM ajustes_usuario_prioridad"))
    finally:
        c.close()


# --- estado vacío ------------------------------------------------------------------------------

def test_vacio_invita_a_marcar(vista):
    assert not vista.filtros.btn_marcar.isHidden()
    assert all(vista.filtros.chip("prioridad", k).isHidden() for k in ("alta", "normal", "baja"))
    assert not vista._nuevo.isHidden()
    assert "NO SABE A QUIÉN QUERÉS MEJORAR" in vista._nota.text() and "LOS 3" in vista._nota.text()


def test_la_etiqueta_nuevo_no_se_estira_al_alto_del_header(vista):
    """Primera captura: el label tomaba los 56 px del header y era un bloque lima vertical."""
    assert vista._nuevo.height() <= 20, vista._nuevo.height()


def test_el_chip_vacio_entra_al_modo_edicion(vista):
    vista.filtros.btn_marcar.click()
    assert vista.editando and not vista._header_edit.isHidden() and vista._header.isHidden()


# --- modo edición --------------------------------------------------------------------------------

def test_en_modo_edicion_la_botonera_reemplaza_nivel_y_discos(vista):
    vista.btn_prioridades.click()
    c = _celda(vista, "Piper")
    assert not c.botonera.isHidden() and c._nivel.isHidden() and c._discos.isHidden()
    assert "MODO EDICIÓN" in vista._nota.text()


def test_en_modo_edicion_el_click_no_pide_la_ficha(vista, qapp):
    pedidas = []
    vista.ficha_pedida.connect(pedidas.append)
    vista.btn_prioridades.click()
    c = _celda(vista, "Lycaon")
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(60, 30))
    assert pedidas == []
    vista.btn_listo.click()
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(60, 30))
    assert pedidas == [c.celda.id], "fuera del modo, el click vuelve a pedir la ficha"


def test_un_click_guarda_en_la_db_y_actualiza_todo_en_el_lugar(vista, db):
    vista.filtros.chip("elemento", "Eléctrico").setChecked(True)     # un filtro elegido
    vista.btn_prioridades.click()
    c = _celda(vista, "Claret Flint")
    c.botonera.botones["alta"].click()
    assert _en_db(db) == {1: "alta"}
    assert c.prioridad == "alta" and c.botonera.valor == "alta"
    assert not c._guardado.isHidden()
    assert "RECALCULADAS" in vista._estado_prio.text()
    assert vista.filtros.chip("prioridad", "alta").text() == "▲ Alta 1"
    assert vista.filtros.btn_marcar.isHidden() and vista._nuevo.isHidden()
    assert not any(i.isHidden() for i in vista._leyenda_prio.values())
    assert vista.filtros.chip("elemento", "Eléctrico").isChecked(), "no se perdió el filtro"
    assert _celda(vista, "Claret Flint") is c, "la celda se actualizó, no se rearmó la grilla"


def test_volver_a_normal_borra_la_fila(vista, db):
    vista.btn_prioridades.click()
    c = _celda(vista, "Piper")
    c.botonera.botones["baja"].click()
    assert _en_db(db) == {2: "baja"}
    c.botonera.botones["normal"].click()
    assert _en_db(db) == {} and c.prioridad is None


def test_un_backup_por_sesion_de_edicion(vista, db):
    vista.btn_prioridades.click()
    _celda(vista, "Claret Flint").botonera.botones["alta"].click()
    _celda(vista, "Piper").botonera.botones["baja"].click()
    assert len(list(db.parent.glob("roster.backup_preprioridad_*.db"))) == 1


def test_si_no_se_guardo_la_celda_no_lo_muestra(vista, db, monkeypatch):
    vista.btn_prioridades.click()
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    c = _celda(vista, "Piper")
    c.botonera.botones["baja"].click()
    assert _en_db(db) == {}
    assert c.prioridad is None
    # Lo que se VE: el segmento tildado, no un atributo interno (un sabotaje que dejaba "baja"
    # tildado pasaba en verde mirando `botonera.valor`).
    assert [k for k, b in c.botonera.botones.items() if b.isChecked()] == ["normal"]
    assert "NO SE GUARDÓ" in vista._estado_prio.text()


def test_listo_y_esc_salen_del_modo(vista, qapp):
    vista.btn_prioridades.click()
    vista.btn_listo.click()
    assert not vista.editando and vista._header_edit.isHidden()
    assert _celda(vista, "Piper").botonera.isHidden()
    vista.btn_prioridades.click()
    vista.activateWindow()
    vista.setFocus()
    QTest.keyClick(vista, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not vista.editando


def test_en_solo_lectura_no_se_entra(qapp, db, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    con = sqlite3.connect(db)
    try:
        v = RosterView(con, db_path=db)
        assert not v.btn_prioridades.isEnabled() and not v.filtros.btn_marcar.isEnabled()
        v.entrar_edicion()
        assert not v.editando
    finally:
        con.close()


# --- el ancho, con las fuentes reales -------------------------------------------------------------

def test_con_prioridades_y_en_modo_edicion_la_vista_entra_en_1100(qapp, tmp_path, monkeypatch):
    fuentes = glob.glob(r"C:\Windows\Fonts\*.ttf")
    if not fuentes:
        pytest.skip("sin fuentes de Windows: el ancho medido no sería el real")
    from PySide6.QtGui import QFontDatabase
    for f in fuentes:
        QFontDatabase.addApplicationFont(f)
    real = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not real.is_file():
        pytest.skip("sin la DB de dominio")
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    copia = tmp_path / "copia.db"
    shutil.copy(real, copia)
    c = sqlite3.connect(copia)
    c.execute("DELETE FROM ajustes_usuario_prioridad")
    c.executemany("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) "
                  "SELECT id, ? FROM agents WHERE nombre = ?", [("alta", "Claret Flint"), ("baja", "Piper")])
    c.commit()
    c.close()
    con = sqlite3.connect(copia)
    try:
        v = RosterView(con, db_path=copia)
        assert v.minimumSizeHint().width() <= 1100, ("con prioridades", v.minimumSizeHint())
        v.entrar_edicion()
        assert v.minimumSizeHint().width() <= 1100, ("en modo edición", v.minimumSizeHint())
    finally:
        con.close()

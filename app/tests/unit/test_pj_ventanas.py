"""Las ventanas flotantes de la página del PJ (SPEC 2026-09-28, parte 2).

Guardan en el momento con `EditorFichaPJ` sobre una COPIA de la DB de dominio y se vuelven a
dibujar leyendo la DB. En sólo lectura, la franja y los controles apagados; si una escritura
falla, lo dicen.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication            # noqa: E402

from app.core.ficha_pj import EditorFichaPJ, leer_eleccion_pj  # noqa: E402
from app.db.repositories import agentes_cambiaron     # noqa: E402
from app.ui.pj_pagina.datos import pagina_pj          # noqa: E402
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


def _pagina(con, db, nombre, editor=None):
    pid = _id(con, nombre)
    return PjPagina(lambda: pagina_pj(con, pid), editor=editor or EditorFichaPJ(db), db_path=db)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- secundarios -------------------------------------------------------------------------------

def test_def_en_imprescindible_para_ellen(qapp, con, db):
    pagina = _pagina(con, db, "Ellen")
    v = pagina.ventana("secundarios")
    assert v.fila_de["DEF%"] == 0 and "dashed" in v.fichas["DEF%"].styleSheet()
    assert v.elegir_nivel("DEF%", 1)
    assert leer_eleccion_pj(con, _id(con, "Ellen")).niveles == {"DEF%": 1}
    assert v.fila_de["DEF%"] == 1, "se redibujó leyendo la DB"
    assert "2px solid" in v.fichas["DEF%"].styleSheet() and "dashed" in v.fichas["Daño Crítico"].styleSheet()
    assert any("DEF%" in t and "no le suma" in t for t in v.textos_visibles()), "el ⚠ en la ventana"
    assert any("DEF% (tuyo)" in t for t in pagina.textos_visibles()), "la página se refrescó"
    assert v.elegir_nivel("DEF%", None)
    assert leer_eleccion_pj(con, _id(con, "Ellen")).niveles == {}


def test_el_menu_trae_los_cinco_niveles_y_la_guia(qapp, con, db):
    v = _pagina(con, db, "Ellen").ventana("secundarios")
    acciones = [a for a in v.menu_de("DEF%").actions() if not a.isSeparator()]
    assert [a.text() for a in acciones] == ["Imprescindible", "Muy bueno", "Bueno", "Sirve", "No sirve",
                                            "↺ Como la guía"]
    assert [a.isChecked() for a in acciones[:5]] == [False, False, False, False, True]
    acciones[1].trigger()
    assert leer_eleccion_pj(con, _id(con, "Ellen")).niveles == {"DEF%": 2}


def test_esta_parte_a_la_guia_borra_los_niveles_del_usuario(qapp, con, db):
    a = _id(con, "Ellen")
    ed = EditorFichaPJ(db)
    ed.nivel_substat(a, "DEF%", 1)
    ed.nivel_substat(a, "HP%", 2)
    v = _pagina(con, db, "Ellen", editor=ed).ventana("secundarios")
    v.btn_guia.click()
    assert leer_eleccion_pj(con, a).niveles == {}
    assert "2px solid" not in "".join(b.styleSheet() for b in v.fichas.values())


def test_en_solo_lectura_la_franja_y_nada_se_guarda(qapp, con, db, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    antes = _sha(db)
    v = _pagina(con, db, "Ellen").ventana("secundarios")
    assert v.franja_solo_lectura is not None and not v.cuerpo.isEnabled() and not v.btn_guia.isEnabled()
    assert not v.elegir_nivel("DEF%", 1)
    assert _sha(db) == antes and "solo lectura" in v.mensaje.text()


def test_una_escritura_que_falla_lo_dice_sin_romper(qapp, con, db):
    class EditorRoto(EditorFichaPJ):
        def nivel_substat(self, *a, **k):
            raise sqlite3.IntegrityError("CHECK constraint failed")
    v = _pagina(con, db, "Ellen", editor=EditorRoto(db)).ventana("secundarios")
    assert not v.elegir_nivel("DEF%", 1)
    assert v.mensaje.text().startswith("No se guardó: CHECK constraint failed")
    assert v.fila_de["DEF%"] == 0


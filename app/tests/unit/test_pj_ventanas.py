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


# --- sets --------------------------------------------------------------------------------------

def _set(con, nombre):
    return con.execute("SELECT id FROM disc_sets WHERE nombre = ?", (nombre,)).fetchone()[0]


def test_elegir_el_4pc_lleva_el_2pc_al_recomendado_y_los_renglones_en_orden(qapp, con, db):
    a, monarca = _id(con, "Ju Fufu"), _set(con, "Monarca del Pináculo")
    v = _pagina(con, db, "Ju Fufu").ventana("sets")
    assert v.elegir_4pc(monarca)
    e = leer_eleccion_pj(con, a)
    assert (e.set_4p_id, e.set_2p_id) == (monarca, _set(con, "Disco Sacudestrellas"))
    orden = [_set(con, n) for n in ("Disco Sacudestrellas", "Tecno Pícido")]
    assert list(v.botones_2pc)[:2] == orden
    assert set(list(v.botones_2pc)[2:4]) == {_set(con, "Voz Astral"), _set(con, "Punk Hormonal")}
    assert v.botones_2pc[orden[0]].text() == "Disco Sacudestrellas (recomendado)"
    assert monarca not in v.botones_2pc, "el set del 4pc no se ofrece como 2pc"
    assert "2px solid" in v.botones_4pc[monarca].styleSheet()


def test_elegir_el_2pc_guarda_con_el_4pc_vigente(qapp, con, db):
    a, monarca, voz = _id(con, "Ju Fufu"), _set(con, "Monarca del Pináculo"), _set(con, "Voz Astral")
    v = _pagina(con, db, "Ju Fufu").ventana("sets")
    v.elegir_4pc(monarca)
    assert v.elegir_2pc(voz)
    e = leer_eleccion_pj(con, a)
    assert (e.set_4p_id, e.set_2p_id) == (monarca, voz)


def test_un_4pc_fuera_de_la_guia_avisa_y_automatico_lo_borra(qapp, con, db):
    a = _id(con, "Ju Fufu")
    v = _pagina(con, db, "Ju Fufu").ventana("sets")
    fuera = next(s for s, b in v.botones_4pc.items() if b.toolTip() == "Fuera de la guía.")
    assert v.elegir_4pc(fuera)
    assert any("fuera de la guía de Ju Fufu" in t for t in v.textos_visibles())
    assert v.elegir_4pc(None)
    assert leer_eleccion_pj(con, a).set_4p_id is None


def test_sin_4pc_no_se_puede_elegir_el_2pc(qapp, con, db):
    v = _pagina(con, db, "Ju Fufu").ventana("sets")
    antes = _sha(db)
    v.datos.foto.set_4p_id = None
    assert not v.elegir_2pc(_set(con, "Voz Astral"))
    assert v.mensaje.text() == "Elegí primero el 4pc." and _sha(db) == antes


# --- principales -------------------------------------------------------------------------------

def test_agregar_un_principal_fuera_de_la_guia_y_volver(qapp, con, db):
    a = _id(con, "Ellen")
    v = _pagina(con, db, "Ellen").ventana("principales")
    assert v.botones[(4, "Daño Crítico")].isChecked() and v.botones[(4, "Daño Crítico")].text() == "Daño Crítico · guía"
    assert v.alternar(4, "Prob. Crítica")
    assert leer_eleccion_pj(con, a).principales == {4: ("Daño Crítico", "Prob. Crítica")}
    assert v.botones[(4, "Prob. Crítica")].isChecked(), "se redibujó leyendo la DB"
    assert any(t.startswith("Prob. Crítica en el slot 4 no le sirve a Ellen") for t in v.textos_visibles())
    assert v.alternar(4, "Prob. Crítica")                     # igual a la guía: sin fila
    assert leer_eleccion_pj(con, a).principales == {}


def test_apagar_el_unico_no_deja_el_slot_vacio(qapp, con, db):
    v = _pagina(con, db, "Ellen").ventana("principales")
    antes = _sha(db)
    v.botones[(4, "Daño Crítico")].click()                    # Qt lo destilda; no hay nada que guardar
    assert _sha(db) == antes
    assert v.botones[(4, "Daño Crítico")].isChecked()
    assert "no puede quedar sin principales" in v.mensaje.text()


def test_el_slot_5_solo_ofrece_el_bono_del_elemento(qapp, con, db):
    v = _pagina(con, db, "Ellen").ventana("principales")
    assert (5, "Bono Daño Hielo") in v.botones and (5, "Bono Daño Fuego") not in v.botones


# --- fijos -------------------------------------------------------------------------------------

def _fijo(con, nombre, stat):
    from app.core.ficha_pj import fijos_de_la_ficha
    from app.db.repositories import AgentRepo
    agentes_cambiaron()
    return {f.stat: f for f in fijos_de_la_ficha(con, AgentRepo(con).get_by_id(_id(con, nombre)))}.get(stat)


def test_cambiar_desactivar_y_volver_a_la_guia(qapp, con, db):
    v = _pagina(con, db, "Anby").ventana("fijos")
    assert v.renglones["prob_critico"] == "tiene 48,2 · faltan 1,8 · el motor lo busca"
    assert v.cambiar("prob_critico", 55)
    f = _fijo(con, "Anby", "prob_critico")
    assert (f.objetivo, f.origen, f.de_la_guia) == (55, "tuyo", 50)
    assert v.spins["prob_critico"].value() == 55 and ("prob_critico", "↺") in v.botones
    assert v.desactivar("prob_critico")
    assert _fijo(con, "Anby", "prob_critico").objetivo is None
    assert v.renglones["prob_critico"] == "desactivado (guía: 50)"
    v.botones[("prob_critico", "reactivar")].click()
    f = _fijo(con, "Anby", "prob_critico")
    assert (f.objetivo, f.origen) == (50, "set")


def test_agregar_uno_nuevo_y_el_combo_no_repite(qapp, con, db):
    v = _pagina(con, db, "Anby").ventana("fijos")
    ofrecidos = [v.combo_nuevo.itemData(i) for i in range(v.combo_nuevo.count())]
    assert "prob_critico" not in ofrecidos and "ataque" in ofrecidos
    assert v.agregar("ataque", 2000)
    f = _fijo(con, "Anby", "ataque")
    assert (f.objetivo, f.origen, f.de_la_guia) == (2000, "tuyo", None)
    assert "ataque" not in [v.combo_nuevo.itemData(i) for i in range(v.combo_nuevo.count())]


def test_editar_sin_cambiar_no_escribe_y_un_cero_no_se_guarda(qapp, con, db):
    v = _pagina(con, db, "Anby").ventana("fijos")
    antes = _sha(db)
    v.spins["prob_critico"].editingFinished.emit()             # mismo valor: nada
    assert _sha(db) == antes and not list(db.parent.glob("copia.backup_preficha_*.db"))
    assert not v.cambiar("prob_critico", 0)
    assert _sha(db) == antes and "mayor que 0" in v.mensaje.text()


def test_despues_de_editar_la_ficha_y_el_motor_dicen_lo_mismo(qapp, con, db):
    from app.core.ficha_pj import fijos_de_la_ficha
    from app.db.repositories import AgentRepo
    v = _pagina(con, db, "Anby").ventana("fijos")
    v.cambiar("prob_critico", 55)
    v.agregar("ataque", 2000)
    agentes_cambiaron()
    anby = AgentRepo(con).get_by_id(_id(con, "Anby"))
    vivos = {f.stat: f.objetivo for f in fijos_de_la_ficha(con, anby) if f.objetivo is not None}
    assert vivos == anby.stats_fijos == {"prob_critico": 55, "ataque": 2000}

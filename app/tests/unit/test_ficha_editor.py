"""`EditorFichaPJ` y `foto`: lo que el usuario elige en la ficha, guardado con la ceremonia del
proyecto (RNF-01) y visto por el motor sin reiniciar (SPEC 2026-09-27, parte 4).

- modo solo lectura: no escribe ni hace backup;
- un backup por SESIÓN, antes de la primera escritura;
- un valor inválido no queda escrito (los CHECK de la mig 46);
- `None` vuelve a la guía; `volver_a_la_guia` borra todo lo del PJ y nada de otro;
- la foto muestra NIVELES, nunca pesos.

Todo sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.core.ficha_pj import EditorFichaPJ, foto
from app.db.repositories import AgentRepo, agentes_cambiaron

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_46 = RAIZ / "db" / "migrations" / "2026-09-27_46_ficha_sets_y_stats.sql"
TABLAS = ("ajustes_usuario_substats", "ajustes_usuario_principales", "ajustes_usuario_fijos",
          "ajustes_usuario_build")

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture
def copia(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    c = tmp_path / "copia.db"
    shutil.copy(DB_REAL, c)
    con = sqlite3.connect(c)
    ya = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'set_condiciones_4pc'").fetchone()[0]
    con.close()
    if not ya:
        sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
        try:
            from apply_migration import aplicar
        finally:
            sys.path.pop(0)
        assert aplicar(MIG_46, c, hacer_backup=False, dry_run=False) == 0
    con = sqlite3.connect(c)
    for t in TABLAS:
        con.execute(f"DELETE FROM {t}")
    con.commit()
    con.close()
    return c


def _id(db, nombre):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]
    finally:
        con.close()


def _filas(db, tabla):
    con = sqlite3.connect(db)
    try:
        return con.execute(f"SELECT * FROM {tabla}").fetchall()
    finally:
        con.close()


def _agente(db, nombre):
    agentes_cambiaron()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)
    finally:
        con.close()


def test_en_solo_lectura_no_escribe_ni_respalda(copia, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    ed = EditorFichaPJ(copia)
    res = ed.nivel_substat(_id(copia, "Ellen"), "DEF%", 1)
    assert not res.escribio and ed.backup is None and _filas(copia, "ajustes_usuario_substats") == []


def test_un_backup_por_sesion(copia):
    ed = EditorFichaPJ(copia)
    ellen = _id(copia, "Ellen")
    r1 = ed.nivel_substat(ellen, "DEF%", 1)
    r2 = ed.fijo(ellen, "ataque", 3100)
    assert r1.escribio and r2.escribio and r1.backup == r2.backup and r1.backup.exists()


def test_el_nivel_llega_al_motor_y_none_vuelve_a_la_guia(copia):
    ed = EditorFichaPJ(copia)
    ellen = _id(copia, "Ellen")
    guia = dict(_agente(copia, "Ellen").substat_preferences)
    ed.nivel_substat(ellen, "DEF%", 1)
    ed.nivel_substat(ellen, "DEF%", 2)                         # actualiza, no duplica
    assert _filas(copia, "ajustes_usuario_substats") == [(ellen, "DEF%", 2, _filas(copia, "ajustes_usuario_substats")[0][3])]
    assert _agente(copia, "Ellen").substat_preferences["DEF%"] == 0.8
    ed.nivel_substat(ellen, "DEF%", None)
    assert _agente(copia, "Ellen").substat_preferences == guia


@pytest.mark.parametrize("llamada", [
    lambda ed, pj: ed.nivel_substat(pj, "DEF%", 7),
    lambda ed, pj: ed.nivel_substat(pj, "Impacto", 1),
    lambda ed, pj: ed.principales(pj, 3, ["DEF%"]),
    lambda ed, pj: ed.fijo(pj, "velocidad", 10),
    lambda ed, pj: ed.nivel_substat(99999, "DEF%", 1),        # PJ inexistente: FK
])
def test_un_valor_invalido_no_queda_escrito(copia, llamada):
    with pytest.raises(sqlite3.IntegrityError):
        llamada(EditorFichaPJ(copia), _id(copia, "Ellen"))
    assert all(_filas(copia, t) == [] for t in TABLAS)


def test_principales_fijos_y_build(copia):
    ed = EditorFichaPJ(copia)
    ellen = _id(copia, "Ellen")
    ed.principales(ellen, 4, ["Prob. Crítica", "Daño Crítico"])
    ed.desactivar_fijo(_id(copia, "Astra Yao"), "ataque")
    ed.build(ellen, 41, 48)
    assert _agente(copia, "Ellen").mains[4] == ("Daño Crítico", "Prob. Crítica")
    assert "ataque" not in _agente(copia, "Astra Yao").stats_fijos
    e = _agente(copia, "Ellen")
    assert (e.set_4p_id, e.set_2p_id, e.origen_build) == (41, 48, "declarado")
    with pytest.raises(ValueError):
        ed.principales(ellen, 5, [])
    with pytest.raises(ValueError):
        ed.build(ellen, 41, 41)


def test_volver_a_la_guia_borra_todo_del_pj_y_nada_de_otro(copia):
    ed = EditorFichaPJ(copia)
    ellen, astra = _id(copia, "Ellen"), _id(copia, "Astra Yao")
    ed.nivel_substat(ellen, "DEF%", 1)
    ed.principales(ellen, 4, ["Prob. Crítica"])
    ed.fijo(ellen, "ataque", 3100)
    ed.build(ellen, 41, None)
    ed.nivel_substat(astra, "ATK%", 1)
    ed.volver_a_la_guia(ellen)
    for t in TABLAS:
        assert [f for f in _filas(copia, t) if f[0] == ellen] == [], t
    assert len(_filas(copia, "ajustes_usuario_substats")) == 1         # la de Astra sigue


def test_la_foto_muestra_niveles_y_avisos(copia):
    ed = EditorFichaPJ(copia)
    ellen = _id(copia, "Ellen")
    ed.nivel_substat(ellen, "DEF%", 1)
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    try:
        f = foto(con, ellen)
    finally:
        con.close()
    assert f.nombre == "Ellen" and f.niveles["DEF%"] == 1
    assert f.niveles["Daño Crítico"] == 1 and f.niveles["HP"] == 0       # de la guía / no nombrado
    assert set(f.niveles.values()) <= {0, 1, 2, 3, 4}                   # niveles, nunca pesos
    assert any(a.tipo == "substat_no_te_beneficia" for a in f.avisos)


def test_el_motor_ve_el_cambio_sin_reiniciar(copia):
    """Un AgentRepo que ya cargó (como el de la captura en vivo) ve el cambio: el editor avisa."""
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    try:
        repo = AgentRepo(con)
        ellen = next(a for a in repo.get_all() if a.nombre == "Ellen")
        assert ellen.substat_preferences.get("DEF%", 0) == 0
        EditorFichaPJ(copia).nivel_substat(ellen.id, "DEF%", 1)
        assert repo.get_by_id(ellen.id).substat_preferences["DEF%"] == 1.0
    finally:
        con.close()

"""El repositorio de la prioridad de buildeo (mig 42): leerla en cada `Agent` y guardarla.

Una sola forma de decir "normal" (B1): sin fila. Guardar 'normal' borra la fila; leer un PJ sin fila
da 'normal'. Todo sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.db.repositories import PRIORIDADES, AgentRepo, PrioridadRepo

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture
def copia(tmp_path):
    c = tmp_path / "copia.db"
    shutil.copy(DB_REAL, c)
    con = sqlite3.connect(c)
    con.execute("DELETE FROM ajustes_usuario_prioridad")    # partir de "nadie declarado"
    con.commit()
    con.close()
    return c


@pytest.fixture
def con(copia):
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def _id(con, nombre):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


def _prioridades(con) -> dict[str, str]:
    return {a.nombre: a.prioridad for a in AgentRepo(con).get_all()}


def test_sin_declarar_todos_en_normal(con):
    p = _prioridades(con)
    assert len(p) >= 52 and set(p.values()) == {"normal"}


def test_lo_guardado_llega_al_agent(con):
    repo = PrioridadRepo(con)
    repo.guardar(_id(con, "Claret Flint"), "alta")
    repo.guardar(_id(con, "Piper"), "baja")
    p = _prioridades(con)
    assert p["Claret Flint"] == "alta" and p["Piper"] == "baja"
    assert sorted(n for n, v in p.items() if v != "normal") == ["Claret Flint", "Piper"]


def test_guardar_normal_borra_la_fila(con):
    repo, pid = PrioridadRepo(con), _id(con, "Piper")
    repo.guardar(pid, "baja")
    repo.guardar(pid, "normal")
    assert con.execute("SELECT COUNT(*) FROM ajustes_usuario_prioridad").fetchone()[0] == 0
    assert repo.get(pid) == "normal"


def test_cambiar_de_alta_a_baja_deja_una_sola_fila_y_renueva_el_sello(con):
    repo, pid = PrioridadRepo(con), _id(con, "Piper")
    repo.guardar(pid, "alta")
    con.execute("UPDATE ajustes_usuario_prioridad SET actualizado = '2000-01-01 00:00:00'")
    repo.guardar(pid, "baja")
    filas = con.execute("SELECT prioridad, actualizado FROM ajustes_usuario_prioridad").fetchall()
    assert len(filas) == 1 and filas[0][0] == "baja"
    assert filas[0][1] != "2000-01-01 00:00:00", "el sello dice cuándo se tocó por última vez"


@pytest.mark.parametrize("valor", ["media", "Alta", "", None])
def test_un_valor_desconocido_no_se_escribe(con, valor):
    with pytest.raises(ValueError):
        PrioridadRepo(con).guardar(_id(con, "Piper"), valor)
    assert con.execute("SELECT COUNT(*) FROM ajustes_usuario_prioridad").fetchone()[0] == 0


def test_el_orden_es_de_mayor_a_menor():
    assert PRIORIDADES == ("alta", "normal", "baja")


def test_una_db_sin_la_migracion_42_da_todos_en_normal(copia):
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    c.execute("DROP TABLE ajustes_usuario_prioridad")
    assert PrioridadRepo(c).get_all() == {}
    assert {a.prioridad for a in AgentRepo(c).get_all()} == {"normal"}
    c.close()


def test_el_rebuild_de_la_db_conserva_la_prioridad(copia, tmp_path):
    """Es una declaración del usuario: ningún censo la reproduce (`rebuild_account_db.DECLARADO`)."""
    from app.scripts.rebuild_account_db import rebuild
    c = sqlite3.connect(copia)
    PrioridadRepo(c).guardar(_id(c, "Claret Flint"), "alta")
    c.commit()
    c.close()
    rebuild(copia, tmp_path / "nueva.db")
    n = sqlite3.connect(tmp_path / "nueva.db")
    assert n.execute("SELECT prioridad FROM ajustes_usuario_prioridad").fetchall() == [("alta",)]
    n.close()

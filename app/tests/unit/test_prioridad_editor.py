"""`EditorPrioridades`: la escritura de la prioridad desde la app (RNF-01) y el aviso al motor.

- modo solo lectura: no escribe ni hace backup;
- un backup por SESIÓN de edición, antes de la primera escritura (no uno por click);
- cada click es su transacción; un PJ inexistente no queda escrito;
- después del commit, los `AgentRepo` que ya tenían los PJs cacheados ven la prioridad nueva: si
  no, el motor seguía con la vieja hasta reiniciar y "sugerencias recalculadas" mentía.

Todo sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.prioridad import EditorPrioridades
from app.db.repositories import AgentRepo

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture
def copia(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    c = tmp_path / "copia.db"
    shutil.copy(DB_REAL, c)
    con = sqlite3.connect(c)
    con.execute("DELETE FROM ajustes_usuario_prioridad")
    con.commit()
    con.close()
    return c


def _id(db, nombre):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]
    finally:
        con.close()


def _filas(db):
    con = sqlite3.connect(db)
    try:
        return dict(con.execute("SELECT agente_id, prioridad FROM ajustes_usuario_prioridad"))
    finally:
        con.close()


def _backups(db: Path):
    return sorted(db.parent.glob(f"{db.stem}.backup_preprioridad_*.db"))


def test_guarda_y_normal_borra(copia):
    ed, cid = EditorPrioridades(copia), _id(copia, "Claret Flint")
    assert ed.guardar(cid, "alta", "Claret Flint").escribio
    assert _filas(copia) == {cid: "alta"}
    ed.guardar(cid, "normal")
    assert _filas(copia) == {}


def test_un_backup_por_sesion_antes_de_la_primera_escritura(copia):
    ed = EditorPrioridades(copia)
    r1 = ed.guardar(_id(copia, "Claret Flint"), "alta")
    r2 = ed.guardar(_id(copia, "Piper"), "baja")
    assert r1.backup == r2.backup and len(_backups(copia)) == 1
    con = sqlite3.connect(r1.backup)
    try:
        assert con.execute("SELECT COUNT(*) FROM ajustes_usuario_prioridad").fetchone()[0] == 0, \
            "el backup es el estado de ANTES de editar"
    finally:
        con.close()
    EditorPrioridades(copia).guardar(_id(copia, "Piper"), "normal")
    assert len(_backups(copia)) == 2, "otra sesión, otro backup"


def test_en_modo_solo_lectura_no_escribe_ni_respalda(copia, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    res = EditorPrioridades(copia).guardar(_id(copia, "Piper"), "baja")
    assert not res.escribio and "solo lectura" in res.motivo_no_escribio
    assert _filas(copia) == {} and _backups(copia) == []


def test_un_valor_desconocido_no_escribe_ni_respalda(copia):
    with pytest.raises(ValueError):
        EditorPrioridades(copia).guardar(_id(copia, "Piper"), "media")
    assert _filas(copia) == {} and _backups(copia) == []


def test_un_pj_inexistente_no_queda_escrito(copia):
    with pytest.raises(sqlite3.IntegrityError):
        EditorPrioridades(copia).guardar(999999, "alta")
    assert _filas(copia) == {}


def test_el_motor_ve_la_prioridad_nueva_sin_reiniciar(copia):
    """Un AgentRepo que ya cargó los PJs (como el del controller) tiene que ver el cambio."""
    lectura = sqlite3.connect(copia)
    lectura.row_factory = sqlite3.Row
    try:
        repo = AgentRepo(lectura)
        cid = _id(copia, "Claret Flint")
        assert repo.get_by_id(cid).prioridad == "normal"
        EditorPrioridades(copia).guardar(cid, "alta")
        assert repo.get_by_id(cid).prioridad == "alta"
    finally:
        lectura.close()

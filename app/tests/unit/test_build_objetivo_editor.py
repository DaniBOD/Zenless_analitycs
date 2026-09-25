"""`BuildObjetivoRepo` y `EditorBuildObjetivo`: el build de sets que Daniel declara para un PJ.

Daniel, 2026-09-25, sobre Gatillo (Armonía umbría + Tecno Pícido) y Grace (Blues Libre + Jazz
Caótico), cuyos 4pc la guía no lista: "son builds mías que veo óptimas, dejalo como builds creadas
por el usuario". Cualquier set vale, esté o no en la guía.

- modo solo lectura: no escribe ni hace backup;
- un backup por SESIÓN, antes de la primera escritura;
- cada cambio es su transacción; un PJ o set inexistente no queda escrito;
- guardar dos veces actualiza (no duplica); borrar vuelve al automático.

Todo sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.build_objetivo import EditorBuildObjetivo
from app.db.repositories import BuildDeclarado, BuildObjetivoRepo

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture
def copia(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    c = tmp_path / "copia.db"
    shutil.copy(DB_REAL, c)
    con = sqlite3.connect(c)
    con.execute("DELETE FROM ajustes_usuario_build")
    con.commit()
    con.close()
    return c


def _q(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _agente(db, nombre):
    return _q(db, "SELECT id FROM agents WHERE nombre = ?", (nombre,))[0][0]


def _set(db, nombre):
    return _q(db, "SELECT id FROM disc_sets WHERE nombre = ?", (nombre,))[0][0]


def _leer(db, agente):
    con = sqlite3.connect(db)
    try:
        return BuildObjetivoRepo(con).get(agente)
    finally:
        con.close()


def _backups(db: Path):
    return sorted(db.parent.glob(f"{db.stem}.backup_prebuild_*.db"))


def test_declara_un_build_fuera_de_la_guia(copia):
    """Gatillo: Armonía umbría no está en su guía, y se declara igual."""
    gatillo, armonia, picido = _agente(copia, "Gatillo"), _set(copia, "Armonía umbría"), _set(copia, "Tecno Pícido")
    r = EditorBuildObjetivo(copia).guardar(gatillo, armonia, picido, "Gatillo")
    assert r.escribio and r.backup is not None
    assert _leer(copia, gatillo) == BuildDeclarado(armonia, picido)


def test_guardar_dos_veces_actualiza_y_un_backup_por_sesion(copia):
    grace = _agente(copia, "Grace")
    blues, jazz, metal = _set(copia, "Blues Libre"), _set(copia, "Jazz Caótico"), _set(copia, "Metal Eléctrico")
    ed = EditorBuildObjetivo(copia)
    ed.guardar(grace, blues, jazz)
    ed.guardar(grace, metal, None)
    assert _leer(copia, grace) == BuildDeclarado(metal, None)
    assert _q(copia, "SELECT COUNT(*) FROM ajustes_usuario_build")[0][0] == 1
    assert len(_backups(copia)) == 1


def test_borrar_vuelve_al_automatico(copia):
    grace = _agente(copia, "Grace")
    ed = EditorBuildObjetivo(copia)
    ed.guardar(grace, _set(copia, "Blues Libre"))
    ed.borrar(grace)
    assert _leer(copia, grace) is None


def test_un_set_inexistente_no_queda_escrito(copia):
    grace = _agente(copia, "Grace")
    with pytest.raises(sqlite3.IntegrityError):
        EditorBuildObjetivo(copia).guardar(grace, 99999)
    assert _leer(copia, grace) is None


def test_el_2pc_no_puede_ser_el_4pc(copia):
    grace, blues = _agente(copia, "Grace"), _set(copia, "Blues Libre")
    with pytest.raises(ValueError):
        EditorBuildObjetivo(copia).guardar(grace, blues, blues)
    assert _backups(copia) == []


def test_readonly_no_escribe_ni_respalda(copia, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    grace = _agente(copia, "Grace")
    r = EditorBuildObjetivo(copia).guardar(grace, _set(copia, "Blues Libre"))
    assert not r.escribio and r.motivo_no_escribio
    assert _leer(copia, grace) is None and _backups(copia) == []


def test_un_agentrepo_abierto_ve_el_build_nuevo(copia):
    """Como con la prioridad: el controller y la captura en vivo tienen un `AgentRepo` de toda la
    sesión. Sin el aviso, el motor seguía con el build objetivo viejo hasta reiniciar."""
    from app.db.repositories import AgentRepo
    grace = _agente(copia, "Grace")
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    repo = AgentRepo(con)
    antes = repo.get_by_id(grace).set_4p_id
    # En la copia no hay builds declarados: Grace cae en el primero de su guía (Metal Eléctrico).
    jazz = _set(copia, "Jazz Caótico")
    assert antes != jazz
    EditorBuildObjetivo(copia).guardar(grace, jazz, None)
    assert repo.get_by_id(grace).set_4p_id == jazz
    con.close()

"""Migración 44 + `app.core.movimientos`: registrar en la DB un movimiento hecho en el juego.

Daniel aplicó dos sugerencias (#85 Anby → Dialyn con #92 de reposición; #188 Astra Yao → Ju Fufu
con #192) y pidió: "realizalos en la db para que tenga trazabilidad". El desplazado queda LIBRE
(invariante del 2026-07-22: el juego no recuerda quién lo llevaba). Todo sobre una COPIA.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.core.movimientos import EditorMovimientos, Movimiento

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_44 = RAIZ / "db" / "migrations" / "2026-09-25_44_movimientos_discos.sql"

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


def _aplicar_mig(db):
    sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
    try:
        from apply_migration import aplicar
    finally:
        sys.path.pop(0)
    return aplicar(MIG_44, db, hacer_backup=False, dry_run=False)


def _disco(con, slot, agente, equipado=1, set_id=34):
    return con.execute("INSERT INTO inventory_discs (set_id, slot, main_stat, main_valor, nivel, "
                       "agente_asignado, equipado, descartado) VALUES (?, ?, 'HP', 2200, 15, ?, ?, 0)",
                       (set_id, slot, agente, equipado)).lastrowid


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    con = sqlite3.connect(copia)
    con.execute("DROP TABLE IF EXISTS movimientos_discos")
    con.commit()
    con.close()
    assert _aplicar_mig(copia) == 0
    con = sqlite3.connect(copia)
    ids = {n: i for i, n in con.execute("SELECT id, nombre FROM agents")}
    with con:
        d = {"85": _disco(con, 3, ids["Anby"]), "86": _disco(con, 3, ids["Dialyn"]),
             "92": _disco(con, 3, None, equipado=0)}
        con.execute("DELETE FROM inventory_discs WHERE slot = 3 AND agente_asignado IN (?, ?) AND id NOT IN (?, ?)",
                    (ids["Anby"], ids["Dialyn"], d["85"], d["86"]))
    con.close()
    return copia, ids, d


def _estado(db, disc):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT equipado, agente_asignado FROM inventory_discs WHERE id = ?", (disc,)).fetchone()
    finally:
        con.close()


def _log(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT disc_id, slot, desde_agente_id, hacia_agente_id, motivo, fuente "
                           "FROM movimientos_discos ORDER BY id").fetchall()
    finally:
        con.close()


def test_el_swap_de_dialyn_queda_registrado(db):
    path, ids, d = db
    r = EditorMovimientos(path).registrar([Movimiento(d["85"], ids["Dialyn"], "ref"),
                                           Movimiento(d["92"], ids["Anby"], "ref")])
    assert r.escribio and r.backup is not None and r.lote
    assert _estado(path, d["85"]) == (1, ids["Dialyn"])
    assert _estado(path, d["92"]) == (1, ids["Anby"])
    assert _estado(path, d["86"]) == (0, None)                     # el desplazado queda libre
    assert _log(path) == [
        (d["86"], 3, ids["Dialyn"], None, "desplazado", "declarado_usuario"),
        (d["85"], 3, ids["Anby"], ids["Dialyn"], "equipa", "declarado_usuario"),
        (d["92"], 3, None, ids["Anby"], "equipa", "declarado_usuario"),
    ]


def test_la_tanda_es_entera_o_nada(db):
    path, ids, d = db
    with pytest.raises(ValueError):
        EditorMovimientos(path).registrar([Movimiento(d["85"], ids["Dialyn"]), Movimiento(999999, ids["Anby"])])
    assert _estado(path, d["85"]) == (1, ids["Anby"]) and _log(path) == []


def test_dos_al_mismo_slot_del_mismo_pj_no(db):
    path, ids, d = db
    with pytest.raises(ValueError):
        EditorMovimientos(path).registrar([Movimiento(d["85"], ids["Dialyn"]), Movimiento(d["92"], ids["Dialyn"])])
    assert _log(path) == []


def test_readonly_no_escribe(db, monkeypatch):
    path, ids, d = db
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    r = EditorMovimientos(path).registrar([Movimiento(d["85"], ids["Dialyn"])])
    assert not r.escribio and _estado(path, d["85"]) == (1, ids["Anby"])


def test_un_agentrepo_abierto_ve_lo_equipado_nuevo(db):
    """Lo equipado decide el build objetivo (R19): el motor lo tiene que ver sin reiniciar."""
    import app.db.repositories as repos
    path, ids, d = db
    antes = repos._GENERACION_AGENTES
    EditorMovimientos(path).registrar([Movimiento(d["85"], ids["Dialyn"])])
    assert repos._GENERACION_AGENTES == antes + 1


def test_la_db_rechaza_un_desplazado_con_destino(db):
    path, ids, d = db
    con = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO movimientos_discos (lote, disc_id, slot, desde_agente_id, hacia_agente_id, "
                    "motivo, fuente) VALUES ('x', ?, 3, ?, ?, 'desplazado', 'x')", (d["86"], ids["Dialyn"], ids["Anby"]))
    con.close()


def test_rebuild_la_vacia():
    sys.path.insert(0, str(RAIZ / "app" / "scripts"))
    try:
        import rebuild_account_db as r
    finally:
        sys.path.pop(0)
    assert "movimientos_discos" in r.VACIAR

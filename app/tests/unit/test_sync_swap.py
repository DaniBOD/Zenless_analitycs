"""Write del swap de disco entre PJs: `DiscSyncer.move_disc_between_agents` (23.4, RNF-01).

Mueve la fila EXISTENTE del disco del origen al destino (update_assignment), en vez de dejar que
la persistencia S17 inserte un duplicado. Desequipa el disco desplazado del destino. Gate readonly.
"""
from __future__ import annotations

import sqlite3

import pytest

_SCHEMA = """
CREATE TABLE inventory_discs (
    id INTEGER PRIMARY KEY,
    set_id INTEGER, slot INTEGER,
    main_stat TEXT, main_valor REAL,
    sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0,
    sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0,
    sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0,
    sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0,
    nivel INTEGER DEFAULT 0,
    equipado INTEGER DEFAULT 0,
    agente_asignado INTEGER,
    descartado INTEGER DEFAULT 0,
    score_evaluacion REAL,
    agentes_compatibles TEXT,
    notas TEXT
);
"""


class _FakeAgent:
    def __init__(self, i):
        self.id = i


class _FakeAgentRepo:
    """origen 'Yixuan'→1, destino 'Nangong Yu'→2."""
    _M = {"Yixuan": 1, "Nangong Yu": 2, "Ellen": 3}

    def get_by_nombre(self, n):
        i = self._M.get(n)
        return _FakeAgent(i) if i else None


def _mk_syncer(tmp_path, monkeypatch, rows):
    """DB temp con `rows` = [(id, set_id, slot, equipado, agente)]. Devuelve (syncer, db_path)."""
    db = tmp_path / "swap.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)
    for (did, sid, slot, eq, ag) in rows:
        con.execute(
            "INSERT INTO inventory_discs (id, set_id, slot, main_stat, equipado, agente_asignado) "
            "VALUES (?,?,?,?,?,?)", (did, sid, slot, "ATK", eq, ag),
        )
    con.commit()
    con.close()

    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    s = se.DiscSyncer(db_path=db)
    s._agent_repo = _FakeAgentRepo()
    return s, db


def _disc_row(db, disc_id):
    con = sqlite3.connect(str(db)); con.row_factory = sqlite3.Row
    r = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (disc_id,)).fetchone()
    con.close()
    return (r["agente_asignado"], r["equipado"])


def test_mueve_la_fila_del_origen_sin_duplicar(tmp_path, monkeypatch):
    # Yixuan(1) tiene disco 10 (set 5, slot 2). Nangong(2) tiene disco 20 (set 6, slot 2).
    s, db = _mk_syncer(tmp_path, monkeypatch,
                       [(10, 5, 2, 1, 1), (20, 6, 2, 1, 2)])
    try:
        assert s.move_disc_between_agents("Yixuan", "Nangong Yu", slot=2, set_id=5) is True
    finally:
        s.close()
    assert _disc_row(db, 10) == (2, 1)   # disco movido → Nangong, equipado
    assert _disc_row(db, 20) == (2, 0)   # disco desplazado del destino → desequipado
    # no se creó fila nueva (sigue habiendo 2 discos)
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM inventory_discs").fetchone()[0] == 2
    con.close()


def test_destino_sin_disco_previo_en_el_slot(tmp_path, monkeypatch):
    """Nangong no tenía nada en slot 2 → solo se mueve el del origen, sin desequipar nada."""
    s, db = _mk_syncer(tmp_path, monkeypatch, [(10, 5, 2, 1, 1)])
    try:
        assert s.move_disc_between_agents("Yixuan", "Nangong Yu", slot=2) is True
    finally:
        s.close()
    assert _disc_row(db, 10) == (2, 1)


def test_readonly_no_escribe(tmp_path, monkeypatch):
    import app.core.sync_equip as se
    s, db = _mk_syncer(tmp_path, monkeypatch, [(10, 5, 2, 1, 1)])
    monkeypatch.setattr(se, "is_readonly", lambda: True)   # ahora sí readonly
    try:
        assert s.move_disc_between_agents("Yixuan", "Nangong Yu", slot=2) is False
    finally:
        s.close()
    assert _disc_row(db, 10) == (1, 1)   # intacto


def test_origen_sin_disco_en_db_no_mueve(tmp_path, monkeypatch):
    """Sin fila del origen no hay nada que mover (la persistencia S17 lo dará de alta)."""
    s, db = _mk_syncer(tmp_path, monkeypatch, [(20, 6, 2, 1, 2)])   # solo el disco del destino
    try:
        assert s.move_disc_between_agents("Yixuan", "Nangong Yu", slot=2) is False
    finally:
        s.close()


def test_set_no_coincide_no_mueve(tmp_path, monkeypatch):
    """Si el disco equipado del origen no es el set del diálogo → no se mueve (RNF-02)."""
    s, db = _mk_syncer(tmp_path, monkeypatch, [(10, 5, 2, 1, 1)])
    try:
        assert s.move_disc_between_agents("Yixuan", "Nangong Yu", slot=2, set_id=99) is False
    finally:
        s.close()
    assert _disc_row(db, 10) == (1, 1)   # intacto


def test_pj_no_resuelto_no_mueve(tmp_path, monkeypatch):
    s, db = _mk_syncer(tmp_path, monkeypatch, [(10, 5, 2, 1, 1)])
    try:
        assert s.move_disc_between_agents("Desconocido", "Nangong Yu", slot=2) is False
    finally:
        s.close()

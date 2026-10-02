"""S17 no pisa la fila del slot con OTRO disco del mismo set (SPEC 2026-10-02, punto 6).

QA en vivo 2026-10-02 00:22: Daniel le cambió a Claret el Rosa espinosa slot 4 por OTRO Rosa
espinosa slot 4 que estaba libre (y ya guardado, #419). `persist_s17_disc` decidía "mismo disco" con
sólo el set → `s17_update` sobrescribió #402 con el nuevo: el viejo desapareció de la DB y el nuevo
quedó dos veces.

- "Mismo disco" = `es_el_mismo_disco`: si no lo es, el viejo se desequipa y no se pisa.
- El monitor confirma "LIBRE → PJ · CAMBIÓ ✓" y marca `equipado_desde_libre`: con exactamente UNA
  fila libre de esa identidad, S17 la adopta en vez de insertar otra. Con gemelos se abstiene.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.tests.unit.test_sync_swap import _SCHEMA

_SCHEMA_ROSA = _SCHEMA + """
INSERT INTO disc_sets VALUES (55, 'Rosa espinosa', 'Thorned Rose', 'DEF', '+16%', '...');
INSERT INTO agents (id, nombre, rol) VALUES (52, 'Claret Flint', 'Armero');
INSERT INTO agent_score_thresholds (agente_id) VALUES (52);
"""

VIEJO = [("HP%", 6.0, 1), ("ATK%", 3.0, 0), ("DEF", 15.0, 0), ("ATK", 57.0, 2)]
NUEVO = [("DEF%", 14.4, 2), ("Maestría de Anomalía", 9.0, 0), ("ATK%", 3.0, 0), ("HP%", 9.0, 2)]


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    path = tmp_path / "s17.db"
    con = sqlite3.connect(str(path))
    con.executescript(_SCHEMA_ROSA)
    con.commit()
    con.close()
    return path


def _fila(path, subs, nivel=15, equipado=1, agente=52, id_=None):
    cols = ", ".join(f"sub{i}, val{i}, rolls{i}" for i in range(1, len(subs) + 1))
    vals = [v for s in subs for v in s]
    con = sqlite3.connect(str(path))
    cur = con.execute(
        f"INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, {cols}, nivel, "
        f"equipado, agente_asignado) VALUES (?, 55, 4, 'Prob. Crítica', 24.0, "
        f"{', '.join('?' * len(vals))}, ?, ?, ?)", [id_, *vals, nivel, equipado, agente])
    con.commit()
    did = cur.lastrowid
    con.close()
    return did


def _rosa4(subs, nivel=15, equipado_desde_libre=False) -> DiscParsed:
    d = DiscParsed(set_name_raw="Rosa espinosa", set_name_canon="Rosa espinosa", slot=4,
                   main_stat_raw="Prob. Crítica", main_stat_canon="Prob. Crítica", main_valor=24.0,
                   main_unidad="%", nivel=nivel, rareza="S", confianza_global=0.95,
                   subs=[SubstatParsed(n, n, v, "%" if n.endswith("%") else "flat", r, 0.95)
                         for n, v, r in subs])
    d.agente_asignado_nombre, d.agente_asignado_conf = "Claret Flint", 0.95
    d.equipado_desde_libre = equipado_desde_libre
    return d


def _estado(path):
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    out = {r["id"]: (r["equipado"], r["agente_asignado"], r["sub1"]) for r in con.execute(
        "SELECT id, equipado, agente_asignado, sub1 FROM inventory_discs")}
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    assert fk == [] and ok == "ok"
    return out


def _persistir(path, parsed):
    from app.core.sync_equip import DiscSyncer
    s = DiscSyncer(db_path=path)
    try:
        return s.persist_s17_disc(parsed)
    finally:
        s.close()


def test_otro_disco_del_mismo_set_no_pisa_la_fila(db):
    viejo = _fila(db, VIEJO)
    res = _persistir(db, _rosa4(NUEVO))
    est = _estado(db)
    assert res.trigger != "s17_update"
    # Desequipado y con SUS stats. Conserva el dueño: así es `set_unequipped` hoy (el invariante
    # R2 del 2026-07-22, que se lo sacaría, está frenado por Daniel).
    assert est[viejo] == (0, 52, "HP%"), "el viejo queda desequipado y con SUS stats"
    assert est[res.disc_id][:2] == (1, 52) and est[res.disc_id][2] == "DEF%"


def test_el_libre_recien_equipado_se_adopta_sin_duplicar(db):
    """El caso #419: el nuevo ya estaba guardado libre; el monitor vio LIBRE → Claret."""
    viejo = _fila(db, VIEJO)
    libre = _fila(db, NUEVO, equipado=0, agente=None)
    res = _persistir(db, _rosa4(NUEVO, equipado_desde_libre=True))
    est = _estado(db)
    assert res.trigger == "s17_equipa_libre" and res.disc_id == libre
    assert len(est) == 2, "no se insertó nada"
    assert est[libre][:2] == (1, 52) and est[viejo][0] == 0


def test_sin_la_observacion_del_monitor_no_se_adopta_un_libre(db):
    """Los libres siguen fuera del match por identidad (gemelos): sin la evidencia del check, se
    inserta como hasta hoy."""
    _fila(db, VIEJO)
    libre = _fila(db, NUEVO, equipado=0, agente=None)
    res = _persistir(db, _rosa4(NUEVO))
    assert res.disc_id != libre and _estado(db)[libre][:2] == (0, None)


def test_con_gemelos_libres_se_abstiene(db):
    _fila(db, VIEJO)
    g1 = _fila(db, NUEVO, equipado=0, agente=None)
    g2 = _fila(db, NUEVO, equipado=0, agente=None)
    res = _persistir(db, _rosa4(NUEVO, equipado_desde_libre=True))
    est = _estado(db)
    assert res.disc_id not in (g1, g2)
    assert est[g1][:2] == (0, None) and est[g2][:2] == (0, None)


def test_el_refresco_tras_una_mejora_sigue_siendo_update(db):
    pre = [("HP%", 3.0, 0), ("ATK%", 3.0, 0), ("DEF", 15.0, 0)]
    fila = _fila(db, pre, nivel=0)
    res = _persistir(db, _rosa4(pre[:2] + [("DEF", 30.0, 1), ("ATK", 19.0, 0)], nivel=3))
    assert res.trigger == "s17_update" and res.disc_id == fila
    assert len(_estado(db)) == 1

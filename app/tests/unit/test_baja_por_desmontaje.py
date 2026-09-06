"""Baja de discos desmontados: la fila se marca `descartado=1` en vez de borrarse.

Tercer verbo del ciclo de vida (2026-09-06). Hasta acá la bitácora de desmontaje escribía un JSON
y dejaba la DB intacta a propósito, con la baja anotada como "un paso futuro y separado". Sin ella
el sistema sólo sabe SUMAR: cada disco farmeado entra y ninguno sale, así que la DB se aleja de la
cuenta sola.

⚠️ El riesgo de este verbo es el opuesto al de los otros dos. Insertar de más se corrige; dar de
baja la fila equivocada BORRA un disco que el usuario sí tiene. Por eso el matcher exige
identidad ∧ VALORES y se abstiene ante ambigüedad — es la regla que el propio
`teardown_batch._record` dejó escrita: *"el matcher futuro debe usar identidad ∧ valores y, ante
≥2 candidatos, reportar ambigüedad en vez de dar de baja la fila equivocada"*.

La razón concreta: **en Nivel 0 todos los rolls son 0**, y lo que se desmonta es casi todo Nivel 0.
Ahí la firma de identidad colapsa a (set, slot, main, nombres de substat) y dos discos distintos
del mismo set pueden compartirla. Lo único que los separa son los valores.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.db.repositories import InventoryDiscRepo


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "discos.db"
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER, slot INTEGER NOT NULL,
            main_stat TEXT, main_valor REAL, unidad_main TEXT,
            sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0, unidad1 TEXT,
            sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0, unidad2 TEXT,
            sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0, unidad3 TEXT,
            sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0, unidad4 TEXT,
            nivel INTEGER DEFAULT 0, equipado INTEGER DEFAULT 0,
            agente_asignado INTEGER, descartado INTEGER DEFAULT 0,
            score_evaluacion REAL, agentes_compatibles TEXT, notas TEXT
        );
    """)
    c.commit()
    yield c
    c.close()


def _fila(con, *, slot=1, main="HP", main_valor=2200.0, subs=(("ATK", 38.0, 0),),
          nivel=0, set_id=1, agente=None, equipado=0):
    cols = "set_id, slot, main_stat, main_valor, nivel, agente_asignado, equipado"
    vals = [set_id, slot, main, main_valor, nivel, agente, equipado]
    for i, (nombre, valor, rolls) in enumerate(subs, start=1):
        cols += f", sub{i}, val{i}, rolls{i}"
        vals += [nombre, valor, rolls]
    cur = con.execute(f"INSERT INTO inventory_discs ({cols}) VALUES ({','.join('?'*len(vals))})", vals)
    con.commit()
    return cur.lastrowid


def _registro_disco(*, slot=1, main="HP", main_valor=2200.0, subs=(("ATK", 38.0, 0),),
                    nivel=0, set_id=1):
    """Un disco tal como lo guarda `TeardownBatch._record`."""
    return {
        "set_id": set_id, "slot": slot, "nivel": nivel,
        "main": {"canon": main, "raw": main, "valor": main_valor, "unidad": "flat"},
        "subs": [{"canon": n, "raw": n, "valor": v, "unidad": "flat", "rolls": r}
                 for n, v, r in subs],
    }


# --- el caso feliz --------------------------------------------------------------------------

def test_encuentra_la_fila_del_disco_desmontado(con):
    rid = _fila(con)
    repo = InventoryDiscRepo(con)
    assert [d.id for d in repo.find_para_baja(_registro_disco())] == [rid]


def test_una_fila_ya_descartada_no_vuelve_a_aparecer(con):
    rid = _fila(con)
    repo = InventoryDiscRepo(con)
    repo.marcar_descartado(rid)
    con.commit()
    assert repo.find_para_baja(_registro_disco()) == []


# --- ⭐ lo que separa dos discos de Nivel 0: los VALORES ---------------------------------------

def test_en_nivel_0_los_valores_son_lo_unico_que_distingue(con):
    """Dos discos con la MISMA identidad (set, slot, nivel, main, substats con rolls 0) y
    distinto valor de substat. La firma de identidad sola los confunde; los valores no."""
    a = _fila(con, subs=(("ATK", 38.0, 0),))
    b = _fila(con, subs=(("ATK", 57.0, 0),))
    repo = InventoryDiscRepo(con)
    assert [d.id for d in repo.find_para_baja(_registro_disco(subs=(("ATK", 38.0, 0),)))] == [a]
    assert [d.id for d in repo.find_para_baja(_registro_disco(subs=(("ATK", 57.0, 0),)))] == [b]


def test_el_valor_del_main_tambien_distingue(con):
    a = _fila(con, main_valor=2200.0)
    _fila(con, main_valor=1830.0)
    repo = InventoryDiscRepo(con)
    assert [d.id for d in repo.find_para_baja(_registro_disco(main_valor=2200.0))] == [a]


def test_gemelos_reales_devuelven_los_dos(con):
    """Indistinguibles de verdad ⇒ 2 candidatos. El caller debe ABSTENERSE, no elegir."""
    _fila(con); _fila(con)
    repo = InventoryDiscRepo(con)
    assert len(repo.find_para_baja(_registro_disco())) == 2


# --- lo que NO tiene que matchear -------------------------------------------------------------

@pytest.mark.parametrize("cambio", [
    {"slot": 2}, {"nivel": 3}, {"set_id": 2}, {"main": "ATK"},
    {"subs": (("DEF", 38.0, 0),)},          # otro substat
    {"subs": (("ATK", 38.0, 1),)},          # mismo substat, otro rolls
])
def test_no_matchea_si_algo_de_la_identidad_difiere(con, cambio):
    _fila(con)
    repo = InventoryDiscRepo(con)
    assert repo.find_para_baja(_registro_disco(**cambio)) == []


def test_tolera_ruido_de_ocr_en_el_valor(con):
    """Los dos lados vienen de OCR de pantallas distintas: 38.0 y 38.04 son el mismo disco."""
    rid = _fila(con, subs=(("ATK", 38.0, 0),))
    repo = InventoryDiscRepo(con)
    assert [d.id for d in repo.find_para_baja(_registro_disco(subs=(("ATK", 38.04, 0),)))] == [rid]

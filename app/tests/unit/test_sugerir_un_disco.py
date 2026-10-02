"""Paso 8 (SPEC 2026-10-01): `sugerir_un_disco`, la sugerencia en vivo de UN disco.

Una sola autoridad con la pantalla Discos: para cada disco del inventario, lo que dice en vivo es
lo que `generar` dice de él antes de cruzarlo con las demás (`resolver_conflictos`). Sobre una
COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.sugerencias import contexto_motor, generar, por_disco, sugerir_un_disco
from app.db.repositories import agentes_cambiaron

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")
CAMPOS = ("tipo", "disc_id", "destino_id", "slot", "origen", "reemplazo_id", "delta", "prioridad")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("paso8") / "copia.db"
    shutil.copy(DB_REAL, p)
    agentes_cambiaron()
    yield p
    agentes_cambiaron()


@pytest.fixture(scope="module")
def con(db):
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _nucleo(s: dict | None):
    return None if s is None else tuple(s.get(k) for k in CAMPOS)


def test_en_vivo_dice_lo_mismo_que_discos_para_todo_el_inventario(db, con):
    rep = por_disco(generar(db))
    pares = {s["disc_id_2"] for sd in rep.values() for s in [sd.propia] if s and s.get("disc_id_2")}
    c = contexto_motor(con)
    distintos, n = [], 0
    for d in c.activos:
        if d.id in pares or (d.id in rep and rep[d.id].propia and rep[d.id].propia["tipo"] == "armar_2pc"):
            continue
        esperado = rep[d.id].propia if d.id in rep else None
        vivo = sugerir_un_disco(con, d, c).propia
        n += 1
        if _nucleo(vivo) != _nucleo(esperado):
            distintos.append((d.id, _nucleo(esperado), _nucleo(vivo)))
    assert n > 300
    assert distintos == []


def test_un_equipado_bien_puesto_no_tiene_nada_que_hacer(db, con):
    rep = por_disco(generar(db))
    c = contexto_motor(con)
    quieto = next(d for d in c.activos if d.equipado and d.agente_asignado and d.id not in rep)
    assert sugerir_un_disco(con, quieto, c).propia is None


def test_un_drop_que_no_esta_en_la_db_se_evalua(con):
    c = contexto_motor(con)
    base = next(d for d in c.libres if d.nivel == 15)
    s = sugerir_un_disco(con, replace(base, id=-1), c).propia
    assert s is not None and s["disc_id"] == -1


def test_la_rama_mover_esta_viva(con):
    """`_clasificar` es compartida con `generar`: la paridad no ve si se rompe en los dos lados.
    Ancla propia: hoy el inventario tiene movimientos (9 el 2026-10-01). Si algún día no queda
    ninguno, armar el caso en la copia en vez de saltear el test."""
    c = contexto_motor(con)
    movs = [s for d in c.activos if d.equipado and d.agente_asignado
            for s in [sugerir_un_disco(con, d, c).propia] if s]
    assert movs and all(s["tipo"] == "mover" and s["origen"] for s in movs)


def test_un_libre_sin_nivel_leido_no_sugiere(con):
    c = contexto_motor(con)
    base = next(d for d in c.libres)
    assert sugerir_un_disco(con, replace(base, id=-2, nivel=None), c).propia is None

"""El build objetivo en el motor: R19 (de dónde sale) y R20 (un set fuera del objetivo no es
candidato; no se desarma un set objetivo activo).

Caso 12 (SPEC, 2026-09-25): el motor mandaba Armonía umbría a Ye Shunguang, "que no genera
réplicas", y el disco le rompía el 2pc de Tecno tetraodóntido sin costo. Gatillo y Grace llevan un
4pc que la guía no lista y Daniel lo declaró: "son builds mías que veo óptimas".
"""
from __future__ import annotations

import shutil
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from app.core.recommender import Cambio, _elegir, evaluar_cambio, evaluar_salida
from app.core.score_normalizer import ScoringContext
from app.core.scoring import set_valido
from app.db.repositories import (
    AgentRepo, ArchetypeRepo, BuildDeclarado, Disc, resolver_build_objetivo,
)

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"

# La guía de un PJ de ejemplo: 4pc 10 (2pc 20 recomendado, 21) y 4pc 11 (2pc 22).
GUIA = [(10, [(1, 20, True), (2, 21, False)]), (11, [(1, 22, True)])]


# --- R19 ------------------------------------------------------------------------------------

def test_lo_declarado_manda_aunque_la_guia_no_lo_nombre():
    assert resolver_build_objetivo(BuildDeclarado(99, 98), {10: 4, 20: 2}, GUIA) == (99, 98, "declarado")


def test_lo_equipado_si_la_guia_lo_avala():
    assert resolver_build_objetivo(None, {11: 4, 22: 2}, GUIA) == (11, 22, "equipado")
    assert resolver_build_objetivo(None, {10: 4, 21: 2}, GUIA) == (10, 21, "equipado")


def test_equipado_con_un_2pc_que_la_guia_no_combina_toma_el_recomendado():
    """Burnice: 4pc Jazz Caótico (en la guía) + 2pc Blues Libre (no combinado con ese 4pc)."""
    assert resolver_build_objetivo(None, {10: 4, 22: 2}, GUIA) == (10, 20, "equipado")


def test_4pc_fuera_de_la_guia_o_sin_4pc_toma_el_primero_de_la_guia():
    assert resolver_build_objetivo(None, {77: 4, 20: 2}, GUIA) == (10, 20, "guia_fuera")
    assert resolver_build_objetivo(None, {10: 3, 20: 2, 21: 1}, GUIA) == (10, 20, "guia_sin_4pc")


def test_sin_guia_ni_declaracion_no_hay_objetivo():
    assert resolver_build_objetivo(None, {10: 4}, []) == (None, None, None)


def test_guia_sin_2pc_deja_el_2pc_libre():
    """Evelyn: la guía no da 2pc para sus 4pc."""
    assert resolver_build_objetivo(None, {}, [(10, [])]) == (10, None, "guia_sin_4pc")


# --- R20 ------------------------------------------------------------------------------------

class _PJ:
    def __init__(self, s4, s2):
        self.set_4p_id, self.set_2p_id = s4, s2


def _disco(set_id, slot=1, i=1, subs=None, nivel=15):
    return Disc(id=i, set_id=set_id, slot=slot, main_stat="HP", main_valor=2200.0, main_unidad=None,
                subs=subs or [], nivel=nivel, equipado=0, agente_asignado=None)


def test_set_valido():
    assert set_valido(_disco(10), _PJ(10, 20)) and set_valido(_disco(20), _PJ(10, 20))
    assert not set_valido(_disco(41), _PJ(10, 20))
    assert set_valido(_disco(41), _PJ(None, None))           # sin objetivo no se restringe
    assert set_valido(_disco(41), _PJ(10, None))             # 2pc libre


def _cambio(delta, rompe=False):
    return Cambio(agente_id=1, agente_nombre="x", slot=1, delta=delta, delta_disco=delta,
                  delta_sets=0.0, rompe_objetivo=rompe)


def test_elegir_no_toma_un_cambio_que_desarma_el_objetivo():
    class A:
        prioridad = "normal"
    assert _elegir([(A(), None, _cambio(5.0, rompe=True))]) is None
    assert _elegir([(A(), None, _cambio(5.0, rompe=True)), (A(), None, _cambio(1.0))])[2].delta == 1.0


# --- sobre la DB (copia) --------------------------------------------------------------------

@pytest.fixture
def con(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _agente(con, nombre):
    return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)


def _set(con, nombre):
    return con.execute("SELECT id FROM disc_sets WHERE nombre = ?", (nombre,)).fetchone()[0]


def test_caso_12_armonia_umbria_no_es_candidata_para_ye_shunguang(con):
    ye = _agente(con, "Ye Shunguang")
    assert not set_valido(_disco(_set(con, "Armonía umbría")), ye)
    assert set_valido(_disco(_set(con, "Balada de aguas blancas")), ye)


def test_gatillo_y_grace_usan_lo_que_declaro_daniel(con):
    gatillo, grace = _agente(con, "Gatillo"), _agente(con, "Grace")
    assert (gatillo.set_4p_id, gatillo.set_2p_id, gatillo.origen_build) == (
        _set(con, "Armonía umbría"), _set(con, "Tecno Pícido"), "declarado")
    assert (grace.set_4p_id, grace.set_2p_id, grace.origen_build) == (
        _set(con, "Blues Libre"), _set(con, "Jazz Caótico"), "declarado")
    assert set_valido(_disco(_set(con, "Armonía umbría")), gatillo)


def test_no_se_desarma_un_2pc_objetivo_activo(con):
    """PJ con 4 del 4pc y 2 del 2pc objetivo: un disco del 4pc en un slot del 2pc lo deja 5+1."""
    ye = _agente(con, "Ye Shunguang")
    arch = ArchetypeRepo(con).get_by_id(ye.arquetipo_primario_id)
    s4, s2 = ye.set_4p_id, ye.set_2p_id
    build = {1: _disco(s4, 1, 1), 2: _disco(s4, 2, 2), 3: _disco(s4, 3, 3), 4: _disco(s4, 4, 4),
             5: _disco(s2, 5, 5), 6: _disco(s2, 6, 6)}
    nuevo = _disco(s4, 5, 50, subs=[("Prob. Crítica", 9.6, None, 3), ("Daño Crítico", 14.4, None, 2)])
    assert evaluar_cambio(ye, arch, build, nuevo, ScoringContext(), lambda _: None).rompe_objetivo
    mismo_set = _disco(s2, 5, 51, subs=[("Prob. Crítica", 9.6, None, 3)])
    assert not evaluar_cambio(ye, arch, build, mismo_set, ScoringContext(), lambda _: None).rompe_objetivo


def test_al_origen_no_se_le_desarma_el_objetivo_al_sacarle_un_disco(con):
    """Sacarle a Ye un disco de su 2pc objetivo activo: ni el slot vacío ni un reemplazo del 4pc
    valen como "no pierde"."""
    ye = _agente(con, "Ye Shunguang")
    arch = ArchetypeRepo(con).get_by_id(ye.arquetipo_primario_id)
    s4, s2 = ye.set_4p_id, ye.set_2p_id
    build = {1: _disco(s4, 1, 1), 2: _disco(s4, 2, 2), 3: _disco(s4, 3, 3), 4: _disco(s4, 4, 4),
             5: _disco(s2, 5, 5), 6: _disco(s2, 6, 6)}
    libre_4pc = _disco(s4, 5, 60, subs=[("Prob. Crítica", 9.6, None, 3), ("Daño Crítico", 14.4, None, 2)])
    salida = evaluar_salida(build[5], ye, arch, build, [libre_4pc], ScoringContext(), lambda _: None)
    assert salida.mejor_delta < 0 and salida.reemplazo_id is None


def test_un_disco_excelente_de_un_set_que_nadie_usa_se_guarda_no_se_descarta(con):
    """R20 decide a quién se le SUGIERE; guardar o descartar sigue siendo por rol. Daniel: "un
    disco perfecto, pero no para la actualidad sino para el futuro"."""
    from app.core.recommender import recomendar
    from app.db.repositories import DiscSetRepo, InventoryDiscRepo
    agentes = AgentRepo(con)
    usados = {s for a in agentes.get_all() for s in (a.set_4p_id, a.set_2p_id) if s is not None}
    libre_de_todos = next(r[0] for r in con.execute("SELECT id FROM disc_sets ORDER BY id") if r[0] not in usados)
    disco = Disc(id=999999, set_id=libre_de_todos, slot=4, main_stat="Prob. Crítica", main_valor=24.0,
                 main_unidad=None, nivel=15, equipado=0, agente_asignado=None,
                 subs=[("Daño Crítico", 19.2, None, 3), ("ATK%", 6.0, None, 1),
                       ("Perforación", 18.0, None, 1), ("ATK", 19.0, None, 0)])
    inv = InventoryDiscRepo(con)
    rec = recomendar(disco, agentes, ArchetypeRepo(con), DiscSetRepo(con), ScoringContext(),
                     builds=inv.find_equipped_by_agent, libres=[])
    assert rec.tipo == "reserva", rec.tipo


def test_dejar_vacio_un_slot_del_2pc_objetivo_no_cuenta_como_no_pierde(con):
    """El disco que se saca RESTA (líneas que a Ye no le sirven): vaciar el slot "mejoraría" el
    puntaje, pero desarma su 2pc objetivo activo — que el motor no sabe valorar."""
    ye = _agente(con, "Ye Shunguang")
    arch = ArchetypeRepo(con).get_by_id(ye.arquetipo_primario_id)
    s4, s2 = ye.set_4p_id, ye.set_2p_id
    malo = _disco(s2, 5, 5, subs=[("DEF%", 14.4, None, 2), ("HP", 448.0, None, 3)])
    build = {1: _disco(s4, 1, 1), 2: _disco(s4, 2, 2), 3: _disco(s4, 3, 3), 4: _disco(s4, 4, 4),
             5: malo, 6: _disco(s2, 6, 6)}
    salida = evaluar_salida(malo, ye, arch, build, [], ScoringContext(), lambda _: None)
    assert salida.mejor_delta < 0

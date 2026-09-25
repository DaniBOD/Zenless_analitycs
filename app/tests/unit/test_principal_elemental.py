"""Un Bono Daño de OTRO elemento es un principal equivocado (R9).

Hallado al correr el motor sobre el inventario entero (paso 7b, 2026-09-22): los arquetipos aceptan
en el slot 5 los seis "Bono Daño X" y nadie lo cruzaba con el elemento del PJ. El motor mandaba un
Bono Daño Fuego a Lycaon (Hielo) y uno Eléctrico a Piper (Físico). Lumen es el único elemento sin
Bono Daño en el juego (confirmado in-game el 2026-07-29).
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace

import pytest

from app.core.recommender import evaluar_salida, recomendar
from app.core.score_normalizer import ScoringContext
from app.core.scoring import principal_valido
from app.db.repositories import Agent, AgentRepo, Archetype, Disc
from app.tests.unit.test_optimizer_build_actual import MIYABI_ID, REAL_DB_PATH, _insert_disc

CTX = ScoringContext()
ELEMENTALES = ["Bono Daño Físico", "Bono Daño Fuego", "Bono Daño Hielo", "Bono Daño Eléctrico",
               "Bono Daño Éter", "Bono Daño Viento"]
ARCH = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0},
    substats_perjudiciales={}, threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=ELEMENTALES + ["ATK%"],
    mains_6=["ATK%"],
)


def _pj(pj_id, elemento):
    return Agent(id=pj_id, nombre=f"pj_{elemento}", arquetipo_primario_id=1,
                 arquetipo_primario_code="ATK_DPS", threshold_equip=0.75, threshold_upgrade=0.5,
                 substat_preferences={}, elemento=elemento)


def _disco(disc_id, main, dueno=None):
    subs = [("Prob. Crítica", None, None, 2), ("Daño Crítico", None, None, 2),
            ("ATK%", None, None, 1), ("ATK", None, None, 0)]
    return Disc(id=disc_id, set_id=900, slot=5, main_stat=main, main_valor=None, main_unidad=None,
                subs=subs, nivel=15, equipado=1 if dueno else 0, agente_asignado=dueno)


@pytest.mark.parametrize("elemento, main, esperado", [
    ("Fuego", "Bono Daño Fuego", True),
    ("Fuego", "Bono Daño Hielo", False),
    ("Hielo", "Bono Daño Fuego", False),
    ("Físico", "Bono Daño Eléctrico", False),
    ("Fuego", "ATK%", True),                 # el no elemental no depende del elemento
    ("Lumen", "Bono Daño Éter", False),      # no existe Bono Daño Lumen: ninguno le sirve
    ("Lumen", "ATK%", True),
    (None, "Bono Daño Hielo", True),         # sin elemento cargado no se restringe (B2)
])
def test_el_bono_de_dano_tiene_que_ser_de_su_elemento(elemento, main, esperado):
    assert principal_valido(_disco(1, main), ARCH, _pj(1, elemento)) is esperado


def test_sin_pj_sigue_mirando_solo_el_arquetipo():
    assert principal_valido(_disco(1, "Bono Daño Hielo"), ARCH) is True
    assert principal_valido(_disco(1, "DEF%"), ARCH) is False


class _Repos:
    def __init__(self, agentes):
        self._a = agentes

    def get_all(self):
        return self._a

    def get_by_id(self, _):
        return ARCH

    def get_archetypes_for_set(self, _):
        return []

    def get_bonus(self, _):
        return (None, None, None)


def test_un_libre_de_fuego_va_al_pj_de_fuego_aunque_el_de_hielo_lo_necesite_mas():
    """Al de Hielo le falta el slot 5 entero (ganaría más), pero el disco no es suyo."""
    hielo, fuego = _pj(1, "Hielo"), _pj(2, "Fuego")
    builds = {1: {}, 2: {5: _disco(20, "Bono Daño Fuego", dueno=2)}}
    builds[2][5] = replace(builds[2][5], subs=[("ATK", None, None, 0)])
    repo = _Repos([hielo, fuego])
    rec = recomendar(_disco(10, "Bono Daño Fuego"), repo, _Repos([ARCH]), repo, CTX,
                     builds=lambda i: builds.get(i, {}))
    assert rec.agente_id == fuego.id
    assert rec.movimiento is not None and rec.movimiento.agente_id == fuego.id


def test_un_reemplazo_de_otro_elemento_no_repone():
    """A (Fuego) no queda cubierto por un libre de Hielo, por bueno que sea."""
    a = _pj(1, "Fuego")
    suyo = _disco(10, "Bono Daño Fuego", dueno=1)
    salida = evaluar_salida(suyo, a, ARCH, {5: suyo}, [_disco(11, "Bono Daño Hielo")], CTX,
                            lambda _: None)
    assert salida.reemplazo_id is None and salida.mejor_delta < 0


def test_el_repositorio_carga_el_elemento():
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    con = sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        agentes = AgentRepo(con).get_all()
        esperado = {r["id"]: r["elemento"] for r in con.execute("SELECT id, elemento FROM agents")}
    finally:
        con.close()
    assert {a.id: a.elemento for a in agentes} == esperado
    assert esperado[MIYABI_ID] == "Hielo"


@pytest.fixture
def db_miyabi(tmp_path):
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    con = sqlite3.connect(copia)
    with con:
        con.execute("DELETE FROM optimizer_pending_actions")
        con.execute("DELETE FROM inventory_disc_evaluations")
        con.execute("DELETE FROM inventory_discs")
        con.execute("UPDATE agents SET protected_build = 0")
    con.close()
    return copia


_SUBS = [("Prob. Crítica", 7.2, 2), ("Daño Crítico", 14.4, 2), ("ATK%", 6.0, 1), ("ATK", 19.0, 0)]


@pytest.mark.parametrize("main, entra", [("Bono Daño Hielo", True), ("Bono Daño Fuego", False)])
def test_el_optimizador_no_le_pone_a_miyabi_un_bono_de_otro_elemento(db_miyabi, main, entra):
    """El control (Hielo) tiene que entrar: si no, el caso no discrimina nada."""
    from app.core.optimizer import BuildOptimizer
    con = sqlite3.connect(db_miyabi)
    con.row_factory = sqlite3.Row
    # Un set de SU build objetivo (R20): el caso es del elemento, no del set.
    set_objetivo = AgentRepo(con).get_by_id(MIYABI_ID).set_4p_id
    with con:
        disco = _insert_disc(con, 5, set_objetivo, main, 30.0, _SUBS, agente=None, equipado=0)
    con.close()
    opt = BuildOptimizer(db_miyabi)
    try:
        res = opt.best_builds(MIYABI_ID, persist=False, top_n=1)
    finally:
        opt.close()
    usados = {d.disc_id for b in res.builds for d in b.discos}
    assert (disco in usados) is entra

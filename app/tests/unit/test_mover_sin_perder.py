"""Mover un disco de un PJ a otro sólo si EL QUE LO TIENE NO PIERDE (etapa 1, paso 7).

Decisión de Daniel (2026-09-22): "…aparece un disco que ya le sirve a otro PJ (sin perjudicar al
PJ que lo tiene equipado o si está libre)". Reemplaza la regla del 2026-09-12, que movía si el
destino ganaba más de lo que perdía el origen. Ahora el origen tiene que quedar igual o mejor,
contando que puede recibir un disco LIBRE del inventario en ese slot.

La misma regla (`evaluar_salida`) la usan las sugerencias y el optimizador (B1).
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace

import pytest

from app.core.recommender import evaluar_salida, recomendar
from app.core.score_normalizer import ScoringContext
from app.db.repositories import Agent, Archetype, Disc

CTX = ScoringContext()
DPS_ARCH = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                        "Perforación": 0.7},
    substats_perjudiciales={"DEF": -0.8, "HP": -0.5}, threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=["ATK%"], mains_6=["ATK%"],
)
A = Agent(id=1, nombre="A", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
          threshold_equip=0.75, threshold_upgrade=0.50,
          substat_preferences={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.5})
B = Agent(id=2, nombre="B", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
          threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})

BUENO = [("Prob. Crítica", 1), ("Daño Crítico", 1), ("ATK%", 3), ("Perforación", 0)]
FLOJO = [("HP", 2), ("DEF", 2), ("ATK", 1), ("Perforación", 0)]


def _disco(disc_id, subs, dueno=None, slot=2, set_id=900):
    return Disc(id=disc_id, set_id=set_id, slot=slot, main_stat="ATK", main_valor=None,
                main_unidad=None, subs=[(s, None, None, m) for s, m in subs], nivel=15,
                equipado=1 if dueno else 0, agente_asignado=dueno)


def _sin_bonos(_):
    return None


class _Repos:
    def __init__(self, agentes):
        self._a = agentes

    def get_all(self):
        return self._a

    def get_by_id(self, _):
        return DPS_ARCH

    def get_archetypes_for_set(self, _):
        return []

    def get_bonus(self, _):
        return (None, None, None)


def _reco(disco, builds, libres, agentes=(A, B)):
    repo = _Repos(list(agentes))
    return recomendar(disco, repo, _Repos([DPS_ARCH]), repo, CTX,
                      builds=lambda i: builds.get(i, {}), libres=libres)


# --- evaluar_salida --------------------------------------------------------------------------

def test_sin_reemplazo_el_origen_pierde():
    disco = _disco(10, BUENO, dueno=A.id)
    salida = evaluar_salida(disco, A, DPS_ARCH, {2: disco}, [], CTX, _sin_bonos)
    assert salida.mejor_delta < 0 and salida.reemplazo_id is None


def test_con_un_reemplazo_igual_de_bueno_no_pierde():
    disco = _disco(10, BUENO, dueno=A.id)
    otro = _disco(11, BUENO)
    salida = evaluar_salida(disco, A, DPS_ARCH, {2: disco}, [otro], CTX, _sin_bonos)
    assert salida.mejor_delta == 0 and salida.reemplazo_id == 11


def test_sacarle_un_disco_que_le_resta_no_es_perder():
    """Dejar el slot vacío puede ser MEJOR que un disco que le resta."""
    malo = _disco(10, FLOJO, dueno=A.id)
    assert evaluar_salida(malo, A, DPS_ARCH, {2: malo}, [], CTX, _sin_bonos).mejor_delta > 0


def test_un_reemplazo_de_otro_slot_no_sirve():
    disco = _disco(10, BUENO, dueno=A.id)
    otro_slot = _disco(11, BUENO, slot=3)
    assert evaluar_salida(disco, A, DPS_ARCH, {2: disco}, [otro_slot], CTX,
                          _sin_bonos).reemplazo_id is None


# --- recomendar() con un disco ajeno ---------------------------------------------------------

def test_le_sirve_mas_a_B_y_A_tiene_reemplazo_se_mueve():
    """A valora el ATK% a la mitad; a B le rinde más. Y A tiene un libre igual de bueno para él."""
    disco = _disco(10, BUENO, dueno=A.id)
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)}}
    rec = _reco(disco, builds, [_disco(11, BUENO)])
    assert rec.tipo == "equipar" and rec.agente_id == B.id
    m = rec.movimiento
    assert m.origen_id == A.id and m.reemplazo_id == 11 and m.delta_origen >= 0 and m.delta > 0


def test_un_reemplazo_con_atk_plano_no_repone_al_que_vale_el_porcentual():
    """El mismo reemplazo pero con ATK plano +3 en vez de ATK% +3: A no valora el plano (R7), así
    que perdería 2,0 → no se mueve. (Medido: era la primera versión del test de arriba, que
    daba por "igual de bueno" un disco que para A no lo era.)"""
    disco = _disco(10, BUENO, dueno=A.id)
    plano = _disco(11, [("Prob. Crítica", 1), ("Daño Crítico", 1), ("Perforación", 0), ("ATK", 3)])
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)}}
    assert evaluar_salida(disco, A, DPS_ARCH, {2: disco}, [plano], CTX, _sin_bonos).mejor_delta < 0
    assert _reco(disco, builds, [plano]).movimiento is None


def test_si_A_pierde_no_se_mueve_aunque_B_gane_mas():
    """La regla vieja (neto > 0) lo movía: B gana más de lo que pierde A. La de Daniel, no."""
    disco = _disco(10, BUENO, dueno=A.id)
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)}}
    rec = _reco(disco, builds, [])
    assert rec.movimiento is None


def test_origen_protegido_no_se_toca():
    A_prot = replace(A, protected_build=True)
    disco = _disco(10, BUENO, dueno=A.id)
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)}}
    rec = _reco(disco, builds, [_disco(11, BUENO)], agentes=(A_prot, B))
    assert rec.movimiento is None


def test_si_B_no_gana_no_se_mueve():
    """Aunque A no pierda: mover sin ganar no es una mejora."""
    disco = _disco(10, BUENO, dueno=A.id)
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, BUENO + [], dueno=B.id)}}
    builds[B.id][2] = _disco(12, [("Prob. Crítica", 5), ("Daño Crítico", 0), ("ATK%", 0),
                                  ("Perforación", 0)], dueno=B.id)
    rec = _reco(disco, builds, [_disco(11, BUENO)])
    assert rec.movimiento is None


# --- el optimizador aplica la MISMA regla ---------------------------------------------------

from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH, _insert_disc  # noqa: E402


@pytest.fixture
def db(tmp_path):
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    ellen = con.execute("SELECT id FROM agents WHERE nombre='Ellen'").fetchone()["id"]
    # un ATK_DPS SIN pesos propios: valora el ATK% entero, Ellen al 0,8
    otro = con.execute(
        "SELECT a.id FROM agents a WHERE a.rol='Ataque' AND a.nombre <> 'Ellen' AND NOT EXISTS "
        "(SELECT 1 FROM agent_substat_preferences p WHERE p.agente_id=a.id) ORDER BY a.id LIMIT 1"
    ).fetchone()["id"]
    with con:
        con.execute("DELETE FROM optimizer_pending_actions")
        con.execute("DELETE FROM inventory_disc_evaluations")
        con.execute("DELETE FROM inventory_discs")
        con.execute("UPDATE agents SET protected_build = 0")
    con.close()
    return copia, ellen, otro


_ATK = [("ATK%", 15.0, 4), ("Perforación", 9.0, 0), ("ATK", 19.0, 0), ("Prob. Crítica", 2.4, 0)]


def _run(path, agente_id):
    from app.core.optimizer import BuildOptimizer
    opt = BuildOptimizer(path)
    try:
        return opt.best_builds(agente_id, persist=False, top_n=1)
    finally:
        opt.close()


def test_optimizador_no_le_saca_a_ellen_lo_que_no_puede_reponer(db):
    path, ellen, otro = db
    con = sqlite3.connect(path)
    with con:
        ajeno = _insert_disc(con, 1, 48, "HP", 2200.0, _ATK, agente=ellen, equipado=1)
    con.close()
    result = _run(path, otro)
    assert ajeno not in {d.disc_id for b in result.builds for d in b.discos}


def test_optimizador_admite_el_ajeno_si_ellen_tiene_un_libre_que_la_repone(db):
    """La admisión, mirada directo: con un libre igual para Ellen, el swap pasa y dice cuál la
    repone; sin él, queda marcado `origen_pierde`. (Mirar la build final no alcanza: con un libre
    idéntico al alcance, el optimizador puede preferir el libre y el caso no discrimina nada.)"""
    from app.core.optimizer import (BuildOptimizer, _admite_disco_ajeno, _disc_base_score,
                                    _swap_de_disco_ajeno)
    from app.core.recommender import _bonos_2pc_desde
    path, ellen, otro = db
    con = sqlite3.connect(path)
    with con:
        ajeno = _insert_disc(con, 1, 48, "HP", 2200.0, _ATK, agente=ellen, equipado=1)
        repone = _insert_disc(con, 1, 48, "HP", 2200.0, _ATK, agente=None, equipado=0)
    con.close()

    opt = BuildOptimizer(path)
    try:
        dest = opt._agent_repo.get_by_id(otro)
        arch = opt._arch_repo.get_by_id(dest.arquetipo_primario_id)
        disc = opt._inv_disc_repo.get_by_id(ajeno)
        bonos = _bonos_2pc_desde(opt._set_repo)

        def _swap(libres):
            sw = _swap_de_disco_ajeno(disc, dest, _disc_base_score(disc, dest, arch, opt._ctx),
                                      opt._agent_repo, opt._arch_repo, opt._ctx)
            opt._marcar_si_el_origen_pierde(sw, disc, libres, bonos)
            return sw

        con_repuesto = _swap([opt._inv_disc_repo.get_by_id(repone)])
        sin_repuesto = _swap([])
    finally:
        opt.close()

    assert con_repuesto["neto"] > 0, "precondición: a `otro` le rinde más que a Ellen"
    assert _admite_disco_ajeno(con_repuesto) and con_repuesto["reemplazo_id"] == repone
    assert not _admite_disco_ajeno(sin_repuesto) and sin_repuesto["motivo"] == "origen_pierde"

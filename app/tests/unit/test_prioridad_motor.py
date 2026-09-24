"""La prioridad de buildeo en el motor de discos (mig 42).

Daniel (2026-09-24), con los stats reales: 32 de 108 movimientos iban a Piper, "que no uso casi
nada", sacándole discos a PJs que sí usa. Eligió que la prioridad BLOQUEE:

- nunca se sugiere sacarle un disco a un PJ para dárselo a otro de prioridad MÁS BAJA;
- entre iguales sigue "el que lo tiene no pierde";
- los discos van primero a los de prioridad alta ("recibe discos primero").

La regla es una sola (`recommender.puede_recibir_de` / `_elegir`, B1): la usan el recomendador,
el optimizador y el orden de los conflictos del reporte de sugerencias.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.recommender import nivel_prioridad, puede_recibir_de
from app.tests.unit.test_mover_sin_perder import A, B, BUENO, CTX, DPS_ARCH, FLOJO, _disco, _reco

C = replace(B, id=3, nombre="C")


def _con(pj, prioridad):
    return replace(pj, prioridad=prioridad)


# --- la regla --------------------------------------------------------------------------------

def test_niveles():
    assert (nivel_prioridad("alta"), nivel_prioridad("normal"), nivel_prioridad("baja")) == (2, 1, 0)
    assert nivel_prioridad(None) == nivel_prioridad("xx") == 1, "desconocido cuenta como normal"


@pytest.mark.parametrize("destino, origen, puede", [
    ("alta", "normal", True), ("normal", "normal", True), ("baja", "baja", True),
    ("normal", "alta", False), ("baja", "normal", False), ("baja", "alta", False),
])
def test_puede_recibir_de(destino, origen, puede):
    assert puede_recibir_de(_con(B, destino), _con(A, origen)) is puede


# --- mover un disco ajeno --------------------------------------------------------------------
# El caso base de `test_mover_sin_perder`: el disco de A le rinde más a B y A tiene un libre que
# lo repone. Sin prioridades, se mueve.

def _mover(pa, pb):
    disco = _disco(10, BUENO, dueno=A.id)
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)}}
    return _reco(disco, builds, [_disco(11, BUENO)], agentes=(_con(A, pa), _con(B, pb)))


def test_sin_prioridades_se_mueve_como_antes():
    assert _mover("normal", "normal").agente_id == B.id


@pytest.mark.parametrize("pa, pb", [("alta", "normal"), ("normal", "baja"), ("alta", "baja")])
def test_no_se_le_saca_un_disco_a_uno_de_mayor_prioridad(pa, pb):
    assert _mover(pa, pb).movimiento is None


@pytest.mark.parametrize("pa, pb", [("baja", "normal"), ("normal", "alta"), ("alta", "alta")])
def test_hacia_igual_o_mayor_prioridad_si_se_mueve(pa, pb):
    rec = _mover(pa, pb)
    assert rec.agente_id == B.id and rec.movimiento.origen_id == A.id


def test_entre_destinos_posibles_gana_el_de_mayor_prioridad():
    """B ganaría más (tiene un disco FLOJO), C gana menos (tiene uno a medias), pero C es alta."""
    disco = _disco(10, BUENO, dueno=A.id)
    medio = [("Prob. Crítica", 1), ("Daño Crítico", 0), ("ATK%", 0), ("Perforación", 0)]
    builds = {A.id: {2: disco}, B.id: {2: _disco(12, FLOJO, dueno=B.id)},
              C.id: {2: _disco(13, medio, dueno=C.id)}}
    agentes = (A, B, _con(C, "alta"))
    rec = _reco(disco, builds, [_disco(11, BUENO)], agentes=agentes)
    assert rec.agente_id == C.id
    sin_prio = _reco(disco, builds, [_disco(11, BUENO)], agentes=(A, B, C))
    assert sin_prio.agente_id == B.id, "precondición: sin prioridades, B gana más"


# --- un disco libre ---------------------------------------------------------------------------

def test_un_libre_va_primero_al_de_prioridad_alta():
    libre = _disco(10, BUENO)
    medio = [("Prob. Crítica", 1), ("Daño Crítico", 0), ("ATK%", 0), ("Perforación", 0)]
    builds = {B.id: {2: _disco(12, FLOJO, dueno=B.id)}, C.id: {2: _disco(13, medio, dueno=C.id)}}
    assert _reco(libre, builds, [], agentes=(B, C)).agente_id == B.id, "precondición"
    assert _reco(libre, builds, [], agentes=(B, _con(C, "alta"))).agente_id == C.id


def test_si_al_de_alta_no_lo_mejora_va_al_que_si():
    """La prioridad ordena entre los que MEJORAN: no le da un disco peor a un PJ de alta."""
    medio = [("Prob. Crítica", 1), ("Daño Crítico", 0), ("ATK%", 0), ("Perforación", 0)]
    libre = _disco(10, medio)          # a B (slot vacío) le suma; a C (lleva uno BUENO) le resta
    builds = {B.id: {}, C.id: {2: _disco(13, BUENO, dueno=C.id)}}
    rec = _reco(libre, builds, [], agentes=(B, _con(C, "alta")))
    assert rec.tipo == "equipar" and rec.agente_id == B.id


def test_un_pj_de_baja_igual_recibe_si_nadie_mas_lo_quiere():
    libre = _disco(10, BUENO)
    builds = {B.id: {2: _disco(12, FLOJO, dueno=B.id)}, C.id: {2: _disco(13, BUENO, dueno=C.id)}}
    assert _reco(libre, builds, [], agentes=(_con(B, "baja"), C)).agente_id == B.id


# --- un disco sin terminar (MEJORAR) ---------------------------------------------------------

def test_a_quien_subirlo_sigue_el_mismo_orden():
    from app.tests.unit.test_mejorar_comparativo import BUENO as BUENO5, D369, FLOJO as FLOJO5
    from app.tests.unit.test_mejorar_comparativo import _disco as _d5, _pj, _reco as _reco5
    flojo, medio = _pj(1, "con_flojo"), _pj(2, "con_medio")
    medio_subs = [("Prob. Crítica", 0), ("HP", 0), ("DEF", 0), ("Perforación", 0)]
    builds = {1: {5: _d5(10, FLOJO5, 15, dueno=1)}, 2: {5: _d5(20, medio_subs, 15, dueno=2)}}
    assert _reco5(_d5(1, D369, 0), builds, [flojo, medio]).agente_id == flojo.id, "precondición"
    rec = _reco5(_d5(1, D369, 0), builds, [flojo, replace(medio, prioridad="alta")])
    assert rec.tipo == "mejorar" and rec.agente_id == medio.id
    del BUENO5


# --- el optimizador aplica la MISMA regla ---------------------------------------------------

class _AgRepo:
    def __init__(self, *agentes):
        self._a = {a.id: a for a in agentes}

    def get_by_id(self, i):
        return self._a.get(i)


class _ArRepo:
    def get_by_id(self, _):
        return DPS_ARCH


@pytest.mark.parametrize("pa, pb, admite", [
    ("normal", "normal", True), ("alta", "normal", False), ("baja", "normal", True),
])
def test_el_optimizador_no_le_saca_a_uno_de_mayor_prioridad(pa, pb, admite):
    from app.core.optimizer import _admite_disco_ajeno, _swap_de_disco_ajeno
    origen, destino = _con(A, pa), _con(B, pb)
    disco = _disco(10, BUENO, dueno=A.id)
    swap = _swap_de_disco_ajeno(disco, destino, 99.0, _AgRepo(origen, destino), _ArRepo(), CTX)
    assert _admite_disco_ajeno(swap) is admite
    if not admite:
        assert swap["motivo"] == "origen_con_mas_prioridad"


# --- los conflictos del reporte -------------------------------------------------------------

def test_en_un_conflicto_se_queda_el_disco_el_de_mayor_prioridad():
    """Dos sugerencias quieren el mismo disco #11: una para un PJ normal que gana más, otra para
    uno de alta. Se lo lleva el de alta; la otra queda marcada, no desaparece."""
    from app.scripts.sugerir_movimientos import Sugerencia, resolver_conflictos
    normal = Sugerencia("equipar", 11, "#11", "B", 2, 2, delta=9.0)
    alta = Sugerencia("equipar", 11, "#11", "C", 3, 2, delta=1.0, prioridad="alta")
    resolver_conflictos([normal, alta])
    assert alta.conflicto is None and normal.conflicto is not None


def test_en_un_conflicto_entre_iguales_gana_el_que_mas_mejora():
    from app.scripts.sugerir_movimientos import Sugerencia, resolver_conflictos
    poco = Sugerencia("equipar", 11, "#11", "B", 2, 2, delta=1.0)
    mucho = Sugerencia("equipar", 11, "#11", "C", 3, 2, delta=9.0)
    resolver_conflictos([poco, mucho])
    assert mucho.conflicto is None and poco.conflicto is not None

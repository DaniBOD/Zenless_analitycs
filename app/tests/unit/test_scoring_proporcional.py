"""El puntaje cuenta el STAT, y el principal equivocado descalifica (etapa 1, paso 2 — 2026-09-22).

**Proporcional.** Una línea valía `peso × (1 + 0,25·mejoras)`: un Daño Crítico +4 —cinco veces el
stat de uno +0— contaba 2,0 contra 1,0. Daniel juzga por el stat que el disco da ("DC 175 → 189"),
no por cuántas líneas buenas tiene. Ahora una línea vale `peso × (1 + mejoras)`.

**Un máximo que existe.** El máximo teórico suponía las 5 mejoras en CADA una de las 4 líneas (20
mejoras: un disco imposible). Con mejoras proporcionales eso dejaba todo puntaje real muy por
debajo de 1. Ahora es el disco perfecto de verdad: las 4 mejores líneas y las 5 mejoras en la mejor.

**El principal.** Caso 6 de Daniel (R9): un principal equivocado mata al disco para ese rol, con
secundarios perfectos y todo. El scoring viejo le daba el peso de una línea, así que un PV % de
slot 4 con cuatro buenas líneas empataba exacto con un Daño Crítico de tres. Esa pregunta la
contestaba además el optimizador con su propio `if`: ahora hay una sola autoridad (B1).
"""
from __future__ import annotations

import pytest

import app.core.optimizer as optimizer
from app.core.recommender import recomendar
from app.core.score_normalizer import ScoringContext
from app.core.scoring import principal_valido, score_disco
from app.db.repositories import Agent, Archetype, Disc

ATK_DPS = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                        "Perforación": 0.7},
    substats_perjudiciales={"DEF": -0.8, "HP": -0.5},
    threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=["ATK%"], mains_6=["ATK%"],
)
DPS = Agent(id=1, nombre="dps", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
            threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})


def _disco(slot=2, main="ATK", subs=(), nivel=15, disc_id=1):
    return Disc(id=disc_id, set_id=999, slot=slot, main_stat=main, main_valor=None,
                main_unidad=None, subs=[(s, None, None, m) for s, m in subs], nivel=nivel,
                equipado=0, agente_asignado=None)


def _puntaje(disco, ctx=None):
    return score_disco(disco, DPS, ATK_DPS, ctx or ScoringContext())


def test_una_linea_vale_lo_que_da_de_stat():
    """Un Daño Crítico +4 tiene cinco veces el stat de uno +0: tiene que valer cinco veces más."""
    c0 = _puntaje(_disco(subs=[("Daño Crítico", 0)])).subs_positivos[0].contribucion
    c4 = _puntaje(_disco(subs=[("Daño Crítico", 4)])).subs_positivos[0].contribucion
    assert c4 == pytest.approx(5 * c0), (c0, c4)


def test_el_maximo_teorico_lo_toca_un_disco_que_existe():
    """El máximo tiene que ser un disco POSIBLE: si suma mejoras que ningún disco puede tener,
    ningún disco real se acerca a 1 y los umbrales quedan corridos.

    Es una cota, no un valor exacto por slot: en los slots 1-3 el principal no suma, y en los 4-6
    el stat del principal no puede repetirse abajo. Lo que se exige es que las líneas SÍ lleguen a
    su tope con un disco real: las 4 mejores del arquetipo y las 5 mejoras en la mejor."""
    top4 = sorted(ATK_DPS.substats_positivos.values(), reverse=True)[:4]
    maximo = sum(top4) + 5 * top4[0] + 1.0 + 0.5            # líneas + principal + nivel
    assert ScoringContext().score_maximo_teorico(ATK_DPS) == pytest.approx(maximo)

    ideal = _disco(slot=2, main="ATK", nivel=15, subs=[
        ("Prob. Crítica", 5), ("Daño Crítico", 0), ("ATK%", 0), ("Perforación", 0)])
    assert _puntaje(ideal).score_raw == pytest.approx(maximo - 1.0), \
        "sólo le falta el punto del principal, que en slot 2 no existe"


@pytest.mark.parametrize("slot,main,esperado", [
    (4, "Daño Crítico", True),
    (4, "HP%", False),          # el caso D3 de Daniel
    (5, "HP%", False),
    (6, "ATK%", True),
    (1, "HP", True),            # slots 1-3: el principal es fijo, no se pregunta
    (2, "ATK", True),
])
def test_principal_valido(slot, main, esperado):
    assert principal_valido(_disco(slot=slot, main=main), ATK_DPS) is esperado


def test_una_lista_vacia_de_principales_no_restringe():
    """Así se comportaba el optimizador antes de delegar: se conserva."""
    sin_lista = Archetype(id=2, code="X", substats_positivos={}, substats_perjudiciales={},
                          threshold_stock=0.7)
    assert principal_valido(_disco(slot=4, main="HP%"), sin_lista) is True


class _Repos:
    def get_all(self):
        return [DPS]

    def get_by_id(self, _):
        return ATK_DPS

    def get_archetypes_for_set(self, _):
        return []


class _ArchRepos(_Repos):
    def get_all(self):
        return [ATK_DPS]


def test_el_recomendador_no_propone_un_pj_con_el_principal_equivocado():
    """Secundarios perfectos y principal equivocado: para ese rol no hay candidato."""
    d3 = _disco(slot=4, main="HP%", nivel=15, subs=[
        ("Prob. Crítica", 2), ("Daño Crítico", 2), ("ATK%", 1), ("Perforación", 0)])
    rec = recomendar(d3, _Repos(), _ArchRepos(), _Repos(), ScoringContext())
    assert rec.agente_id is None and rec.tipo == "descartar", rec
    assert rec.top_candidatos == []


def test_el_optimizador_excluye_con_la_misma_regla():
    malo = _disco(slot=4, main="HP%", subs=[("Prob. Crítica", 2)], disc_id=1)
    bueno = _disco(slot=4, main="Daño Crítico", subs=[("Prob. Crítica", 2)], disc_id=2)
    cands, _ = optimizer._greedy_candidates([malo, bueno], DPS, ATK_DPS, ScoringContext())
    assert [d.id for d in cands[4]] == [2]


def test_el_optimizador_DELEGA_en_scoring(monkeypatch):
    """No alcanza con que coincidan hoy: el optimizador tiene que preguntarle a la MISMA función,
    o la próxima vez que cambie la regla se van a separar (B1)."""
    monkeypatch.setattr(optimizer, "principal_valido", lambda disc, arch: False)
    bueno = _disco(slot=4, main="Daño Crítico", subs=[("Prob. Crítica", 2)])
    cands, _ = optimizer._greedy_candidates([bueno], DPS, ATK_DPS, ScoringContext())
    assert cands[4] == []

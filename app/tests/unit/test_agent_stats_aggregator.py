"""
Tests para AgentStatsAggregator — madura stats entre capturas consecutivas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.parser_agent_stats import AgentStatsParsed, AgentStatsAggregator


def _stats(**kwargs) -> AgentStatsParsed:
    return AgentStatsParsed(**kwargs)


def test_aggregator_empty_initially():
    agg = AgentStatsAggregator()
    assert not agg.has_any
    assert agg.current_agent is None


def test_aggregator_first_merge_clones_input():
    agg = AgentStatsAggregator()
    s = _stats(nivel=60, pv=10797, ataque=2531, agente_nombre="Nangong Yu")
    result = agg.merge(s)
    assert result.nivel == 60
    assert result.pv == 10797
    assert result.ataque == 2531
    assert result.agente_nombre == "Nangong Yu"
    assert agg.has_any
    assert agg.current_agent == "Nangong Yu"


def test_aggregator_preserves_value_when_new_is_none():
    """F8 #1 captura PV. F8 #2 no captura PV. Resultado: aggregator preserva PV."""
    agg = AgentStatsAggregator()
    agg.merge(_stats(pv=10797, ataque=2531, agente_nombre="Nangong Yu"))
    # Segunda captura: PV None, pero ATK presente + nuevo DEF
    result = agg.merge(_stats(pv=None, ataque=2531, defensa=925, agente_nombre="Nangong Yu"))
    assert result.pv == 10797  # preservado del primero
    assert result.ataque == 2531
    assert result.defensa == 925


def test_aggregator_new_value_overwrites_old_when_not_none():
    """Si nuevo es no-None, gana sobre el viejo (asume que es lectura más fresca)."""
    agg = AgentStatsAggregator()
    agg.merge(_stats(pv=9999, agente_nombre="Nangong Yu"))  # valor previo (incorrecto)
    result = agg.merge(_stats(pv=10797, agente_nombre="Nangong Yu"))  # nuevo (correcto)
    assert result.pv == 10797


def test_aggregator_resets_on_agent_change():
    """Cambio de agente → reset. Los stats viejos NO contaminan al nuevo."""
    agg = AgentStatsAggregator()
    agg.merge(_stats(pv=10797, ataque=2531, agente_nombre="Nangong Yu"))
    # Cambio a otro agente
    result = agg.merge(_stats(pv=12000, agente_nombre="Yuzuha"))
    assert result.pv == 12000
    assert result.ataque is None  # se perdió porque cambió de agente
    assert result.agente_nombre == "Yuzuha"


def test_aggregator_no_reset_when_new_has_no_name():
    """Si la nueva extracción no extrajo nombre, NO resetear — fue captura parcial."""
    agg = AgentStatsAggregator()
    agg.merge(_stats(pv=10797, ataque=2531, agente_nombre="Nangong Yu"))
    # Nueva captura sin nombre identificado
    result = agg.merge(_stats(defensa=925, agente_nombre=None))
    assert result.pv == 10797  # preservado
    assert result.ataque == 2531  # preservado
    assert result.defensa == 925  # nuevo
    assert result.agente_nombre == "Nangong Yu"  # preservado


def test_aggregator_resets_on_stats_divergence_even_without_name():
    """
    Bug QA 2026-06-02: al cambiar de agente, si el OCR del nombre del nuevo
    frame falla (None), el aggregator NO debe heredar la identidad del agente
    anterior. Un salto grande de PV/Ataque (pantalla S18 estática) implica otro
    personaje → reset. (Lucy se mostraba como 'N.º 0: Anby' por esta herencia.)
    """
    agg = AgentStatsAggregator()
    # Frame 1: N.º 0: Anby identificado
    agg.merge(_stats(pv=10558, ataque=2630, agente_nombre="N.º 0: Anby"))
    # Frame 2: stats de Lucy pero nombre OCR falló (None)
    result = agg.merge(_stats(pv=12392, ataque=1774, agente_nombre=None))
    assert result.pv == 12392
    assert result.agente_nombre != "N.º 0: Anby", "heredó identidad vieja (bug)"


def test_aggregator_progressively_completes_stats():
    """
    Tres capturas parciales del mismo agente → aggregator converge a stats
    completos. Esto simula 3 F8 con OCR no-determinista frame-a-frame.
    """
    agg = AgentStatsAggregator()
    # Captura 1: nivel+PV+ATK
    agg.merge(_stats(
        nivel=60, pv=10797, ataque=2531,
        agente_nombre="Nangong Yu",
    ))
    # Captura 2: DEF+CR (sin PV ni ATK esta vez)
    agg.merge(_stats(defensa=925, prob_crit=0.194, agente_nombre="Nangong Yu"))
    # Captura 3: IMP+CD+TA+MA+ER
    result = agg.merge(_stats(
        impacto=138, dano_crit=0.932,
        tasa_anomalia=173, maestria_anomalia=305,
        recuperacion_energia=1.2,
        agente_nombre="Nangong Yu",
    ))
    # Después de las 3 capturas, TODOS los stats están presentes
    assert result.nivel == 60
    assert result.pv == 10797
    assert result.ataque == 2531
    assert result.defensa == 925
    assert result.impacto == 138
    assert result.prob_crit == 0.194
    assert result.dano_crit == 0.932
    assert result.tasa_anomalia == 173
    assert result.maestria_anomalia == 305
    assert result.recuperacion_energia == 1.2


def test_aggregator_reset_explicit():
    agg = AgentStatsAggregator()
    agg.merge(_stats(pv=10797, agente_nombre="Nangong Yu"))
    assert agg.has_any
    agg.reset()
    assert not agg.has_any
    assert agg.current_agent is None


def test_aggregator_merge_none_returns_existing():
    """merge(None) no rompe — devuelve el estado actual."""
    agg = AgentStatsAggregator()
    s1 = _stats(pv=10797, agente_nombre="Nangong Yu")
    agg.merge(s1)
    # merge(None) devuelve el agg sin cambios
    result = agg.merge(None)  # type: ignore[arg-type]
    assert result.pv == 10797

"""S18: una lectura INCOMPLETA no compromete la firma del panel (QA en vivo 2026-09-23).

Claret Flint quedó en "[parcial] falta TP (10/11)" y no se guardó nunca. La firma del panel se
comprometía con cualquier lectura UTILIZABLE (PV o ATK), así que el panel quieto no se volvía a
leer y el aggregator no tenía con qué completar. La TP de Claret, medida en vivo, falta en 1 de 6
frames seguidos: releer alcanza.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import monitor as monitor_mod
from app.core.detector import ScreenDetector, ScreenState
from app.core.monitor import Monitor
from app.core.parser_agent_stats import AgentStatsParsed

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
S18_FIXTURES = sorted(FIXTURES.glob("atributos_base_ejemplo_*.png"))

#: Claret tal como la leyó el OCR en vivo: los 11 stats del Armero.
CLARET = AgentStatsParsed(
    agente_nombre="Claret Flint", rol="Armero", nivel=60, pv=8754, defensa=2144, impacto=93,
    prob_crit=1.096, dano_crit=0.932, tasa_anomalia=80, maestria_anomalia=79,
    tasa_perforacion=0.32, dano_laceracion=1.5, acumulacion_afiladura=1.5, confianza_global=0.95,
)
SIN_TP = replace(CLARET, tasa_perforacion=None)
S18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")


class _Ocr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return ("", 0.0)


@pytest.fixture
def frame():
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    return cv2.imdecode(np.fromfile(str(S18_FIXTURES[0]), np.uint8), cv2.IMREAD_COLOR)


def _monitor(monkeypatch, lecturas):
    """Monitor cuyo parser devuelve `lecturas` en orden (la última se repite)."""
    cola = list(lecturas)
    monkeypatch.setattr(monitor_mod, "parse_agent_stats",
                        lambda f, o: cola.pop(0) if len(cola) > 1 else cola[0])
    recibidas: list[AgentStatsParsed] = []
    m = Monitor(ocr=_Ocr(), detector=ScreenDetector(),
                on_agent_stats=lambda stats, st: recibidas.append(replace(stats)))
    return m, recibidas


def test_una_lectura_incompleta_se_relee_y_completa(frame, monkeypatch):
    """El caso de Claret: sin TP en la primera, con TP en la segunda → completa."""
    m, recibidas = _monitor(monkeypatch, [SIN_TP, CLARET])
    m._dispatch_state(frame, S18)
    m._dispatch_state(frame, S18)            # MISMO panel: antes se salteaba
    assert len(recibidas) == 2
    assert recibidas[-1].tasa_perforacion == pytest.approx(0.32)


def test_una_lectura_completa_si_compromete_la_firma(frame, monkeypatch):
    """Lo que el gate protege (RNF-06): un panel quieto y COMPLETO no se vuelve a leer."""
    m, recibidas = _monitor(monkeypatch, [CLARET])
    for _ in range(3):
        m._dispatch_state(frame, S18)
    assert len(recibidas) == 1


def test_un_panel_que_nunca_completa_se_deja_de_releer_y_se_avisa(frame, monkeypatch, caplog):
    tope = monitor_mod._S18_REINTENTOS_INCOMPLETO
    m, recibidas = _monitor(monkeypatch, [SIN_TP])
    with caplog.at_level(logging.WARNING, logger="app.core.monitor"):
        for _ in range(tope + 5):
            m._dispatch_state(frame, S18)
    assert len(recibidas) == tope
    avisos = [r.getMessage() for r in caplog.records if "sigue incompleto" in r.getMessage()]
    assert len(avisos) == 1 and "Claret Flint" in avisos[0] and "TP" in avisos[0]


def test_volver_a_entrar_reintenta_el_panel_que_quedo_incompleto(frame, monkeypatch):
    tope = monitor_mod._S18_REINTENTOS_INCOMPLETO
    m, recibidas = _monitor(monkeypatch, [SIN_TP] * tope + [CLARET])
    for _ in range(tope + 2):
        m._dispatch_state(frame, S18)
    assert len(recibidas) == tope
    m._agent_stats_screen_logged = False     # lo que hace el dispatch al salir de S18
    m._dispatch_state(frame, S18)
    assert len(recibidas) == tope + 1 and recibidas[-1].tasa_perforacion is not None


def test_el_tope_es_por_pj(frame, monkeypatch):
    """Otro PJ incompleto arranca su cuenta de cero, no hereda el tope del anterior."""
    tope = monitor_mod._S18_REINTENTOS_INCOMPLETO
    otro = replace(SIN_TP, agente_nombre="Ellen", rol="Ataque")
    m, recibidas = _monitor(monkeypatch, [SIN_TP] * tope + [otro, otro])
    for _ in range(tope + 2):
        m._dispatch_state(frame, S18)
    # Tras el tope de Claret la firma queda comprometida: el cambio de PJ lo destraba el panel
    # (otra firma). Acá el frame es el mismo, así que se simula esa nueva firma.
    m._s18_last_sig = None
    m._dispatch_state(frame, S18)
    m._dispatch_state(frame, S18)
    assert len(recibidas) == tope + 2

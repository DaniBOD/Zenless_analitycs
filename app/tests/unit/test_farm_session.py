"""Gate de confianza por flujo de farmeo — `FarmSession`.

El flujo orgánico S13 (selección de set) → S14 (pre-combate) → combate → S2 (resultados)
indica que viene un farmeo de discos real. `FarmSession` ARMA una ventana temporal al ver
S13/S14 y la consulta al llegar a S2, para distinguir un farmeo de otros "resultados de
desafío" (anti-falso-positivo). Time-windowed: entre S14 y S2 hay combate (S1/S12), así que
no dependemos de adyacencia estricta de estados.
"""
from __future__ import annotations

from app.core.farm_session import FarmSession


def test_arma_con_s13():
    fs = FarmSession(window_s=600.0)
    fs.on_state("S13", ts=100.0)
    assert fs.is_armed(ts=100.0) is True


def test_arma_con_s14():
    fs = FarmSession(window_s=600.0)
    fs.on_state("S14", ts=100.0)
    assert fs.is_armed(ts=150.0) is True


def test_no_arma_con_estado_no_farmeo():
    fs = FarmSession(window_s=600.0)
    fs.on_state("S18", ts=100.0)   # perfil de agente, nada que ver con farmeo
    assert fs.is_armed(ts=100.0) is False


def test_no_armado_de_entrada():
    fs = FarmSession(window_s=600.0)
    assert fs.is_armed(ts=0.0) is False


def test_decae_tras_la_ventana():
    fs = FarmSession(window_s=600.0)
    fs.on_state("S13", ts=100.0)
    assert fs.is_armed(ts=699.0) is True     # dentro de la ventana (100 + 600)
    assert fs.is_armed(ts=701.0) is False    # ventana vencida


def test_s14_refresca_la_ventana():
    fs = FarmSession(window_s=600.0)
    fs.on_state("S13", ts=100.0)
    fs.on_state("S14", ts=500.0)             # re-arma desde 500
    assert fs.is_armed(ts=1050.0) is True    # 500 + 600 = 1100, sigue vivo

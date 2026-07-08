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


# --- predicción de sets S13 → S2 -------------------------------------------

def test_sin_prediccion_de_entrada():
    fs = FarmSession(window_s=600.0)
    assert fs.predicted(ts=0.0) is None


def test_prediccion_se_lee_dentro_de_la_ventana():
    fs = FarmSession(window_s=600.0)
    sets = [(52, "Wuthering Salon"), (53, "The Sky Ablaze")]
    fs.set_prediction("El piloto y el meca rebelde", sets, ts=100.0)
    pred = fs.predicted(ts=300.0)
    assert pred is not None
    node, got = pred
    assert node == "El piloto y el meca rebelde"
    assert got == sets


def test_prediccion_expira_con_la_ventana():
    fs = FarmSession(window_s=600.0)
    fs.set_prediction("Puños y balas", [(32, "Hormone Punk"), (30, "Fanged Metal")], ts=100.0)
    assert fs.predicted(ts=699.0) is not None    # dentro de la ventana (100 + 600)
    assert fs.predicted(ts=701.0) is None        # ventana vencida


def test_set_prediction_no_rompe_el_gate_temporal():
    fs = FarmSession(window_s=600.0)
    fs.set_prediction("Colmillo y hacha", [(31, "Freedom Blues"), (38, "Polar Metal")], ts=100.0)
    # La predicción NO arma por sí sola el gate de farmeo (eso lo hace on_state).
    assert fs.is_armed(ts=100.0) is False
    fs.on_state("S13", ts=100.0)
    assert fs.is_armed(ts=100.0) is True

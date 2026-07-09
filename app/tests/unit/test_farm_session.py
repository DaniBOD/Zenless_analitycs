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


# --- persistencia + restore (contexto de QA entre reinicios) ----------------

def test_set_prediction_persiste_breadcrumb(tmp_path):
    """Con state_path, set_prediction deja un breadcrumb JSON en disco."""
    p = tmp_path / "farm_state.json"
    fs = FarmSession(window_s=600.0, state_path=p)
    fs.set_prediction("El piloto y el meca rebelde",
                      [(52, "Wuthering Salon"), (53, "The Sky Ablaze")], ts=100.0)
    assert p.exists()


def test_restore_recarga_prediccion_y_arma_gate(tmp_path):
    """Un proceso escribe el breadcrumb; otro (reinicio) lo restaura: `predicted` vuelve y
    el gate queda armado (contexto=flujo), con ventana fresca desde el ts de restore."""
    p = tmp_path / "farm_state.json"
    sets = [(52, "Wuthering Salon"), (53, "The Sky Ablaze")]
    FarmSession(window_s=600.0, state_path=p).set_prediction(
        "El piloto y el meca rebelde", sets, ts=100.0)
    # Reinicio: monotonic arranca de cero → restauramos con ts fresco (0.0).
    fs2 = FarmSession(window_s=600.0, state_path=p)
    assert fs2.predicted(ts=0.0) is None          # todavía nada en memoria
    restored = fs2.restore(ts=0.0)
    assert restored is not None
    node, got = restored
    assert node == "El piloto y el meca rebelde"
    assert got == sets
    pred = fs2.predicted(ts=10.0)
    assert pred is not None and pred[1] == sets    # ventana fresca (0 + 600)
    assert fs2.is_armed(ts=10.0) is True           # gate armado → contexto=flujo


def test_restore_conserva_set_id_none(tmp_path):
    """Branch & Blade Song no tiene set_id (None); el round-trip lo conserva."""
    p = tmp_path / "farm_state.json"
    sets = [(None, "Branch & Blade Song"), (25, "Notes From the Chained")]
    FarmSession(window_s=600.0, state_path=p).set_prediction("Dueto monstruoso", sets, ts=100.0)
    restored = FarmSession(window_s=600.0, state_path=p).restore(ts=0.0)
    assert restored is not None and restored[1] == sets


def test_restore_sin_archivo_devuelve_none(tmp_path):
    """Sin breadcrumo previo (primer QA), restore no encuentra nada y no rompe."""
    fs = FarmSession(window_s=600.0, state_path=tmp_path / "no_existe.json")
    assert fs.restore(ts=0.0) is None


def test_restore_sin_state_path_devuelve_none():
    """Sin state_path configurado (arranque de producción), restore es no-op."""
    assert FarmSession(window_s=600.0).restore(ts=0.0) is None


def test_set_prediction_sin_state_path_no_escribe(tmp_path):
    """Sin state_path, set_prediction NO persiste (producción no deja rastro)."""
    fs = FarmSession(window_s=600.0)   # sin state_path
    fs.set_prediction("X", [(1, "A"), (2, "B")], ts=100.0)
    assert list(tmp_path.iterdir()) == []

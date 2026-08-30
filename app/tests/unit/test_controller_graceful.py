"""
Tests del MonitorController — verifica que maneja gracefully el caso de
"Tesseract no instalado" sin crashear, emitiendo error_occurred en lugar.

No requiere Tesseract ni PySide6 con event loop activo; usa qtbot via pytest-qt
si está disponible, o un fallback con QCoreApplication mínimo.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Skip todo el módulo si PySide6 no está disponible (no debería en este repo,
# pero por defensa)
PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication
import sys


@pytest.fixture(scope="module")
def qapp():
    """QCoreApplication mínima para que los signals funcionen sin GUI."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def test_controller_emits_error_when_no_ocr_backend(qapp):
    """Si NINGUN backend OCR está disponible (ni PaddleOCR ni Tesseract),
    start() debe emitir error_occurred (no crashear).

    Hito 2.8 (2026-05-31): PaddleOCR pasó a ser el backend primario. El error
    solo ocurre cuando AMBOS backends faltan. Para simularlo: forzar que el
    import de paddleocr falle + la búsqueda de Tesseract devuelva None.

    La elección de backend se mudó a `app.core.ocr_worker` cuando el OCR pasó a correr en otro
    proceso (2026-08-29): el hijo no puede importar la UI.
    """
    import builtins
    from app.ui.controller import MonitorController

    received_errors = []

    ctrl = MonitorController()
    ctrl.error_occurred.connect(lambda msg: received_errors.append(msg))

    _real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "paddleocr" or name.startswith("paddleocr."):
            raise ImportError("simulated: paddleocr no disponible")
        return _real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import), \
         patch("app.core.ocr_worker._buscar_tesseract", return_value=None):
        ctrl.start()

    assert len(received_errors) == 1, "Debe emitir exactamente 1 error"
    assert "PaddleOCR" in received_errors[0]
    assert "Tesseract" in received_errors[0]
    assert ctrl._monitor is None, "El monitor NO debe haberse creado"


def test_controller_stop_when_not_started_is_noop(qapp):
    """Llamar stop() sin haber arrancado no debe lanzar excepción."""
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    ctrl.stop()  # no debe crashear


def test_controller_toggle_pause_when_not_started_is_noop(qapp):
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    # Sin monitor activo, toggle_pause es un no-op silencioso
    ctrl.toggle_pause()


def test_agent_stats_log_edge_triggered(qapp):
    """
    El log de stats S18 es EDGE-triggered (2026-06-07): un resultado idéntico no
    re-emite las líneas de log; un cambio de valor sí; `conf` NO gatilla; un
    cambio de estado resetea (re-entrar loguea 1 vez). El binding del panel
    (agent_stats_detected) se emite SIEMPRE.

    Actualizado 2026-07-26: el fixture pasó de parcial a COMPLETO. Un parcial ya
    no loguea las líneas de stats (gate de completitud, pedido de Daniel) — esa
    conducta se prueba en `test_controller_stats_gate`. Lo que este test cubre
    —edge-triggering, conf inocua, reset por estado— no cambió.
    """
    from dataclasses import replace
    from app.ui.controller import MonitorController
    from app.core.parser_agent_stats import AgentStatsParsed
    from app.core.detector import ScreenState

    ctrl = MonitorController()
    logs: list = []
    binds: list = []
    ctrl.log_message.connect(lambda m: logs.append(m))
    ctrl.agent_stats_detected.connect(lambda p: binds.append(p))

    st = ScreenState("S18", 1.0, "tmpl")
    s1 = AgentStatsParsed(
        nivel=60, pv=10000, ataque=2500, defensa=900, impacto=86,
        prob_crit=0.242, dano_crit=0.50, tasa_anomalia=112, maestria_anomalia=330,
        tasa_perforacion=0.0, recuperacion_energia=2.16,
        agente_nombre="Nangong Yu", rol="Aturdimiento", elemento="Éter",
        confianza_global=0.9,
    )

    ctrl._on_agent_stats_from_monitor(s1, st)
    n1 = len(logs)
    assert n1 == 3 and len(binds) == 1       # [reconocido]+[stats]+[completo]

    # Idéntico → no re-loguea; el panel sí se actualiza.
    ctrl._on_agent_stats_from_monitor(s1, st)
    assert len(logs) == n1, "log idéntico no debe re-emitir"
    assert len(binds) == 2

    # Cambia un stat → re-loguea.
    ctrl._on_agent_stats_from_monitor(replace(s1, ataque=2600), st)
    assert len(logs) > n1
    n2 = len(logs)

    # Solo cambia conf → NO gatilla.
    ctrl._on_agent_stats_from_monitor(replace(s1, ataque=2600, confianza_global=0.4), st)
    assert len(logs) == n2, "cambio de conf no debe gatillar"

    # Cambio de estado resetea la firma → re-loguea aunque los datos sean iguales.
    ctrl._on_state_from_monitor(ScreenState("S15", 1.0, "tmpl"))
    n3 = len(logs)
    ctrl._on_agent_stats_from_monitor(replace(s1, ataque=2600), st)
    assert len(logs) > n3

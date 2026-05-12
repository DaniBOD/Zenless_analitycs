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


def test_controller_emits_error_when_tesseract_missing(qapp):
    """Si no hay Tesseract, start() debe emitir error_occurred (no crashear)."""
    from app.ui.controller import MonitorController

    received_errors = []

    ctrl = MonitorController()
    ctrl.error_occurred.connect(lambda msg: received_errors.append(msg))

    # Mockear find_tesseract para que devuelva None
    with patch("app.ui.controller._find_tesseract", return_value=None):
        ctrl.start()

    assert len(received_errors) == 1, "Debe emitir exactamente 1 error"
    assert "Tesseract" in received_errors[0]
    assert "winget" in received_errors[0]
    assert ctrl._monitor is None, "El monitor NO debe haberse creado"


def test_controller_force_scan_emits_error_when_not_started(qapp):
    """force_scan sin monitor activo emite error informativo."""
    from app.ui.controller import MonitorController

    received = []
    ctrl = MonitorController()
    ctrl.error_occurred.connect(lambda msg: received.append(msg))
    ctrl.force_scan()

    assert len(received) == 1
    assert "Iniciar" in received[0]


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

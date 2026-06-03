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
    import de paddleocr falle + _find_tesseract devuelva None.
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
         patch("app.ui.controller._find_tesseract", return_value=None):
        ctrl.start()

    assert len(received_errors) == 1, "Debe emitir exactamente 1 error"
    assert "PaddleOCR" in received_errors[0]
    assert "Tesseract" in received_errors[0]
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

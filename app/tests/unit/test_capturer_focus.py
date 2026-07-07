"""
Gate de captura por foco de ventana (anti-FP explorador).

Cubre:
- `WindowBounds` acepta/expone `hwnd` (default 0).
- `is_zzz_focused` (función pura).
- `Monitor._get_frame()` saltea la captura cuando el juego no está en primer plano,
  emitiendo el diagnóstico de pausa una sola vez (edge-trigger) y sin anular la ventana.
"""
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.core.capturer import WindowBounds, is_zzz_focused
from app.core import monitor as monitor_mod
from app.core.monitor import Monitor


def test_windowbounds_hwnd_default_and_set():
    assert WindowBounds(0, 0, 800, 600).hwnd == 0
    wb = WindowBounds(0, 0, 800, 600, "ZZZ", 123)
    assert wb.hwnd == 123
    assert wb.title == "ZZZ"


@pytest.mark.parametrize("fg, zzz, expected", [
    (5, 5, True),    # el juego está en primer plano
    (5, 9, False),   # otra ventana al frente
    (5, 0, False),   # hwnd del juego desconocido
    (0, 0, False),   # ambos desconocidos
])
def test_is_zzz_focused(fg, zzz, expected):
    assert is_zzz_focused(fg, zzz) is expected


def _make_monitor(diagnostics):
    return Monitor(
        ocr=MagicMock(),
        detector=MagicMock(),
        on_diagnostic=diagnostics.append,
        capture_only_focused=True,
    )


def test_get_frame_pausa_cuando_no_enfocado(monkeypatch):
    diagnostics: list[str] = []
    mon = _make_monitor(diagnostics)
    win = WindowBounds(0, 0, 800, 600, "ZZZ", 123)

    monkeypatch.setattr(monitor_mod, "find_zzz_window", lambda: win)
    monkeypatch.setattr(monitor_mod, "get_foreground_window", lambda: 999)  # otra ventana
    monkeypatch.setattr(monitor_mod, "capture_window",
                        lambda w: pytest.fail("no debe capturar sin foco"))
    monkeypatch.setattr(monitor_mod.time, "sleep", lambda s: None)

    # Primera pasada: encuentra ventana, detecta sin foco → None, pausa + diagnóstico.
    assert mon._get_frame() is None
    assert mon._window is win           # NO se anula (evita re-búsqueda cada frame)
    assert mon._focus_paused is True

    # Segunda pasada sin foco: NO re-emite el diagnóstico de pausa (edge-trigger).
    assert mon._get_frame() is None
    pausas = [d for d in diagnostics if "segundo plano" in d]
    assert len(pausas) == 1


def test_get_frame_reanuda_al_recuperar_foco(monkeypatch):
    diagnostics: list[str] = []
    mon = _make_monitor(diagnostics)
    mon._window = WindowBounds(0, 0, 800, 600, "ZZZ", 123)
    mon._focus_paused = True             # veníamos pausados

    fake_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    monkeypatch.setattr(monitor_mod, "get_foreground_window", lambda: 123)  # juego al frente
    monkeypatch.setattr(monitor_mod, "capture_window", lambda w: fake_frame)

    frame = mon._get_frame()
    assert frame is fake_frame
    assert mon._focus_paused is False
    assert any("reanudada" in d for d in diagnostics)


def test_gate_desactivado_captura_siempre(monkeypatch):
    """Con capture_only_focused=False, captura aunque el juego no esté al frente."""
    mon = Monitor(ocr=MagicMock(), detector=MagicMock(), capture_only_focused=False)
    mon._window = WindowBounds(0, 0, 800, 600, "ZZZ", 123)

    fake_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    monkeypatch.setattr(monitor_mod, "get_foreground_window", lambda: 999)
    monkeypatch.setattr(monitor_mod, "capture_window", lambda w: fake_frame)

    assert mon._get_frame() is fake_frame

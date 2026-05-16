"""
Tests para Monitor._process_agent_stats — observabilidad de excepciones.

Verifica que cuando parse_agent_stats falla, el callback `on_diagnostic`
recibe el mensaje (para que el LivePanel del .exe lo muestre como
`[diag] error parseando stats S18: ...`), en lugar de quedar en stderr
suprimido por el .exe windowed.

Cubre dos rutas de excepción:
  - parse_agent_stats raises
  - on_agent_stats callback raises (e.g. controller crashea)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.detector import ScreenState  # noqa: E402
from app.core.monitor import Monitor  # noqa: E402
from app.core.parser_agent_stats import AgentStatsParsed  # noqa: E402


class _OkOcr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return ("PV Ataque Defensa", 0.8)

    def number(self, img):
        return (0.0, 0.0)


def _frame() -> np.ndarray:
    return np.zeros((1440, 2560, 3), dtype=np.uint8)


def _s18_state() -> ScreenState:
    return ScreenState("S18", 0.75, "deep_detect:test", method="deep_detect")


def test_diagnostic_emitido_cuando_parse_agent_stats_falla(monkeypatch):
    """Si parse_agent_stats raise → on_diagnostic recibe '[diag] error parseando S18: ...'."""
    from app.core import monitor as monitor_mod

    def _boom(frame, ocr):
        raise RuntimeError("ROI fuera de rango")

    monkeypatch.setattr(monitor_mod, "parse_agent_stats", _boom)

    received_diag: list[str] = []
    received_stats: list = []

    m = Monitor(
        ocr=_OkOcr(),
        detector=MagicMock(),
        on_agent_stats=lambda s, st: received_stats.append(s),
        on_diagnostic=received_diag.append,
    )
    m._process_agent_stats(_frame(), _s18_state())

    assert len(received_stats) == 0, "on_agent_stats no debe invocarse si parse falló"
    assert len(received_diag) == 1
    msg = received_diag[0]
    assert "error parseando stats S18" in msg
    assert "RuntimeError" in msg
    assert "ROI fuera de rango" in msg


def test_diagnostic_emitido_cuando_callback_on_agent_stats_falla(monkeypatch):
    """Si parse OK pero el callback explota → on_diagnostic reporta 'error en callback agent_stats'."""
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda frame, ocr: AgentStatsParsed(nivel=60, pv=10797, ataque=2531, defensa=925),
    )

    received_diag: list[str] = []

    def _bad_callback(stats, state):
        raise ValueError("payload no serializable")

    m = Monitor(
        ocr=_OkOcr(),
        detector=MagicMock(),
        on_agent_stats=_bad_callback,
        on_diagnostic=received_diag.append,
    )
    m._process_agent_stats(_frame(), _s18_state())

    assert len(received_diag) == 1
    msg = received_diag[0]
    assert "error en callback agent_stats" in msg
    assert "ValueError" in msg
    assert "payload no serializable" in msg


def test_callback_normal_no_emite_diagnostic(monkeypatch):
    """Path feliz: parse OK + callback OK → on_diagnostic NO se invoca."""
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda frame, ocr: AgentStatsParsed(nivel=60, pv=10797, ataque=2531, defensa=925),
    )

    received_diag: list[str] = []
    received_stats: list = []

    m = Monitor(
        ocr=_OkOcr(),
        detector=MagicMock(),
        on_agent_stats=lambda s, st: received_stats.append(s),
        on_diagnostic=received_diag.append,
    )
    m._process_agent_stats(_frame(), _s18_state())

    assert len(received_diag) == 0, f"Path feliz no debe emitir diag, recibió: {received_diag}"
    assert len(received_stats) == 1
    assert received_stats[0].pv == 10797


def test_falta_de_on_diagnostic_no_rompe(monkeypatch):
    """Si on_diagnostic es None y parse falla, no debe lanzar — solo loggear."""
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda frame, ocr: (_ for _ in ()).throw(RuntimeError("test")),
    )

    m = Monitor(
        ocr=_OkOcr(),
        detector=MagicMock(),
        on_agent_stats=None,
        on_diagnostic=None,
    )
    # No debe lanzar (silencioso es OK si no hay callbacks, log.exception se encarga)
    m._process_agent_stats(_frame(), _s18_state())


def test_on_diagnostic_excepcion_no_propaga(monkeypatch):
    """Si on_diagnostic mismo lanza al recibir el error, el monitor sigue vivo."""
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda frame, ocr: (_ for _ in ()).throw(RuntimeError("parse falla")),
    )

    def _broken_diag(msg):
        raise RuntimeError("diag rota")

    m = Monitor(
        ocr=_OkOcr(),
        detector=MagicMock(),
        on_agent_stats=None,
        on_diagnostic=_broken_diag,
    )
    # No debe propagar la excepción del on_diagnostic
    m._process_agent_stats(_frame(), _s18_state())

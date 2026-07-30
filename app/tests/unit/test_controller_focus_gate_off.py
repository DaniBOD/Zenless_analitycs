"""El gate por foco va APAGADO por defecto: la captura no se pausa sola en segundo plano.

## Por qué

Pedido de Daniel, repetido: la captura **no debe cortarse sola**. Eran dos mecanismos distintos y
se apagaron en dos pasadas — primero el auto-stop del watcher de ventana (2026-07-25, ver
`test_controller_auto_stop`), y ahora este, que no detiene el monitor pero **pausa la captura**
mientras el juego no esté al frente: desde afuera se ve igual de mudo.

## Lo que se resigna, dicho explícito

`capture_window()` usa `mss.grab()` sobre la **región de pantalla** donde está la ventana del
juego, no sobre su superficie propia. Con el juego tapado por otra ventana se capturan esos
píxeles ajenos y el detector los clasifica → falso positivo en el log. Eso es exactamente lo que
el gate evitaba (`Dev_IA/2026-07-07_Gate_Captura_Por_Foco_Anti_FP.md`).

Se acepta a cambio de que la sesión no se interrumpa sola. Para reproducir el comportamiento viejo
en una sesión puntual: `DANIBOD_FOCUS_GATE=1` (o `qa_launch.ps1 -FocusGate`).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_DEFAULTS = Path(__file__).resolve().parents[2] / "config" / "defaults.toml"


def test_el_default_del_toml_esta_apagado():
    with open(_DEFAULTS, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["monitor"]["solo_capturar_si_enfocado"] is False


def test_el_helper_devuelve_false_sin_overrides(monkeypatch):
    from app.ui.controller import _capture_only_focused
    monkeypatch.delenv("DANIBOD_FOCUS_GATE", raising=False)
    monkeypatch.delenv("DANIBOD_NO_FOCUS_GATE", raising=False)
    assert _capture_only_focused() is False


def test_el_fallback_tambien_esta_apagado(monkeypatch):
    """Si el TOML no se puede leer, el default sigue siendo OFF.

    Importa porque el `.exe` empaquetado podría no encontrar el archivo: ahí el fallback ES el
    comportamiento real, y un fallback en True reintroduciría la pausa sin que nadie la pidiera.
    """
    from app.ui import controller as ctrl
    monkeypatch.delenv("DANIBOD_FOCUS_GATE", raising=False)
    monkeypatch.delenv("DANIBOD_NO_FOCUS_GATE", raising=False)
    # `open` es un builtin: se inyecta un global en el módulo, que tiene precedencia sobre él.
    monkeypatch.setattr(ctrl, "open",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no existe")),
                        raising=False)
    assert ctrl._capture_only_focused() is False


def test_se_puede_volver_a_activar_por_entorno(monkeypatch):
    """Apagarlo por defecto no es lo mismo que borrarlo: el camino anti-FP sigue disponible."""
    from app.ui.controller import _capture_only_focused
    monkeypatch.delenv("DANIBOD_NO_FOCUS_GATE", raising=False)
    monkeypatch.setenv("DANIBOD_FOCUS_GATE", "1")
    assert _capture_only_focused() is True


def test_activar_gana_sobre_desactivar(monkeypatch):
    """Con las dos variables puestas manda la que ACTIVA: pedir explícitamente el gate es una
    decisión, y `DANIBOD_NO_FOCUS_GATE` hoy solo repite el default."""
    from app.ui.controller import _capture_only_focused
    monkeypatch.setenv("DANIBOD_FOCUS_GATE", "1")
    monkeypatch.setenv("DANIBOD_NO_FOCUS_GATE", "1")
    assert _capture_only_focused() is True


def test_el_monitor_tampoco_gatea_por_defecto():
    """El default del propio `Monitor` también va en False, para que construirlo directo (tests,
    scripts, herramientas) no reintroduzca la pausa por la puerta de atrás."""
    import inspect

    from app.core.monitor import Monitor
    assert inspect.signature(Monitor.__init__).parameters["capture_only_focused"].default is False


def test_con_el_gate_apagado_el_frame_no_se_descarta(monkeypatch):
    """La prueba de comportamiento, no de configuración: con el gate en False, `_get_frame` no
    consulta el foco y devuelve el frame igual."""
    from unittest.mock import MagicMock

    import app.core.monitor as mon_mod

    consultas = {"n": 0}

    def _foreground_espia():
        consultas["n"] += 1
        return 999

    monkeypatch.setattr(mon_mod, "get_foreground_window", _foreground_espia)
    monkeypatch.setattr(mon_mod, "capture_window", lambda w: "FRAME")

    m = mon_mod.Monitor(ocr=MagicMock(), detector=MagicMock())
    m._window = MagicMock(hwnd=1)
    assert m._get_frame() == "FRAME"
    assert consultas["n"] == 0, "no debería ni preguntar por el foco con el gate apagado"

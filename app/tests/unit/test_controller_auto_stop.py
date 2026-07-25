"""El watcher de ventana NO debe detener la captura por su cuenta.

## Por qué

Pedido de Daniel (2026-07-25): *"desactiva la capacidad de detener la captura en segundo plano,
eso me ha generado inconsistencias"*. Había **dos** mecanismos que la cortaban solos y en la
primera pasada solo se apagó uno (el gate por foco, `DANIBOD_NO_FOCUS_GATE`). El otro es este:
un timer cada 3 s que llama `stop()` en cuanto `find_zzz_window()` devuelve None.

Detenerse ahí es peor que seguir: `Monitor._get_frame` ya maneja la ausencia de ventana —avisa
una vez, duerme 4 s y la re-busca— así que el costo de seguir vivo es despreciable, y en cambio
un `stop()` deja al usuario con la app abierta y sin capturar, sin que nada se lo diga. Si el
watcher se equivoca un solo ciclo (alt-tab, cambio de resolución, la ventana un instante sin
título), la sesión se corta y se pierde lo que estuviera en curso — una tanda de desmontaje, por
ejemplo, que para cuando se nota ya destruyó los discos.

Arrancar solo sigue estando bien: eso agrega capacidad, no la quita.
"""
from __future__ import annotations

import pytest


class _CtrlDoble:
    """Doble mínimo: solo la lógica del watcher, sin Qt ni OCR ni DB."""

    def __init__(self):
        self._monitor = object()          # "hay monitor corriendo"
        self._was_window_present = True
        self._auto_detect_enabled = True
        self.stop_llamado = 0
        self.start_llamado = 0

    def stop(self):
        self.stop_llamado += 1

    def start(self):
        self.start_llamado += 1


@pytest.fixture
def ctrl(monkeypatch):
    from app.ui.controller import MonitorController
    c = _CtrlDoble()
    c._check_zzz_window = MonitorController._check_zzz_window.__get__(c, _CtrlDoble)
    return c


def _sin_ventana(monkeypatch):
    import app.core.capturer as cap
    monkeypatch.setattr(cap, "find_zzz_window", lambda: None)


def _con_ventana(monkeypatch):
    import app.core.capturer as cap
    monkeypatch.setattr(cap, "find_zzz_window", lambda: object())


def test_perder_la_ventana_no_detiene_la_captura(ctrl, monkeypatch):
    _sin_ventana(monkeypatch)
    ctrl._check_zzz_window()
    assert ctrl.stop_llamado == 0, "el watcher cortó la captura solo"


def test_perder_la_ventana_queda_registrado(ctrl, monkeypatch, caplog):
    """Que no corte no significa que lo esconda: el usuario tiene que poder ver en el log que el
    juego desapareció, sobre todo si después nota que faltan capturas."""
    caplog.set_level("INFO")
    _sin_ventana(monkeypatch)
    ctrl._check_zzz_window()
    assert any("ventana" in r.message.lower() for r in caplog.records), caplog.text


def test_se_puede_reactivar_el_corte_a_pedido(ctrl, monkeypatch):
    """Queda como opt-in explícito por si alguna vez conviene (p.ej. ahorrar CPU en una sesión
    larga sin el juego). El default es NO cortar."""
    monkeypatch.setenv("DANIBOD_AUTO_STOP_ON_WINDOW_LOST", "1")
    _sin_ventana(monkeypatch)
    ctrl._check_zzz_window()
    assert ctrl.stop_llamado == 1


def test_seguir_arrancando_solo_al_aparecer_la_ventana(ctrl, monkeypatch):
    """Lo que se apaga es el corte, no el arranque: eso agrega capacidad, no la quita."""
    ctrl._monitor = None
    ctrl._was_window_present = False
    _con_ventana(monkeypatch)
    ctrl._check_zzz_window()
    assert ctrl.start_llamado == 1

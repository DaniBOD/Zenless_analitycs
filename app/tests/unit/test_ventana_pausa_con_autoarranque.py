"""La pausa del sidebar tiene que habilitarse aunque el monitor arranque DURANTE la construcción.

QA en vivo del 2026-09-17: con ZZZ abierto, `set_auto_detect(True)` arranca el monitor en el acto,
dentro de `MainWindow._setup_ui`, y `monitor_started` salía antes de que el sidebar estuviera
conectado. Los botones quedaron deshabilitados toda la sesión y parecían texto de relleno.

Los tests del sidebar no lo podían ver (le llaman `on_monitor_started` a mano), y el smoke con la
ventana real tampoco: corrió con `DANIBOD_NO_AUTOSTART=1`, o sea que **fabricó el caso que anda**.
Por eso acá se construye la `MainWindow` VERDADERA, con el auto-arranque simulado en el mismo punto
en que ocurre de verdad. Arrancar el monitor real no hace falta: lo que importa es el ORDEN.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def test_con_zzz_abierto_al_arrancar_la_pausa_queda_habilitada(monkeypatch):
    from app.ui.controller import MonitorController

    monkeypatch.setenv("DANIBOD_READONLY", "1")
    monkeypatch.delenv("DANIBOD_NO_AUTOSTART", raising=False)
    # ZZZ ya abierto: el watcher arranca el monitor en el acto, que es lo que hace `start()`
    # visible hacia afuera — emitir `monitor_started`.
    monkeypatch.setattr(MonitorController, "set_auto_detect",
                        lambda self, enabled: self.monitor_started.emit())
    pedidos: list[int] = []
    monkeypatch.setattr(MonitorController, "toggle_pause", lambda self: pedidos.append(1))

    from app.main import MainWindow
    w = MainWindow()
    try:
        assert w.sidebar.btn_pausa.isEnabled(), (
            "el monitor arrancó durante la construcción y el sidebar no se enteró")
        w.sidebar.btn_pausa.click()
        assert pedidos == [1], "el botón tiene que llegar al controller"
        w._controller.pause_changed.emit(True)
        assert w.sidebar.btn_pausa.text() == "Reanudar"
    finally:
        w._tray.hide()
        w.close()
        w.deleteLater()

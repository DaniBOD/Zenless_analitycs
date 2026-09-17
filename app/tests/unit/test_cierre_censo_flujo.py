"""El flujo del botón «Cerrar pasada de censo»: sidebar → controller → monitor → diálogo (2026-09-17).

La ventana principal no se construye en los tests (abre la DB, la vista en vivo y el tray), así que
el ida y vuelta vive en `FlujoCierreCenso` con la pregunta inyectada, y acá se maneja con un
controller falso que tiene las MISMAS señales que el real. Lo que importa verificar es el efecto:
qué se volvió a pedir, qué quedó en la consola y en qué estado quedó el botón.
"""
from __future__ import annotations

import inspect
import os
import sys
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal                          # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

_INST = {
    "discos": {"registrados": 300, "total_pantalla": 411, "faltan": 111},
    "armas": None,
    "roster": {"vistos": 45, "total": 51,
               "pendientes": ["Aria", "Ellen", "Jane", "Lycaon", "Miyabi", "Nicole", "Pyrois",
                              "Soukaku", "Velina", "Yanagi"]},
}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class _Controller(QObject):
    """Las señales y los dos métodos que el flujo usa del `MonitorController` real."""
    censo_cierre_resultado = Signal(dict)
    monitor_started = Signal()
    monitor_stopped = Signal()
    pause_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.pedidos: list = []
        self.pausas = 0

    def pedir_cierre_censo(self, confirmado=None):
        self.pedidos.append(confirmado)

    def toggle_pause(self):
        self.pausas += 1


def _armar(qapp, respuesta_dialogo: bool):
    from app.ui.shell.cierre_censo import FlujoCierreCenso
    from app.ui.shell.sidebar import Sidebar
    c, sb, log, preguntas = _Controller(), Sidebar(), [], []

    def preguntar(texto):
        preguntas.append(texto)
        return respuesta_dialogo

    flujo = FlujoCierreCenso(c, sb, log.append, preguntar)
    c.monitor_started.emit()
    return c, sb, log, preguntas, flujo


def test_contract_el_controller_real_tiene_lo_que_el_flujo_usa():
    """El controller falso no sirve de nada si el real no tiene las mismas piezas."""
    from app.ui.controller import MonitorController
    for nombre in ("censo_cierre_resultado", "monitor_started", "monitor_stopped", "pause_changed",
                   "pedir_cierre_censo", "toggle_pause"):
        assert hasattr(MonitorController, nombre), nombre


def test_el_boton_pide_una_vez_sin_confirmacion(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, True)
    sb.btn_cierre.click()
    assert c.pedidos == [None]
    assert not sb.btn_cierre.isEnabled() and sb.btn_cierre.text() == "Cerrando…"


def test_aceptar_el_dialogo_re_pide_con_LA_MISMA_instantanea(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, True)
    sb.btn_cierre.click()
    c.censo_cierre_resultado.emit({"accion": "confirmar", "instantanea": _INST})
    assert c.pedidos == [None, _INST]
    assert len(preguntas) == 1
    assert not sb.btn_cierre.isEnabled(), "sigue cerrando hasta la respuesta de la segunda vuelta"


def test_cancelar_no_re_pide_y_libera_el_boton(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, False)
    sb.btn_cierre.click()
    c.censo_cierre_resultado.emit({"accion": "confirmar", "instantanea": _INST})
    assert c.pedidos == [None]
    assert any("cancelado" in l for l in log)
    assert sb.btn_cierre.isEnabled() and sb.btn_cierre.text() == "Cerrar pasada de censo"


def test_el_cierre_hecho_queda_en_la_consola_y_libera_el_boton(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, True)
    sb.btn_cierre.click()
    c.censo_cierre_resultado.emit({
        "accion": "cerrado",
        "discos": {"registrados": 405, "total_pantalla": 411, "con_dueno": 300, "libres": 100,
                   "sin_resolver": 5},
        "armas": None,
        "roster": {"resumen": {"vistos": 51, "total_db": 51, "huerfanos": 0}},
    })
    texto = "\n".join(log)
    assert "405/411" in texto and "51/51" in texto
    assert sb.btn_cierre.isEnabled()


def test_sin_nada_abierto_no_hay_dialogo(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, True)
    sb.btn_cierre.click()
    c.censo_cierre_resultado.emit({"accion": "nada"})
    assert preguntas == []
    assert any("no hay ninguna pasada abierta" in l for l in log)
    assert sb.btn_cierre.isEnabled()


def test_pausar_llega_al_controller_y_el_texto_sigue_al_estado(qapp):
    c, sb, log, preguntas, _f = _armar(qapp, True)
    sb.btn_pausa.click()
    assert c.pausas == 1
    c.pause_changed.emit(True)
    assert sb.btn_pausa.text() == "Reanudar"


def test_la_respuesta_desde_OTRO_hilo_se_atiende_en_el_de_la_UI(qapp):
    """La señal la emite el hilo del monitor. Un diálogo sólo puede abrirse en el hilo de la UI."""
    hilos: list = []
    c, sb, log, _p, _f = _armar(qapp, True)

    def preguntar(texto):
        hilos.append(threading.current_thread())
        return False

    _f._preguntar = preguntar
    t = threading.Thread(target=lambda: c.censo_cierre_resultado.emit(
        {"accion": "confirmar", "instantanea": _INST}))
    t.start()
    t.join()
    limite = time.monotonic() + 5.0
    while not hilos and time.monotonic() < limite:
        qapp.processEvents()
        time.sleep(0.01)
    assert hilos == [threading.main_thread()]


# --- el texto del diálogo ---------------------------------------------------------------------

def test_el_dialogo_dice_la_cobertura_y_a_quienes_declara_huerfanos():
    from app.ui.shell.cierre_censo import texto_confirmacion
    texto = texto_confirmacion(_INST)
    assert "300/411" in texto and "faltan 111" in texto
    assert "HUÉRFANOS 10" in texto
    assert "Aria" in texto and "(+2)" in texto, "más de 8 nombres se resumen"
    assert "W-Engines" not in texto, "lo que no está abierto no se menciona"


def test_un_roster_completo_dice_sin_huerfanos():
    from app.ui.shell.cierre_censo import texto_confirmacion
    texto = texto_confirmacion({"discos": None, "armas": None,
                                "roster": {"vistos": 51, "total": 51, "pendientes": []}})
    assert "51/51" in texto and "sin huérfanos" in texto


# --- el cableado de la ventana ------------------------------------------------------------------

def test_la_ventana_principal_arma_el_flujo_con_su_dialogo():
    """Contra A2: el flujo probado arriba no sirve si la ventana no lo construye."""
    from app.main import MainWindow
    fuente = inspect.getsource(MainWindow)
    assert "FlujoCierreCenso(c, self.sidebar, vista.append_log," in fuente
    assert "self._preguntar_cierre_censo" in fuente

"""`ServicioSugerencias`: el cálculo de las sugerencias fuera del hilo de la UI (SPEC 2026-09-27).

- el resultado llega por señal, en el hilo de la UI;
- un resultado VIEJO que llega tarde no pisa a uno más nuevo;
- un fallo del cálculo no tira la app: emite `fallo`;
- sin DB no hace nada.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication                   # noqa: E402

from app.ui.discos.servicio_sugerencias import ServicioSugerencias  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


def _esperar(qapp, cond, tope=5.0):
    fin = time.monotonic() + tope
    while not cond() and time.monotonic() < fin:
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


def test_el_resultado_llega_en_el_hilo_de_la_ui(qapp):
    hilos = []
    svc = ServicioSugerencias("x.db", calcular=lambda _p: (hilos.append(threading.current_thread()), {1: "ok"})[1])
    recibidos = []
    svc.listas.connect(lambda r: recibidos.append((r, threading.current_thread())))
    svc.pedir()
    assert _esperar(qapp, lambda: recibidos)
    (res, hilo_ui), = recibidos
    assert res == {1: "ok"} and svc.ultimo == {1: "ok"} and not svc.calculando
    assert hilos[0] is not threading.main_thread() and hilo_ui is threading.main_thread()


def test_un_resultado_viejo_no_pisa_al_nuevo(qapp):
    """El primer pedido tarda más que el segundo: llega último y se descarta."""
    liberar = threading.Event()

    def calcular(_p):
        n = calcular.n = getattr(calcular, "n", 0) + 1
        if n == 1:
            liberar.wait(5)
        return {"pedido": n}

    svc = ServicioSugerencias("x.db", calcular=calcular)
    recibidos = []
    svc.listas.connect(recibidos.append)
    svc.pedir()
    time.sleep(0.05)
    svc.pedir()
    assert _esperar(qapp, lambda: recibidos)
    liberar.set()
    time.sleep(0.1)
    _esperar(qapp, lambda: False, tope=0.3)
    assert recibidos == [{"pedido": 2}] and svc.ultimo == {"pedido": 2}


def test_un_fallo_no_tira_la_app(qapp):
    def roto(_p):
        raise RuntimeError("DB bloqueada")
    svc = ServicioSugerencias("x.db", calcular=roto)
    fallos = []
    svc.fallo.connect(fallos.append)
    svc.pedir()
    assert _esperar(qapp, lambda: fallos)
    assert "DB bloqueada" in fallos[0] and svc.ultimo is None and not svc.calculando


def test_sin_db_no_hace_nada(qapp):
    llamadas = []
    svc = ServicioSugerencias(None, calcular=lambda p: llamadas.append(p) or {})
    svc.pedir()
    assert svc.calcular_ya() is None and llamadas == []


def test_calcular_ya_sincronico(qapp):
    svc = ServicioSugerencias("x.db", calcular=lambda _p: {7: "x"})
    assert svc.calcular_ya() == {7: "x"}

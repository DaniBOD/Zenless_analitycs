"""Salida limpia — toda forma de cerrar la app detiene el monitor antes de que el proceso termine.

El bug que motiva esto no hacía ruido: las tres salidas (la X, "Salir" en la bandeja y el
auto-restart del watchdog RNF-06) llaman a `QApplication.quit()`, y nada estaba conectado a
`aboutToQuit`. El proceso terminaba sin `Monitor.stop()`, que es quien vuelca el buffer de métricas
(se escribe de a 100). Resultado: **cada pasada de QA perdía su última tanda de muestras**. En la
pasada del 2026-09-16 quedaron 500 exactas y faltaba el último de los 10 discos — y en una pasada
corta esa cola puede ser buena parte de lo medido.
"""
from __future__ import annotations

import inspect
import sys

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def test_salir_detiene_el_monitor_una_vez(qapp):
    from app.main import _conectar_salida_limpia

    llamadas: list[int] = []
    detener = lambda: llamadas.append(1)                           # noqa: E731
    _conectar_salida_limpia(qapp, detener)
    try:
        qapp.aboutToQuit.emit()                  # lo que dispara QApplication.quit()
        assert llamadas == [1], "la salida tiene que pasar por stop() exactamente una vez"
    finally:
        qapp.aboutToQuit.disconnect(detener)     # la app de test es compartida entre módulos


def test_sin_aplicacion_no_revienta():
    """Arrancar sin QApplication (algunos scripts importan la ventana) no puede tirar la app."""
    from app.main import _conectar_salida_limpia
    _conectar_salida_limpia(None, lambda: None)


def test_la_ventana_principal_realmente_lo_conecta():
    """**Contra A2.** El test de arriba llama al helper a mano, así que pasaría aunque nadie lo
    usara. La ventana no se construye en los tests (abre la DB, la vista en vivo y el tray), así
    que se verifica que la ventana cablee el `stop` del controller — que es el caso que se
    rompió: un helper correcto que nadie invocaba no habría arreglado nada."""
    from app.main import MainWindow
    # La clase entera y no un método: el controller se crea en `_setup_ui`, no en `__init__`, y el
    # primer intento de este test apuntó al método equivocado. Lo que importa es que la ventana lo
    # cablee, no en cuál de sus métodos.
    fuente = inspect.getsource(MainWindow)
    assert "_conectar_salida_limpia(QApplication.instance(), self._controller.stop)" in fuente

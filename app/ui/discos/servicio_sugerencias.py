"""Las sugerencias del motor para la pantalla Discos, calculadas en un hilo aparte.

`generar` sobre los 380 discos tarda ~0,75 s (medido el 2026-09-27): más que los 500 ms de una
respuesta de la interfaz (RNF-06). La vista pide, sigue pintando el inventario, y completa la
columna cuando llega el resultado.

Cada pedido lleva un número. Si mientras calcula llega otro pedido (volviste a la pestaña, cambió
el inventario), el resultado viejo se descarta al llegar: nunca pisa a uno más nuevo.

El cálculo abre su PROPIA conexión de sólo lectura (`generar` usa `mode=ro`): la conexión de la UI
no se comparte entre hilos.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


def _calcular_real(db_path: Path) -> dict:
    from app.core.sugerencias import generar, por_disco
    return por_disco(generar(db_path))


class ServicioSugerencias(QObject):
    #: {disc_id: SugerenciaDisco} — el último resultado vigente. `object`, NO `dict`: una señal
    #: `dict` pasa por un QVariantMap, que sólo acepta claves de texto, y los ids int se pierden en
    #: silencio (llegaba `{}`; hallado por el test del hilo, 2026-09-27).
    listas = Signal(object)
    #: El cálculo falló: la vista sigue sin sugerencias, y el log tiene el traceback.
    fallo = Signal(str)
    #: interno: del hilo de trabajo al hilo de la UI (conexión encolada entre hilos).
    _llego = Signal(int, object, str)

    def __init__(self, db_path: Path | str | None, calcular: Callable[[Path], dict] | None = None,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._db_path = Path(db_path) if db_path else None
        self._calcular = calcular or _calcular_real
        self._pedido = 0
        self.ultimo: dict | None = None
        self.calculando = False
        self._llego.connect(self._recibir)

    def pedir(self) -> None:
        """Lanza un cálculo en segundo plano. Sin DB no hace nada."""
        if self._db_path is None:
            return
        self._pedido += 1
        self.calculando = True
        threading.Thread(target=self._trabajar, args=(self._pedido,), daemon=True,
                         name=f"sugerencias-{self._pedido}").start()

    def calcular_ya(self) -> dict | None:
        """Lo mismo, en el hilo actual (para tests y herramientas de línea de comandos)."""
        if self._db_path is None:
            return None
        self._pedido += 1
        self._trabajar(self._pedido)
        return self.ultimo

    def _trabajar(self, numero: int) -> None:
        try:
            resultado = self._calcular(self._db_path)
        except Exception as exc:                    # el hilo no puede tirar la app
            log.exception("[discos] no se pudieron calcular las sugerencias")
            self._llego.emit(numero, None, f"{type(exc).__name__}: {exc}")
            return
        self._llego.emit(numero, resultado, "")

    def _recibir(self, numero: int, resultado, error: str) -> None:
        if numero != self._pedido:
            log.debug("[discos] sugerencias del pedido %d descartadas (vigente: %d)", numero, self._pedido)
            return
        self.calculando = False
        if error:
            self.fallo.emit(error)
            return
        self.ultimo = resultado
        self.listas.emit(resultado)

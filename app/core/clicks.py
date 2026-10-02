"""Los clicks del usuario sobre la ventana del juego — SÓLO LECTURA (RNF-03, ampliado 2026-10-02).

Hito "El ritmo de Daniel" (DIAG 2026-10-02): todo lo que la app sabe sale de mirar la pantalla por
polling, cada ~0,4-0,9 s. A un click por segundo, lo que dura menos que un par de ciclos no existe
(22 discos del desmontaje sin leer, una mejora de 2 s, un "Obtenido" que nunca se vio). El click
dice CUÁNDO mirar y QUÉ se tocó, por una vía independiente de la imagen.

Qué se guarda y qué no:
  - sólo el click con el botón APRETADO (no el soltar, ni el movimiento, ni la rueda);
  - sólo si la ventana de ZZZ está en primer plano (`is_zzz_focused`): un click en otra ventana no
    es del juego y no se registra;
  - la posición RELATIVA a la ventana (0-1), que es lo que comparan las regiones de cada pantalla.

Nunca se envía input: `pynput.mouse.Listener` es un hook pasivo de Windows (lectura), la misma
categoría que el `pynput.keyboard.Listener` que RNF-03 permitía desde el día 1. Decisión de Daniel
del 2026-10-02.

El listener real se inyecta (`listener_factory`) para que los tests corran sin hook del sistema.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

# Clicks recordados. A un click por segundo son ~8 minutos: de sobra para cualquier ventana que
# alguien consulte (la tanda de desmontaje más larga del 2026-10-02 duró 2 minutos).
_MAXLEN = 512


@dataclass(frozen=True)
class Click:
    t: float          # time.monotonic() del click (el mismo reloj que el loop del monitor)
    x: float          # 0-1, relativo al ancho de la ventana del juego
    y: float          # 0-1, relativo al alto
    boton: str        # "left" | "right" | "middle" | lo que diga pynput


class ClickListener:
    """Registra los clicks sobre la ventana del juego.

    `ventana_fn` devuelve la ventana vigente (`WindowBounds` o None): se consulta en cada click
    porque el juego puede moverse o redimensionarse. `foco_fn` dice si el juego está en primer
    plano; por defecto, `capturer.is_zzz_focused` sobre la ventana de `ventana_fn`."""

    def __init__(self, ventana_fn: Callable[[], object | None],
                 foco_fn: Callable[[object], bool] | None = None,
                 listener_factory: Callable | None = None,
                 reloj: Callable[[], float] = time.monotonic,
                 maxlen: int = _MAXLEN) -> None:
        self._ventana_fn = ventana_fn
        self._foco_fn = foco_fn or _foco_por_defecto
        self._listener_factory = listener_factory or _listener_pynput
        self._reloj = reloj
        self._clicks: deque[Click] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._listener = None
        # Se SETEA en cada click registrado. Quien quiera despertar con un click lo espera y lo
        # limpia él (`evento.wait(timeout)` + `evento.clear()`).
        self.evento = threading.Event()

    # --- ciclo de vida --------------------------------------------------------------------
    def start(self) -> bool:
        """Arranca el hook. Devuelve False (y lo loguea) si no se pudo: la app sigue sin clicks,
        exactamente como antes del 2026-10-02."""
        if self._listener is not None:
            return True
        try:
            self._listener = self._listener_factory(self._on_click)
            self._listener.start()
        except Exception:
            log.exception("[clicks] no se pudo iniciar el listener del mouse — sigo sin clicks")
            self._listener = None
            return False
        log.info("[clicks] escuchando clicks sobre el juego (sólo lectura)")
        return True

    def stop(self) -> None:
        lst, self._listener = self._listener, None
        if lst is not None:
            try:
                lst.stop()
            except Exception:
                log.debug("[clicks] stop falló", exc_info=True)

    # --- lo que llama el hook ---------------------------------------------------------------
    def _on_click(self, x, y, button, pressed) -> None:
        """Callback de pynput (corre en SU hilo). Nunca levanta: una excepción acá mata el hook."""
        try:
            if not pressed:
                return
            ventana = self._ventana_fn()
            if ventana is None or not self._foco_fn(ventana):
                return
            w, h = getattr(ventana, "width", 0), getattr(ventana, "height", 0)
            if w <= 0 or h <= 0:
                return
            rx = (x - ventana.left) / w
            ry = (y - ventana.top) / h
            if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0):
                return                       # click fuera de la ventana del juego
            nombre = getattr(button, "name", None) or str(button)
            click = Click(t=self._reloj(), x=round(rx, 4), y=round(ry, 4), boton=nombre)
            with self._lock:
                self._clicks.append(click)
            self.evento.set()
        except Exception:
            log.debug("[clicks] callback falló", exc_info=True)

    # --- consultas ------------------------------------------------------------------------
    def desde(self, t: float) -> list[Click]:
        """Los clicks con `t` estrictamente posterior, en orden."""
        with self._lock:
            return [c for c in self._clicks if c.t > t]

    def ultimo(self) -> Click | None:
        with self._lock:
            return self._clicks[-1] if self._clicks else None


def _foco_por_defecto(ventana) -> bool:
    from app.core.capturer import get_foreground_window, is_zzz_focused
    return is_zzz_focused(get_foreground_window(), getattr(ventana, "hwnd", 0))


def _listener_pynput(on_click):
    from pynput import mouse
    return mouse.Listener(on_click=on_click)

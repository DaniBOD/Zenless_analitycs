"""Muestreador del desmontaje (S11): mirar las tildes a ~10 fps mientras el loop hace OCR.

Hito "El ritmo de Daniel" (fase 5 acotada a S11, decisión de Daniel 2026-10-03). Medido contra la
grabación 20261003_111858: Daniel marca un disco por segundo y el loop lee un frame cada ~0,3-0,9 s;
peor, mientras hace el OCR del panel (~500 ms) no mira la pantalla. Dos clicks en la misma ventana
= delta de dos tildes = la bitácora no puede atribuir ninguno ("sin leer"): 8 de 21 con datos.

Este hilo hace sólo lo barato: captura, confirma que sigue en S11 (`sigue_en`, ~1 ms) y cuenta las
tildes (`tilde_cells`, < 3 ms, sin OCR). Cuando el conjunto de tildes CAMBIA guarda una `Muestra`
con los recortes que hacen falta para leer después el contador (header) y el disco (panel) — no el
frame entero: ~2,6 MB por muestra, con tope. El monitor las drena en orden en el despacho de S11 y
las pasa por la misma `TeardownBatch.observe` de siempre, así que la regla de atribución (un delta
de una celda confirmado por el contador) no cambia: sólo recibe un frame por cada cambio.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

# Recortes guardados por muestra (x, y, w, h normalizados). El header contiene el contador N/300
# (`parser_desmontaje._HEADER_ROI` = 0.09, 0.020, 0.30, 0.055, con margen). El panel DETAIL es
# `parser_disc_s3._S11_PANEL_ROI` (0.660, 0.170, 0.310, 0.475) con margen generoso, porque el parser
# de S3 hace rescates con recortes propios alrededor del panel.
ROI_HEADER = (0.07, 0.0, 0.34, 0.09)
ROI_PANEL = (0.60, 0.10, 0.40, 0.65)
# Período del muestreo: a un click por segundo, 10 muestras por segundo dejan cada click solo.
PERIODO_S = 0.1
# Tope de muestras pendientes: 32 × ~2,6 MB ≈ 85 MB en el peor caso (RNF-06). Si se llena se
# descartan las más viejas y se cuenta: el contador del header igual manda el conteo.
MAX_PENDIENTES = 32


def _recortar(frame: np.ndarray, roi) -> tuple[np.ndarray, tuple[int, int]]:
    H, W = frame.shape[:2]
    x, y, w, h = roi
    x0, y0 = int(x * W), int(y * H)
    x1, y1 = min(W, int((x + w) * W)), min(H, int((y + h) * H))
    return frame[y0:y1, x0:x1].copy(), (x0, y0)


@dataclass
class Muestra:
    t: float
    tildes: frozenset
    scroll: float | None
    forma: tuple[int, int, int]             # forma del frame original
    header: np.ndarray
    header_xy: tuple[int, int]
    panel: np.ndarray
    panel_xy: tuple[int, int]
    # La primera muestra de cada visita: no es un cambio sino el punto de partida (tildes y
    # contador) para que la tanda pueda confirmar el primer click. Sin ella el primer cambio
    # llegaba sin contador previo y no se atribuía (reproducción 2026-10-03: 16 de 17, y 0 de 4
    # cuando el muestreador arrancó con la selección empezada).
    referencia: bool = False

    def reconstruir(self) -> np.ndarray:
        """Un frame del tamaño original, negro salvo los dos recortes: lo que necesitan
        `parse_header_counter` y `parse_disc_s11`, que trabajan con coordenadas relativas."""
        frame = np.zeros(self.forma, np.uint8)
        for img, (x0, y0) in ((self.header, self.header_xy), (self.panel, self.panel_xy)):
            frame[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img
        return frame


class MuestreadorS11:
    """Hilo que guarda una muestra por cada cambio de tildes mientras está activo."""

    def __init__(self, capturar: Callable[[], np.ndarray | None],
                 es_s11: Callable[[np.ndarray], bool],
                 tildes_fn: Callable[[np.ndarray], frozenset],
                 scroll_fn: Callable[[np.ndarray], float | None],
                 reloj: Callable[[], float] = time.monotonic,
                 periodo: float = PERIODO_S, max_pendientes: int = MAX_PENDIENTES,
                 con_hilo: bool = True) -> None:
        self._capturar = capturar
        self._es_s11 = es_s11
        self._tildes_fn = tildes_fn
        self._scroll_fn = scroll_fn
        self._reloj = reloj
        self._periodo = periodo
        self._pendientes: deque[Muestra] = deque()
        self._max = max_pendientes
        self._lock = threading.Lock()
        self._activo = threading.Event()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._previas: frozenset | None = None
        self.descartadas = 0
        self._con_hilo = con_hilo                # False en los tests: `paso()` a mano

    # --- ciclo de vida ----------------------------------------------------------------------
    def activar(self) -> None:
        if not self._activo.is_set():
            self._previas = None            # la primera vuelta guarda la muestra de referencia
            self._activo.set()
        if self._hilo is None and self._con_hilo:
            self._hilo = threading.Thread(target=self._correr, name="muestreador_s11", daemon=True)
            self._hilo.start()

    def desactivar(self) -> None:
        self._activo.clear()

    def parar(self) -> None:
        self._activo.clear()
        self._parar.set()

    @property
    def activo(self) -> bool:
        return self._activo.is_set()

    # --- una vuelta (pública para los tests) ---------------------------------------------------
    def paso(self) -> Muestra | None:
        frame = self._capturar()
        if frame is None or not self._es_s11(frame):
            return None
        tildes = self._tildes_fn(frame)
        referencia = self._previas is None
        if not referencia and tildes == self._previas:
            return None
        self._previas = tildes
        header, hxy = _recortar(frame, ROI_HEADER)
        panel, pxy = _recortar(frame, ROI_PANEL)
        m = Muestra(t=self._reloj(), tildes=tildes, scroll=self._scroll_fn(frame),
                    forma=frame.shape, header=header, header_xy=hxy, panel=panel, panel_xy=pxy,
                    referencia=referencia)
        with self._lock:
            if len(self._pendientes) >= self._max:
                self._pendientes.popleft()
                self.descartadas += 1
            self._pendientes.append(m)
        return m

    def pendientes(self) -> int:
        with self._lock:
            return len(self._pendientes)

    def drenar(self) -> list[Muestra]:
        with self._lock:
            out = list(self._pendientes)
            self._pendientes.clear()
        return out

    def _correr(self) -> None:
        while not self._parar.is_set():
            if not self._activo.wait(0.5):
                continue
            t0 = time.perf_counter()
            try:
                self.paso()
            except Exception:
                log.debug("muestreador S11: vuelta fallida", exc_info=True)
            espera = self._periodo - (time.perf_counter() - t0)
            if espera > 0:
                time.sleep(espera)


# --- El OCR de las muestras, en su propio hilo ("procesar después") -------------------------------
# Medido en la reproducción del 2026-10-03: drenar las muestras en el loop (≈0,5 s de OCR del panel
# cada una) lo dejaba 8-10 s sin mirar la pantalla al llegar el "Obtenido" — y la pantalla seguía:
# una visita entera a S11 de 3,4 s pasó sin verse. El OCR es serializado por `OcrProxy` (RLock), así
# que este hilo lo usa cuando el loop no lo está usando, y el loop sólo aplica lecturas ya hechas.

@dataclass
class Leida:
    t: float
    tildes: frozenset
    scroll: float | None
    contador: int | None
    disco: object | None          # DiscParsed del panel, sólo si la muestra sumó tildes


class ProcesadorS11:
    """Consume las muestras del `MuestreadorS11` en orden y deja `Leida`s listas para el loop."""

    def __init__(self, muestreador: MuestreadorS11,
                 contador_fn: Callable[[np.ndarray], int | None],
                 disco_fn: Callable[[np.ndarray], object | None],
                 con_hilo: bool = True) -> None:
        self._m = muestreador
        self._contador_fn = contador_fn
        self._disco_fn = disco_fn
        self._leidas: deque[Leida] = deque()
        self._lock = threading.Lock()
        self._procesando = False
        self._previas: frozenset = frozenset()
        self._parar = threading.Event()
        self._hilo = None
        if con_hilo:
            self._hilo = threading.Thread(target=self._correr, name="procesador_s11", daemon=True)
            self._hilo.start()

    def procesar_pendientes(self) -> int:
        """Lee todas las muestras que haya. Pública para los tests (sin hilo)."""
        n = 0
        for mu in self._m.drenar():
            with self._lock:
                self._procesando = True
            try:
                frame = mu.reconstruir()
                contador = self._contador_fn(frame)
                suma = not mu.referencia and len(mu.tildes) > len(self._previas)
                disco = self._disco_fn(frame) if suma else None
                self._previas = mu.tildes
                with self._lock:
                    self._leidas.append(Leida(mu.t, mu.tildes, mu.scroll, contador, disco))
                n += 1
            except Exception:
                log.debug("procesador S11: muestra fallida", exc_info=True)
            finally:
                with self._lock:
                    self._procesando = False
        return n

    def leidas(self) -> list[Leida]:
        with self._lock:
            out = list(self._leidas)
            self._leidas.clear()
        return out

    @property
    def ocupado(self) -> bool:
        """Hay muestras sin leer (en el muestreador o en proceso)."""
        with self._lock:
            procesando = self._procesando
        return procesando or self._m.pendientes() > 0

    def reiniciar(self) -> None:
        """Visita nueva a S11: las tildes de referencia vuelven a cero."""
        self._previas = frozenset()

    def parar(self) -> None:
        self._parar.set()

    def _correr(self) -> None:
        while not self._parar.is_set():
            if self.procesar_pendientes() == 0:
                time.sleep(0.05)

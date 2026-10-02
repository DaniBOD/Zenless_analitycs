"""Grabador de sesiones (hito "El ritmo de Daniel"): qué frames guarda y que se lean de vuelta.

Sin pantalla ni mouse: captura, reloj, clicks y codificador se inyectan.
"""
from __future__ import annotations

import numpy as np

from app.core.clicks import Click
from app.core.grabacion import Grabador, frame_vigente, leer_grabacion


class _Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class _Clicks:
    def __init__(self):
        self.lista: list[Click] = []

    def desde(self, t):
        return [c for c in self.lista if c.t > t]


def _frame(v: int) -> np.ndarray:
    return np.full((54, 96, 3), v, np.uint8)


def _grabador(tmp_path, frames, clicks=None):
    reloj = _Reloj()
    it = iter(frames)
    escritos = []

    def codificar(ruta, frame):
        escritos.append(int(frame[0, 0, 0]))
        np.save(str(ruta) + ".npy", frame)      # sin PNG: rápido y sin cv2.imencode
        ruta.write_bytes(b"x")

    g = Grabador(tmp_path / "rec", capturar=lambda: next(it), clicks=clicks, reloj=reloj,
                 escritores=1, codificar=codificar)
    g.iniciar(ventana=(96, 54), fps=12)
    return g, reloj, escritos


def test_guarda_el_primero_y_los_que_cambian(tmp_path):
    g, reloj, _ = _grabador(tmp_path, [_frame(10), _frame(10), _frame(80)])
    motivos = []
    for _ in range(3):
        motivos.append(g.paso())
        reloj.t += 0.08
    assert motivos == ["cambio", None, "cambio"]


def test_un_frame_igual_se_guarda_igual_por_latido(tmp_path):
    """Para saber cuánto duró una pantalla quieta (un modal, por ejemplo)."""
    g, reloj, _ = _grabador(tmp_path, [_frame(10), _frame(10)])
    g.paso()
    reloj.t += 1.1
    assert g.paso() == "latido"


def test_un_click_fuerza_su_frame_150_ms_despues(tmp_path):
    """Una tilde de S11 casi no mueve la huella: el click es el que avisa."""
    clicks = _Clicks()
    g, reloj, _ = _grabador(tmp_path, [_frame(10)] * 4, clicks=clicks)
    g.paso()
    clicks.lista.append(Click(t=reloj.t + 0.01, x=0.5, y=0.5, boton="left"))
    reloj.t += 0.05
    assert g.paso() is None                    # todavía no pasaron los 150 ms
    reloj.t += 0.15
    assert g.paso() == "click"
    reloj.t += 0.05
    assert g.paso() is None                    # ya cobrado


def test_sin_frame_no_se_guarda_nada(tmp_path):
    g, _r, _ = _grabador(tmp_path, [None])
    assert g.paso() is None


def test_lo_grabado_se_lee_de_vuelta_en_orden(tmp_path):
    clicks = _Clicks()
    g, reloj, escritos = _grabador(tmp_path, [_frame(10), _frame(90), _frame(20)], clicks=clicks)
    g.paso()
    reloj.t += 0.3
    clicks.lista.append(Click(t=reloj.t, x=0.25, y=0.75, boton="left"))
    g.paso()
    reloj.t += 0.3
    g.paso()
    assert g.cerrar() == 0
    rec = leer_grabacion(tmp_path / "rec")
    assert [f.n for f in rec.frames] == [1, 2, 3]
    assert [c["x"] for c in rec.clicks] == [0.25]
    assert rec.inicio["ventana"] == [96, 54]
    assert frame_vigente(rec, 100.31).n == 2
    assert frame_vigente(rec, 99.0) is None
    assert sorted(escritos) == [10, 20, 90]


def test_si_el_escritor_no_da_abasto_descarta_y_lo_dice(tmp_path):
    g, reloj, _ = _grabador(tmp_path, [_frame(v) for v in (10, 90, 10, 90)])
    g._cola.maxsize = 1                         # una cola llena a propósito
    import threading
    bloqueo = threading.Event()
    g.codificar = lambda ruta, frame: bloqueo.wait(5)
    for _ in range(4):
        g.paso()
        reloj.t += 0.1
    bloqueo.set()
    assert g.cerrar() >= 1
    assert leer_grabacion(tmp_path / "rec").descartados >= 1

"""Arnés para correr el `Monitor._run` VERDADERO sin pantalla, pasada por pasada.

El loop no captura nada acá: cada pasada recibe un frame inyectado cuya firma de S9 es la que dice
el test, el detector devuelve siempre el estado pedido y el despacho se anota en vez de leer. Lo
que queda REAL es exactamente lo que se quiere verificar: el orden de las decisiones del loop
(confirmar antes de clasificar, suprimir, despachar, saltear `classify`) y la votación del buffer
temporal.

Nace del despacho rápido de S9 (2026-09-16). Hasta entonces el cableado del loop se verificaba
leyendo su código fuente, que prueba que una línea EXISTE, no que el loop la ejecute en el orden
que importa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.detector import ScreenState


def firma(valor: float):
    """Firma de S9 sintética. Dos valores muy distintos = dos discos; el mismo valor = panel quieto."""
    return (np.full((24, 48), valor, np.float32), np.full((48, 48), valor, np.float32), None)


@dataclass
class Registro:
    despachados: list[int] = field(default_factory=list)   # nº de pasada (desde 1) de cada despacho
    clasificados: list[int] = field(default_factory=list)  # nº de pasada de cada classify


def correr_loop(monkeypatch, mon, firmas: list[float], estado: str = "S9") -> Registro:
    """Corre `mon._run()` con una pasada por valor de `firmas` y devuelve qué pasó en cada una.

    La cadencia se pone en 0 a propósito: así cualquier despacho que NO ocurra es una decisión del
    loop (supresión, confirmación), no una espera de reloj que el test tendría que adivinar.
    """
    reg = Registro()
    pasadas = iter(enumerate(firmas, start=1))
    actual = {"n": 0, "valor": None}

    def get_frame():
        try:
            n, valor = next(pasadas)
        except StopIteration:
            mon._stop.set()
            return None
        actual["n"], actual["valor"] = n, valor
        return np.zeros((4, 4, 3), np.uint8)

    class _Detector:
        def classify(self, frame):
            reg.clasificados.append(actual["n"])
            return ScreenState(estado, 0.95, "arnes")

    monkeypatch.setattr(mon, "_get_frame", get_frame)
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda frame: firma(actual["valor"]))
    monkeypatch.setattr(mon, "_detector", _Detector())
    monkeypatch.setattr(mon, "_safe_dispatch", lambda frame, st: reg.despachados.append(actual["n"]))
    monkeypatch.setattr(mon, "_wait_fast", lambda: None)
    monkeypatch.setattr("app.core.monitor.polling_cadence_ms", lambda st: 0)
    mon._paused.set()
    mon._stop.clear()
    mon._run()
    return reg

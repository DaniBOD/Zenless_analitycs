"""La grilla que entra entera, sin scroll — la comparten Roster y Armas.

Regla heredable del diseño (Parte B del diseño v1): **si el catálogo no cabe, se comprime la celda;
no se agrega scroll.** Si ni al piso cabe, se dice (`cabe=False`) en vez de dibujar celdas
ilegibles o esconder ítems.

Vivía dentro de `roster/datos.py`. Al llegar Armas, con celdas de otro tamaño, la alternativa era
copiarla: una segunda definición del mismo cálculo (B1). Acá los tamaños son parámetros.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Grilla:
    columnas: int
    celda_w: int
    celda_h: int
    gap: int
    escala: float
    cabe: bool


def calcular(n: int, ancho: int, alto: int, *, base_w: int, base_h: int, gap: int = 6,
             escala_max: float = 2.2, escala_min: float = 0.6) -> Grilla:
    """La grilla de mayor escala que entra ENTERA en `ancho × alto`."""
    n = max(n, 1)
    mejor_c, mejor_s = 1, 0.0
    for c in range(1, n + 1):
        filas = math.ceil(n / c)
        w = (ancho - gap * (c - 1)) / c
        h = (alto - gap * (filas - 1)) / filas
        if w <= 0 or h <= 0:
            continue
        s = min(w / base_w, h / base_h, escala_max)
        # `>=`: entre empates (típico al tope de escala, con la ventana maximizada) gana la de MÁS
        # columnas. Con `>` ganaba la primera y la grilla dejaba media pantalla vacía.
        if s >= mejor_s - 1e-9:
            mejor_c, mejor_s = c, s
    cabe = mejor_s >= escala_min
    s = max(mejor_s, escala_min)
    return Grilla(columnas=mejor_c, celda_w=int(base_w * s), celda_h=int(base_h * s),
                  gap=gap, escala=round(s, 3), cabe=cabe)

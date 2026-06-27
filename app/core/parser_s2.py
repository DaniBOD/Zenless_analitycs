"""Lectura de la grilla de resultados de farmeo (S2, "Resultados del desafío").

S2 muestra una grilla PARCIAL de los discos dropeados (esquina superior derecha): colapsa con
un "▼" cuando hay muchos, y con el desmontaje automático varios se convierten en materiales
("Obtenido al desmontar"). Por eso el conteo total NO es confiable desde S2.

Alcance actual (dirección del usuario 2026-06-27): detectar solo los discos **tier S
(dorados)**, que siempre aparecen en la grilla. El valor es un GATE de display-only — "se
farmeó al menos un disco S" — que combinado con el contexto de flujo (`FarmSession`) sube la
confianza de que el S2 es un farmeo real. La captura completa (set/slot/main/substats + score)
llega al abrir cada disco en S3. Casos B/A (azul/púrpura) y conteo exacto: futuro.

Sin OCR (RNF-06): solo máscara de color sobre la región de la grilla.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Región de la grilla de tiles dentro del frame (normalizada). Las 2 primeras filas visibles,
# por debajo de la barra de EXP y por encima del bloque "Obtenido al desmontar".
_GRID_X = (0.785, 0.995)
_GRID_Y = (0.345, 0.600)

# Dorado (tier S) en HSV OpenCV (H 0-180): franja de rareza + arte dorado del ícono.
_GOLD_LO = (14, 120, 120)
_GOLD_HI = (36, 255, 255)

# Gate: fracción mínima de píxeles dorados saturados en la grilla para afirmar "hay disco S".
_GOLD_FRAC_MIN = 0.02


@dataclass
class S2Summary:
    has_s_discs: bool       # gate: hay ≥1 disco tier S (dorado) visible en la grilla
    gold_frac: float        # fracción de píxeles dorados saturados en la región de la grilla
    n_s_approx: int         # conteo best-effort de franjas/tiles doradas (aproximado)


def _grid_region(frame: np.ndarray) -> np.ndarray:
    H, W = frame.shape[:2]
    x0, x1 = int(_GRID_X[0] * W), int(_GRID_X[1] * W)
    y0, y1 = int(_GRID_Y[0] * H), int(_GRID_Y[1] * H)
    return frame[y0:y1, x0:x1]


def parse_s2_resultado(frame: np.ndarray) -> S2Summary:
    """Detecta discos tier S (dorados) en la grilla de resultados de farmeo. Display-only."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return S2Summary(has_s_discs=False, gold_frac=0.0, n_s_approx=0)

    grid = _grid_region(frame)
    if grid.size == 0:
        return S2Summary(has_s_discs=False, gold_frac=0.0, n_s_approx=0)

    hsv = cv2.cvtColor(grid, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, _GOLD_LO, _GOLD_HI)
    gold_frac = float(gold.mean()) / 255.0

    # Conteo best-effort: cerrar horizontalmente y contar franjas anchas (cada tile S ≈ 1).
    gh, gw = grid.shape[:2]
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
    closed = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    n_s = 0
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 0.18 * gw and (w * h) >= 0.004 * gh * gw:
            n_s += 1

    has = gold_frac >= _GOLD_FRAC_MIN
    return S2Summary(has_s_discs=has, gold_frac=gold_frac, n_s_approx=n_s if has else 0)

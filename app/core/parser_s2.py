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

# Rarezas de disco en HSV OpenCV (gold=S, purple=A, blue=B). La FRANJA de rareza al borde
# inferior de cada tile de disco es la firma robusta de "esto es un drop de disco". Se usa en
# `count_reward_rarity_strips` para verificar S2 (farmeo de discos vs otros resultados/menús).
_RARITY_BANDS = (
    ((14, 120, 120), (36, 255, 255)),    # dorado (S)
    ((125, 80, 80), (155, 255, 255)),    # púrpura (A)
    ((98, 90, 90), (120, 255, 255)),     # azul (B)
)
# ≥ este nº de franjas en la grilla ⇒ es un farmeo de discos. Calibrado (2026-07): farmeo real
# da 3 (todas las capturas); pantallas sin discos (otro contenido, eventos, banners, pase) ≤2.
_DISC_STRIP_MIN = 3


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


def count_reward_rarity_strips(frame: np.ndarray) -> int:
    """Cuenta franjas de rareza (bandas horizontales gold/purple/blue, borde inferior de cada
    tile de disco) en la grilla de recompensas de la pantalla de resultados. Es la firma robusta
    de "drop de discos": un farmeo real da ≥`_DISC_STRIP_MIN`; pantallas sin discos (otros
    resultados, eventos, banners) dan ≤2. Se usa en `detector._verify_s2`. Sin OCR (RNF-06)."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0
    grid = _grid_region(frame)
    if grid.size == 0:
        return 0
    gh, gw = grid.shape[:2]
    hsv = cv2.cvtColor(grid, cv2.COLOR_BGR2HSV)
    mask = np.zeros((gh, gw), np.uint8)
    for lo, hi in _RARITY_BANDS:
        mask |= cv2.inRange(hsv, lo, hi)
    # Las franjas son barras horizontales anchas; cerrar y contar contornos anchos/con área.
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    n = 0
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 0.18 * gw and (w * h) >= 0.004 * gh * gw:
            n += 1
    return n


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

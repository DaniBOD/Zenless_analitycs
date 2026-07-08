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
# NARROW: sub-región derecha, usada por `count_reward_rarity_strips` (verificación S2 anti-FP,
# calibrada). WIDE: las 4 columnas del grid, usada para CONTAR los discos S (que pueden caer en
# cualquier columna; la narrow perdía los tiles de la izquierda → falso "sin disco visible").
_GRID_X = (0.785, 0.995)
_GRID_Y = (0.345, 0.600)
_GRID_X_WIDE = (0.685, 0.997)
_GRID_Y_WIDE = (0.400, 0.620)

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


# --- Geometría de tiles (Fase B: captura slot + set por badge) ----------------------------
# Grilla de recompensas: 4 columnas × 2 filas visibles. Centros calibrados 2026-07 contra las
# franjas de rareza (borde inferior de cada tile) de los 7 fixtures S2 (todos dan 8 tiles).
_TILE_COLS_CX = (0.722, 0.787, 0.852, 0.917)   # centro x de cada columna
_TILE_ROWS_STRIP_CY = (0.494, 0.640)           # cy de la franja de rareza (fondo del tile) por fila
_TILE_W = 0.066        # ancho normalizado del tile
_TILE_ABOVE = 0.095    # alto del tile por encima del cy de la franja (arte + slot)
_TILE_BELOW = 0.012    # margen por debajo del cy de la franja
# Fracción mínima de píxeles de rareza en la banda de la franja para considerar el tile presente.
_TILE_STRIP_FRAC_MIN = 0.15


@dataclass
class TileBox:
    """Caja de un tile de la grilla S2, en píxeles del frame."""
    row: int
    col: int
    x0: int
    y0: int
    x1: int
    y1: int


def _tile_strip_frac(frame: np.ndarray, cx: float, scy: float) -> float:
    """Fracción de píxeles de rareza (gold/purple/blue) en la banda de la franja de un tile."""
    H, W = frame.shape[:2]
    x0, x1 = int((cx - _TILE_W / 2) * W), int((cx + _TILE_W / 2) * W)
    y0, y1 = int((scy - 0.02) * H), int((scy + 0.02) * H)
    sub = frame[y0:y1, x0:x1]
    if sub.size == 0:
        return 0.0
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = np.zeros(sub.shape[:2], np.uint8)
    for lo, hi in _RARITY_BANDS:
        mask |= cv2.inRange(hsv, lo, hi)
    return float(mask.mean()) / 255.0


def tile_boxes(frame: np.ndarray) -> list[TileBox]:
    """Localiza los tiles de disco de la grilla S2 (4×2). Devuelve solo los tiles presentes
    (con franja de rareza), en orden row-major. Sin OCR (RNF-06)."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    H, W = frame.shape[:2]
    out: list[TileBox] = []
    for r, scy in enumerate(_TILE_ROWS_STRIP_CY):
        for c, cx in enumerate(_TILE_COLS_CX):
            if _tile_strip_frac(frame, cx, scy) < _TILE_STRIP_FRAC_MIN:
                continue
            x0 = int((cx - _TILE_W / 2) * W)
            x1 = int((cx + _TILE_W / 2) * W)
            y0 = int((scy - _TILE_ABOVE) * H)
            y1 = int((scy + _TILE_BELOW) * H)
            out.append(TileBox(row=r, col=c, x0=x0, y0=y0, x1=x1, y1=y1))
    return out


def crop_tile_center(frame: np.ndarray, box: TileBox) -> np.ndarray:
    """Recorta el arte del disco (centro del tile) para el matcher de sets. Descarta la banda
    inferior (franja de rareza / badge RARITY) y parte del hexágono de slot arriba-izq."""
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    x0 = box.x0 + int(0.20 * bw)
    x1 = box.x0 + int(0.95 * bw)
    y0 = box.y0 + int(0.12 * bh)
    y1 = box.y0 + int(0.72 * bh)
    return frame[y0:y1, x0:x1]


def crop_tile_slot(frame: np.ndarray, box: TileBox) -> np.ndarray:
    """Recorta la esquina superior-izquierda del tile (hexágono con el dígito de slot 1-6)."""
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    x1 = box.x0 + int(0.46 * bw)
    y1 = box.y0 + int(0.42 * bh)
    return frame[box.y0:y1, box.x0:x1]


def read_tile_slot(frame: np.ndarray, box: TileBox, ocr) -> int | None:
    """OCR del dígito de slot (1-6) de un tile. Upscale ×3 (patrón `_rescue_slot_s3`) para el
    dígito chico. Devuelve el slot o None si no se reconoce. Se calibra en la QA en vivo."""
    if ocr is None:
        return None
    crop = crop_tile_slot(frame, box)
    if crop.size == 0:
        return None
    up = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    try:
        text, _ = ocr.text(up, psm=7, lang="spa")
    except Exception:
        return None
    for ch in (text or ""):
        if ch.isdigit():
            d = int(ch)
            if 1 <= d <= 6:
                return d
    return None


def _grid_region(frame: np.ndarray, wide: bool = False) -> np.ndarray:
    H, W = frame.shape[:2]
    gx, gy = (_GRID_X_WIDE, _GRID_Y_WIDE) if wide else (_GRID_X, _GRID_Y)
    x0, x1 = int(gx[0] * W), int(gx[1] * W)
    y0, y1 = int(gy[0] * H), int(gy[1] * H)
    return frame[y0:y1, x0:x1]


def count_gold_disc_strips(frame: np.ndarray) -> int:
    """Cuenta franjas doradas (tier S) en el grid COMPLETO de recompensas → nº de discos S
    dropeados. Cada tile de disco S tiene una banda dorada al borde inferior; se cuentan como
    barras horizontales anchas (~1 tile) en la región WIDE (4 columnas). Robusto a la columna
    donde caiga el disco. Sin OCR (RNF-06). Ver `parse_s2_resultado`."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0
    grid = _grid_region(frame, wide=True)
    if grid.size == 0:
        return 0
    gh, gw = grid.shape[:2]
    hsv = cv2.cvtColor(grid, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, _GOLD_LO, _GOLD_HI)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
    closed = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    n = 0
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        # franja de tile: barra horizontal ancha (≥~1/8 del ancho, más ancha que alta, con área).
        if w >= 0.12 * gw and w > h and (w * h) >= 0.003 * gh * gw:
            n += 1
    return n


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
    """Cuenta los discos tier S (dorados) dropeados en la grilla de resultados de farmeo, sobre
    el grid COMPLETO (los discos S pueden caer en cualquier columna). Display-only, sin OCR.
    `n_s_approx` = nº de franjas doradas (≈ discos S); `has_s_discs` = hay ≥1."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return S2Summary(has_s_discs=False, gold_frac=0.0, n_s_approx=0)

    grid = _grid_region(frame, wide=True)
    gold_frac = 0.0
    if grid.size > 0:
        hsv = cv2.cvtColor(grid, cv2.COLOR_BGR2HSV)
        gold_frac = float(cv2.inRange(hsv, _GOLD_LO, _GOLD_HI).mean()) / 255.0

    n_s = count_gold_disc_strips(frame)
    return S2Summary(has_s_discs=n_s >= 1, gold_frac=gold_frac, n_s_approx=n_s)

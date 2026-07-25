"""Lectura de la pantalla de Desmontaje de discos (S11).

S11 muestra una grilla de 9 columnas × 5 filas del inventario y un panel DETAIL a la derecha.
El usuario marca los discos a destruir clickeándolos: cada click **muestra el disco en el panel
DETAIL Y alterna su tilde**. Un segundo click sobre el mismo lo desmarca.

Este módulo aporta la señal BARATA del flujo (sin OCR, RNF-06): qué celdas están tildadas. Con
eso el monitor sabe *cuál* disco acaba de cambiar de estado y lo aparea con el que el panel
DETAIL está mostrando en ese mismo frame. El *conteo* autoritativo no sale de acá sino del
contador `N/300` del header, porque los tildes que quedan scrolleados fuera del viewport no se
ven (`Ejemplo_3`: 7 seleccionados, 1 visible).

**El problema difícil: el aro de foco imita al tilde.** El tile que se está mostrando en el
DETAIL lleva un aro de selección que pasa por la MISMA esquina donde vive el badge del tilde, y
tanto su color como el del badge varían entre frames (medido sobre los fixtures: badge H 24-33;
aro de `Ejemplo_6` H 28 — indistinguibles por color). Discriminar por "hay amarillo" da falsos
positivos garantizados: en `Ejemplo_6` el aro llena el 24 % de la esquina con el contador en 0.

La solución es geométrica, no cromática: se mide la fracción de amarillo en un **annulus**
centrado en el badge — el mismo idiom que `_detect_s17_slot_by_hexagon` usa para el aro dorado
del hexágono. El badge es un disco compacto con un check oscuro adentro, así que su anillo se
llena; el aro de foco es un trazo fino que pasa de largo por el borde del tile y apenas lo roza.

Calibrado 2026-07-24 sobre las 225 celdas (5 capturas × 45) de
`Screenshots_Triggers/Discos_Triggers/12_Desmontaje/`:

    tilde mínimo   0.551
    no-tilde máx.  0.140      ⇒ separación 3.9×, umbral 0.30 con ~1.8× de margen a cada lado
"""
from __future__ import annotations

import cv2
import numpy as np

# --- Geometría de la grilla (normalizada, verificada por overlay sobre los fixtures) --------
GRID_COLS = 9
GRID_ROWS = 5

# Centro de cada columna / fila de tiles.
_COLS_CX = (0.0775, 0.145, 0.2125, 0.28, 0.3465, 0.414, 0.481, 0.5485, 0.615)
_ROWS_CY = (0.173, 0.329, 0.484, 0.640, 0.795)

# --- Badge del tilde -----------------------------------------------------------------------
# Desplazamiento del centro del badge respecto del centro del tile (esquina superior-derecha).
_BADGE_DX = 0.027
_BADGE_DY = -0.034
# Radio del badge y annulus a muestrear, en fracciones del radio (mismo patrón que el aro del
# hexágono en `parser_disc_s17`): se evita el centro, donde el check OSCURO baja la fracción.
_BADGE_RAD = 0.007
_ANN_IN, _ANN_OUT = 0.45, 0.85

# Amarillo del badge en HSV OpenCV. Rango ancho a propósito: el tono va de dorado (H 24) a lima
# (H 33) según el frame, y esa variación NO es la señal — la señal es la geometría.
_YELLOW_LO = np.array([18, 150, 150], np.uint8)
_YELLOW_HI = np.array([38, 255, 255], np.uint8)

# Fracción mínima del annulus para afirmar que hay tilde. Ver la calibración del docstring.
_TILDE_FRAC_MIN = 0.30

# --- Gate de "el tile existe" --------------------------------------------------------------
# El amarillo del badge NO es exclusivo del desmontaje: el botón "Aceptar" del modal de
# re-login lleva un círculo lima idéntico y caía justo en la celda (3,5) — un falso positivo
# real, encontrado por el test de negativos. Así que un tilde solo se acepta sobre una celda
# que TIENE un tile de disco, y eso se comprueba por su franja de rareza (mismo criterio que
# `parser_s2.tile_boxes`). Medido: las 45 celdas de S11 dan ≥0.657; los negativos, 0.000.
_STRIP_DY = 0.043
_STRIP_FRAC_MIN = 0.30
_RARITY_BANDS = (
    ((14, 120, 120), (36, 255, 255)),    # dorado (S)
    ((125, 80, 80), (155, 255, 255)),    # púrpura (A)
    ((98, 90, 90), (120, 255, 255)),     # azul (B)
)

# Cache de la máscara del annulus: la geometría solo depende del tamaño de caja, así que se
# calcula una vez por resolución en vez de 45 veces por frame (RNF-06 — corre a 10 fps).
_ANN_CACHE: dict[int, np.ndarray] = {}


def _annulus_mask(box: int, rad: float) -> np.ndarray:
    cached = _ANN_CACHE.get(box)
    if cached is None:
        yy, xx = np.ogrid[:2 * box, :2 * box]
        dist = np.sqrt((xx - box) ** 2 + (yy - box) ** 2)
        cached = (dist >= _ANN_IN * rad) & (dist <= _ANN_OUT * rad)
        _ANN_CACHE[box] = cached
    return cached


def _badge_annulus_frac(frame: np.ndarray, row: int, col: int) -> float:
    """Fracción de amarillo en el annulus del badge de una celda. 0.0 si el recorte no entra."""
    H, W = frame.shape[:2]
    cx = (_COLS_CX[col] + _BADGE_DX) * W
    cy = (_ROWS_CY[row] + _BADGE_DY) * H
    rad = _BADGE_RAD * W
    box = int(rad * 1.3)
    if box < 2:
        return 0.0
    x0, y0 = int(cx - box), int(cy - box)
    if x0 < 0 or y0 < 0 or x0 + 2 * box > W or y0 + 2 * box > H:
        return 0.0
    sub = frame[y0:y0 + 2 * box, x0:x0 + 2 * box]
    if sub.size == 0:
        return 0.0
    mask = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), _YELLOW_LO, _YELLOW_HI) > 0
    ann = _annulus_mask(box, rad)
    if mask.shape != ann.shape or not ann.any():
        return 0.0
    return float(mask[ann].mean())


def _tile_strip_frac(frame: np.ndarray, row: int, col: int) -> float:
    """Fracción de píxeles de rareza en la franja al pie del tile ⇒ "acá hay un disco"."""
    H, W = frame.shape[:2]
    x0, x1 = int((_COLS_CX[col] - 0.022) * W), int((_COLS_CX[col] + 0.022) * W)
    cy = (_ROWS_CY[row] + _STRIP_DY) * H
    half = 0.005 * W
    y0, y1 = int(cy - half), int(cy + half)
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
        return 0.0
    sub = frame[y0:y1, x0:x1]
    if sub.size == 0:
        return 0.0
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = np.zeros(sub.shape[:2], np.uint8)
    for lo, hi in _RARITY_BANDS:
        mask |= cv2.inRange(hsv, lo, hi)
    return float(mask.mean()) / 255.0


# --- Scrollbar -----------------------------------------------------------------------------
# Barra vertical al borde izquierdo de la grilla. Su thumb dice si el viewport se movió, que es
# lo que permite (a) etiquetar un hueco como "fuera_de_viewport" y (b) invalidar el mapa
# celda→disco: si la grilla se corrió, una celda ya no identifica al mismo disco.
_SCROLL_X = (0.030, 0.042)
_SCROLL_Y = (0.09, 0.92)


def scroll_pos(frame: np.ndarray) -> float | None:
    """Posición relativa (0.0 = tope, 1.0 = fondo) del thumb del scrollbar. `None` si no se
    puede medir. Centroide ponderado por brillo: sin umbral que calibrar, y estable ante el
    degradé del track. Medido: tope ≈0.17-0.21, mitad ≈0.49 (Ejemplo_3 y 4 dentro de 0.006)."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        H, W = frame.shape[:2]
        x0, x1 = int(_SCROLL_X[0] * W), int(_SCROLL_X[1] * W)
        y0, y1 = int(_SCROLL_Y[0] * H), int(_SCROLL_Y[1] * H)
        if x1 - x0 < 2 or y1 - y0 < 8:
            return None
        prof = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).mean(axis=1)
        total = float(prof.sum())
        if total <= 0.0:
            return None
        ys = np.arange(len(prof), dtype=np.float64)
        return float((prof * ys).sum() / total / max(1, len(prof) - 1))
    except Exception:
        return None


def tilde_fracs(frame: np.ndarray) -> dict[tuple[int, int], float]:
    """Fracción del annulus por celda `(fila, col)`. Para calibración y diagnóstico."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return {}
    return {
        (r, c): _badge_annulus_frac(frame, r, c)
        for r in range(GRID_ROWS)
        for c in range(GRID_COLS)
    }


def tilde_cells(frame: np.ndarray) -> frozenset[tuple[int, int]]:
    """Celdas `(fila, col)` marcadas para desmontar, según el badge de tilde.

    Sin OCR — corre en el loop rápido a 10 fps (RNF-06). Devuelve `frozenset()` ante un frame
    inválido: es la respuesta honesta de "no vi ningún tilde", y quien cuenta de verdad es el
    contador del header."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return frozenset()
    try:
        # El gate de la franja se evalúa DESPUÉS del amarillo (y solo sobre los candidatos):
        # los tildes son pocos, así que el caso común —una grilla sin nada marcado— paga
        # únicamente los 45 annulus.
        return frozenset(
            (r, c)
            for r in range(GRID_ROWS)
            for c in range(GRID_COLS)
            if _badge_annulus_frac(frame, r, c) >= _TILDE_FRAC_MIN
            and _tile_strip_frac(frame, r, c) >= _STRIP_FRAC_MIN
        )
    except Exception:
        return frozenset()

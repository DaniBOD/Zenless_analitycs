"""Lectura de la grilla de "Resultados de sintonización" (S28): las 10 recompensas del x10.

Geometría FIJA de 5 columnas × 2 filas, sin scroll — más simple que el modal "Obtenido" (S22),
donde las filas hay que detectarlas porque se corren. Medida sobre los 7 fixtures de
`Resultados_sintonizacion/` (2559×1439).

Módulo propio a propósito, siguiendo el precedente de `parser_extraccion`: de `parser_s2` se
importa solo lo que es INDEPENDIENTE de su geometría (las bandas HSV de rareza), nunca sus
cajas de tiles, que son las de S2.

Lo que se extrae por tile:
  - rareza S/A/B, por la banda de color dominante en el badge inferior-izquierdo;
  - marca `NEW!` (ítem nuevo, etiqueta amarilla arriba a la izquierda);
  - recorte del arte, para que el matcher de identidad decida QUÉ es.

⚠️ El TIER NO DETERMINA EL TIPO. En `Ejemplo_4` conviven un `A` que es agente (retrato, con
badge de duplicado ×20) y un `A` que es W-Engine (arte de arma). Quién es cada cosa lo decide
el matcher, no la rareza.

La rareza por banda se validó sobre los 7 grids: **70/70 tiles, cero abstenciones**, y
`Ejemplo_4` da `S A A` + 7 `B`, que es lo que se ve en pantalla.

Display-only: no persiste ni puntúa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.parser_s2 import _RARITY_BANDS

log = logging.getLogger(__name__)

# Etiquetas de `_RARITY_BANDS`, en su mismo orden: dorado, púrpura, azul.
_RARITY_LABELS = ("S", "A", "B")

# --- Geometría de la grilla -----------------------------------------------------------------
# Bordes x normalizados de las 5 columnas y bordes y de las 2 filas. Constantes en los 7 grids.
_COLS_X: tuple[tuple[float, float], ...] = (
    (0.1482, 0.2864),
    (0.2909, 0.4291),
    (0.4336, 0.5718),
    (0.5764, 0.7145),
    (0.7191, 0.8573),
)
_ROWS_Y: tuple[tuple[float, float], ...] = (
    (0.3344, 0.5056),
    (0.5121, 0.6833),
)

# Badge de rareza, en fracciones DEL TILE (no de la pantalla): esquina inferior izquierda.
_BADGE_X = (0.039, 0.300)
_BADGE_Y = (0.642, 0.943)

# Etiqueta `NEW!`, en fracciones del tile: esquina superior izquierda.
_NEW_X = (0.02, 0.42)
_NEW_Y = (0.00, 0.20)
# Amarillo saturado de la etiqueta `NEW!`. Más restrictivo que el realce del riel: acá no
# queremos confundirnos con el dorado del badge S, que vive abajo y fuera de esta caja.
_NEW_LO = np.array((22, 160, 180), dtype=np.uint8)
_NEW_HI = np.array((34, 255, 255), dtype=np.uint8)
_NEW_MIN = 0.06

# Fracción mínima de la banda dominante para no abstenerse. Mismo criterio que
# `parser_s2.tile_rarity`.
_RARITY_MIN = 0.10

# Recorte del arte para el matcher. Tiene que ser CUADRADO y centrado en el ítem: el descriptor
# de `avatar_descriptor` enmascara con un círculo fijo y reescala a cuadrado, así que un recorte
# rectangular se aplasta y deja de parecerse a su referencia.
# Centro del ítem dentro del tile y lado del cuadrado como fracción del ALTO del tile, medidos
# sobre los tiles de los 7 grids. Con 0.85 la esfera entra completa y quedan afuera el badge de
# rareza (inf-izq), el `NEW!` (sup-izq) y el contador de duplicado (inf-der) — esos overlays
# contaminan el color y hacen fallar el match (misma lección que `parser_s2.crop_tile_center`).
# El lado se elige para que el ítem ocupe la MISMA fracción del recorte que en las referencias
# de `Engines_icons` (~85 % de un lienzo cuadrado): la esfera in-game mide ~0.60 del ancho del
# tile ⇒ lado ≈ 1.0 × alto del tile. Con 0.85 la esfera se salía por los bordes y el match
# comparaba peras con manzanas.
_ART_CX = 0.525
_ART_CY = 0.464
_ART_SIDE_H = 1.01


@dataclass(frozen=True)
class TileBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0


@dataclass(frozen=True)
class GachaTile:
    """Una de las 10 recompensas. `rarity` None = no se pudo afirmar (RNF-02)."""
    idx: int              # 1..10, en orden de lectura (fila 1 izq→der, después fila 2)
    row: int              # 0 o 1
    col: int              # 0..4
    rarity: str | None    # 'S' | 'A' | 'B' | None
    is_new: bool
    box: TileBox


def tile_boxes(frame: np.ndarray) -> list[TileBox]:
    """Las 10 cajas, en orden de lectura."""
    h, w = frame.shape[:2]
    out: list[TileBox] = []
    for (ya, yb) in _ROWS_Y:
        for (xa, xb) in _COLS_X:
            out.append(TileBox(int(xa * w), int(ya * h), int(xb * w), int(yb * h)))
    return out


def _sub(frame: np.ndarray, box: TileBox,
         fx: tuple[float, float], fy: tuple[float, float]) -> np.ndarray:
    x0 = box.x0 + int(fx[0] * box.w)
    x1 = box.x0 + int(fx[1] * box.w)
    y0 = box.y0 + int(fy[0] * box.h)
    y1 = box.y0 + int(fy[1] * box.h)
    return frame[max(0, y0):y1, max(0, x0):x1]


def tile_rarity(frame: np.ndarray, box: TileBox) -> str | None:
    """Rareza por la banda de color dominante en el badge. None si ninguna llega al mínimo."""
    sub = _sub(frame, box, _BADGE_X, _BADGE_Y)
    if sub.size == 0:
        return None
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    best, best_frac = None, 0.0
    for label, (lo, hi) in zip(_RARITY_LABELS, _RARITY_BANDS):
        frac = float(cv2.inRange(hsv, np.array(lo), np.array(hi)).mean()) / 255.0
        if frac > best_frac:
            best_frac, best = frac, label
    return best if best_frac >= _RARITY_MIN else None


def tile_is_new(frame: np.ndarray, box: TileBox) -> bool:
    """¿El tile trae la etiqueta `NEW!`? (ítem que no se tenía)."""
    sub = _sub(frame, box, _NEW_X, _NEW_Y)
    if sub.size == 0:
        return False
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    frac = float(cv2.inRange(hsv, _NEW_LO, _NEW_HI).mean()) / 255.0
    return frac >= _NEW_MIN


def crop_tile_art(frame: np.ndarray, box: TileBox) -> np.ndarray:
    """Arte del tile como recorte CUADRADO centrado en el ítem, listo para el matcher."""
    half = int(_ART_SIDE_H * box.h / 2)
    cx = box.x0 + int(_ART_CX * box.w)
    cy = box.y0 + int(_ART_CY * box.h)
    h, w = frame.shape[:2]
    x0, x1 = max(0, cx - half), min(w, cx + half)
    y0, y1 = max(0, cy - half), min(h, cy + half)
    return frame[y0:y1, x0:x1]


def parse_grid(frame: np.ndarray) -> list[GachaTile]:
    """Las 10 recompensas con su rareza y su marca de nuevo. Sin identidad: eso lo agrega
    quien tenga las librerías de referencia cargadas."""
    tiles: list[GachaTile] = []
    for i, box in enumerate(tile_boxes(frame)):
        tiles.append(GachaTile(
            idx=i + 1,
            row=i // len(_COLS_X),
            col=i % len(_COLS_X),
            rarity=tile_rarity(frame, box),
            is_new=tile_is_new(frame, box),
            box=box,
        ))
    return tiles


def count_rarity_badges(frame: np.ndarray) -> int:
    """Cuántos de los 10 tiles tienen un badge de rareza legible.

    Es la señal de verificación de S28: la grilla real da 10; una pantalla que no es la grilla
    no tiene badges en esa geometría.
    """
    return sum(1 for t in parse_grid(frame) if t.rarity is not None)

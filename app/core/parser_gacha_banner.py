"""Lectura del banner de sintonización (S27): qué canal está seleccionado.

El riel izquierdo tiene 6 pastillas fijas (una por canal). La seleccionada se marca con un
REALCE AMARILLO en el marco de la pastilla. Ese realce es la única señal de selección: el
texto del riel no alcanza, porque hay dos "Canal Exclusivo" y dos "Canal Amplificado" y no se
distinguen entre sí por su rótulo.

⚠️ Trampa medida (2026-07-29): el canal Estable (#5) tiene un TELEVISOR AMARILLO permanente
como ícono, y la etiqueta "CHANNEL" de cada pastilla también es amarilla. Un "el más amarillo
gana" sobre la pastilla entera elige SIEMPRE el #5. Por eso la máscara se aplica solo sobre el
MARCO EXTERIOR, con el interior enmascarado. Medido sobre los 6 banners de 3.1:

    seleccionado   0.036 – 0.076
    no seleccionado 0.000, salvo el #5 que deja 0.005 de residuo del televisor

Hueco de 7× entre el peor positivo y el peor negativo ⇒ umbral cómodo en 0.015.

El ORDEN del riel es fijo y es lo que da el TIPO de canal sin depender de OCR ni de matcher.
Verificado idéntico en los 6 fixtures de 3.1. Si un patch lo cambia, la regresión lo marca.

La IDENTIDAD del banner (Aria vs Remielle, que comparten el rótulo "Canal Exclusivo") sale del
ícono de la pastilla vía `AvatarMatcher`, y es OPCIONAL: si el matcher se abstiene se reporta
el índice y el tipo, nunca un nombre inventado (RNF-02).

Display-only: no persiste nada.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

# --- Geometría del riel ---------------------------------------------------------------------
# Centros y normalizados de las 6 pastillas, y el semi-alto de la caja que las contiene.
# Medidos sobre los 6 banners (2559×1439); el riel no se mueve entre canales ni entre banners.
_PILL_CY = (0.1534, 0.2503, 0.3473, 0.4474, 0.5476, 0.6462)
_PILL_HALF_H = 0.0485
# Extensión x de la pastilla (borde izquierdo de pantalla → fin del rótulo).
_PILL_X = (0.0254, 0.1317)

# Grosor del marco como fracción del alto de la caja. Con 0.14 el interior queda excluido, que
# es lo que neutraliza el televisor del #5 y la etiqueta "CHANNEL".
_RING_FRAC = 0.14

# Amarillo del realce en HSV. Mismo tono que la etiqueta "CHANNEL", por eso hace falta el marco.
_YELLOW_LO = np.array((20, 150, 150), dtype=np.uint8)
_YELLOW_HI = np.array((35, 255, 255), dtype=np.uint8)

# Umbral de selección: en el medio del hueco medido (0.005 ↔ 0.036).
_SEL_MIN = 0.015

# Tipo de canal por posición en el riel. Fijo en los 6 fixtures de 3.1.
CHANNEL_TYPES: tuple[str, ...] = (
    "Exclusivo",     # 1 — agente destacado
    "Exclusivo",     # 2 — agente destacado
    "Amplificado",   # 3 — W-Engine destacado
    "Amplificado",   # 4 — W-Engine destacado
    "Estable",       # 5 — permanente
    "Bangbu",        # 6 — bangbú
)

# Qué clase de ítem destaca cada tipo de canal. Sirve para decidir contra qué librería
# matchear el ícono de la pastilla.
CHANNEL_ITEM_KIND: dict[str, str] = {
    "Exclusivo": "agente",
    "Amplificado": "engine",
    "Estable": "mixto",
    "Bangbu": "bangbu",
}


@dataclass(frozen=True)
class ChannelSel:
    """Canal seleccionado en el riel del banner.

    `idx` es 1-based (como se ve en pantalla). `nombre` es None cuando el matcher se
    abstiene — que es el caso normal y esperado, no un error.
    """
    idx: int
    tipo: str
    score: float
    nombre: str | None = None

    @property
    def item_kind(self) -> str:
        return CHANNEL_ITEM_KIND.get(self.tipo, "mixto")


def _pill_box(h: int, w: int, i: int) -> tuple[int, int, int, int]:
    """Caja (x0, y0, x1, y1) en píxeles de la pastilla `i` (0-based)."""
    cy = _PILL_CY[i]
    y0 = max(0, int((cy - _PILL_HALF_H) * h))
    y1 = min(h, int((cy + _PILL_HALF_H) * h))
    x0 = max(0, int(_PILL_X[0] * w))
    x1 = min(w, int(_PILL_X[1] * w))
    return x0, y0, x1, y1


def _ring_mask(bh: int, bw: int) -> np.ndarray:
    """Máscara del marco exterior de la caja (interior a cero)."""
    m = np.full((bh, bw), 255, dtype=np.uint8)
    b = max(2, int(_RING_FRAC * bh))
    if bh > 2 * b and bw > 2 * b:
        m[b:bh - b, b:bw - b] = 0
    return m


def pill_highlight_scores(frame: np.ndarray) -> list[float]:
    """Fracción de píxeles amarillos en el MARCO de cada una de las 6 pastillas."""
    if frame is None or frame.size == 0:
        return [0.0] * len(_PILL_CY)
    h, w = frame.shape[:2]
    out: list[float] = []
    for i in range(len(_PILL_CY)):
        x0, y0, x1, y1 = _pill_box(h, w, i)
        sub = frame[y0:y1, x0:x1]
        if sub.size == 0:
            out.append(0.0)
            continue
        mask = _ring_mask(sub.shape[0], sub.shape[1])
        hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, _YELLOW_LO, _YELLOW_HI)
        denom = int(mask.sum())
        out.append(float((yellow & mask).sum()) / denom if denom else 0.0)
    return out


def selected_channel(frame: np.ndarray) -> ChannelSel | None:
    """Canal seleccionado, o None si ninguna pastilla supera el umbral de realce.

    None significa "no puedo afirmarlo" (p.ej. el frame no es un banner, o está en
    transición), no "no hay ninguno seleccionado".
    """
    scores = pill_highlight_scores(frame)
    if not scores:
        return None
    i = int(np.argmax(scores))
    if scores[i] < _SEL_MIN:
        return None
    return ChannelSel(idx=i + 1, tipo=CHANNEL_TYPES[i], score=round(scores[i], 4))


def crop_pill_icon(frame: np.ndarray, idx: int) -> np.ndarray | None:
    """Recorta el ícono de la pastilla `idx` (1-based) para el matcher de identidad.

    El ícono ocupa el tercio izquierdo de la pastilla; el resto es el rótulo de texto.
    """
    if frame is None or frame.size == 0 or not (1 <= idx <= len(_PILL_CY)):
        return None
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = _pill_box(h, w, idx - 1)
    bw = x1 - x0
    icon = frame[y0:y1, x0:x0 + int(0.48 * bw)]
    return icon if icon.size else None

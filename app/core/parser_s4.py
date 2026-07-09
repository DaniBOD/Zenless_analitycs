"""Parser del selector de la tienda de música de Orphie (S4, "Plan de entrenamiento").

Dos lecturas display-only para predecir el farmeo (alimentan `FarmSession`, como S13):
  - `read_music_genre(frame, ocr)`: OCR del nombre del **género** (abajo-izq, bajo "Preferencia
    de género"). El género ES un set de la DB (`disc_sets.nombre`) → se resuelve con
    `DiscSetRepo.resolve_id`. ROI alto + psm=6 porque los nombres largos se envuelven a 2 líneas.
  - `read_preselected_slot(frame)`: slot preseleccionado en el hexágono "DRIVER". Las 6 posiciones
    son FIJAS (TL=1, TR=6, ML=2, MR=5, BL=3, BR=4); el elegido se resalta como un "+" amarillo/lima.
    Se lee por geometría + máscara amarilla (no por dígito). Ninguna resaltada → None (aleatorio).

Calibrado 2026-07-09 contra las 9 capturas de `18_Seleccion_set_farmeo_tienda_musica`. Sin
dependencia de OCR para el slot (RNF-06)."""
from __future__ import annotations

import cv2
import numpy as np

# ROI del nombre del género (x0, y0, x1, y1 normalizados). Alto para captar nombres envueltos.
_S4_GENRE_ROI = (0.45, 0.835, 0.615, 0.925)

# Centros (fracción) de las 6 posiciones del hexágono DRIVER. Leídos de la grilla real.
_S4_HEX_POSITIONS: dict[int, tuple[float, float]] = {
    1: (0.731, 0.337), 6: (0.849, 0.337),
    2: (0.690, 0.486), 5: (0.889, 0.486),
    3: (0.731, 0.639), 4: (0.849, 0.639),
}
_S4_HEX_R = 0.030                              # radio del sample cuadrado alrededor del centro
_S4_HEX_YELLOW_MIN = 0.08                      # fracción mínima de amarillo → seleccionado (obs. ≥0.19)
_S4_YELLOW_LO = np.array([22, 70, 110], np.uint8)   # amarillo/lima del "+" (H 22-60)
_S4_YELLOW_HI = np.array([60, 255, 255], np.uint8)


def read_music_genre(frame: np.ndarray, ocr) -> str | None:
    """OCR del nombre del género (= set) del selector. Devuelve el texto crudo (whitespace
    colapsado) o None. La resolución a set_id la hace el consumidor vía `DiscSetRepo.resolve_id`
    (tolera ruido OCR: tildes, letras dropeadas, prefijo 'DEMO', espacios perdidos)."""
    if frame is None or ocr is None:
        return None
    try:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = _S4_GENRE_ROI
        crop = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if crop.size == 0:
            return None
        text, _conf = ocr.text(crop, psm=6, lang="spa")
    except Exception:
        return None
    text = " ".join((text or "").split())
    return text or None


def _yellow_frac(frame: np.ndarray, cx: float, cy: float) -> float:
    h, w = frame.shape[:2]
    crop = frame[int((cy - _S4_HEX_R) * h):int((cy + _S4_HEX_R) * h),
                 int((cx - _S4_HEX_R) * w):int((cx + _S4_HEX_R) * w)]
    if crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, _S4_YELLOW_LO, _S4_YELLOW_HI)
    return float(m.mean()) / 255.0


def read_preselected_slot(frame: np.ndarray) -> int | None:
    """Slot 1-6 preseleccionado (posición del hexágono con el "+" amarillo), o None si ninguno
    (aleatorio). Un solo slot puede estar seleccionado a la vez. Sin OCR (RNF-06)."""
    if frame is None or frame.size == 0:
        return None
    vals = {slot: _yellow_frac(frame, cx, cy) for slot, (cx, cy) in _S4_HEX_POSITIONS.items()}
    best = max(vals, key=vals.get)
    return best if vals[best] >= _S4_HEX_YELLOW_MIN else None

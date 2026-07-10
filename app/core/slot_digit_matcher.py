"""Matcher del dígito de slot (1-6) del tile S2 por template (NCC), no OCR.

El dígito de slot del hexágono arriba-izquierda de cada tile de disco en la pantalla de
resultados (S2) es un glifo ESTILIZADO metálico y chico. PaddleOCR lo lee mal de forma crónica
(la familia de errores vista en vivo: '5'↔'S', '6'→'5', '4'→'2'). Como los glifos son un
conjunto FIJO de 6 (1-6), la correlación cruzada normalizada (NCC) contra referencias reales es
mucho más robusta que el OCR.

Truco clave de discriminación: el **hexágono de fondo es idéntico** en todos los slots y domina
la correlación (todos los dígitos correlan ~0.99). Se resta el **template promedio** de todas las
referencias para aislar el residuo específico del dígito → la separación entre dígitos pasa de
~0.12 a ~0.5 de margen. Se recorta además el centro del badge (donde está el dígito, descartando
el borde del hexágono).

Las referencias son recortes reales de tiles S2 (carpeta `app/resources/slot_digits/`, nombre
`<digito>_<origen>_<i>.png`), etiquetados por inspección visual. `identify` abstiene por score
(RNF-02: no adivinar); se usa como camino primario en `parser_s2.read_tile_slot`, con el OCR
como fallback.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

_REFS_DIR = Path(__file__).resolve().parent.parent / "resources" / "slot_digits"

# Recorte central del badge (y0, y1, x0, x1 como fracciones): descarta el borde del hexágono y
# deja el dígito. Tamaño canónico del template (alto × ancho).
_CENTRAL = (0.18, 0.82, 0.16, 0.84)
_TPL_H, _TPL_W = 40, 48

# Abstención por score NCC del residuo. Calibrado por leave-one-out sobre las 30 refs: los
# aciertos correlan ≥0.88 (media 0.96); los cruces de dígito y los crops mal encuadrados quedan
# ≤0.42 → un piso en 0.65 separa limpio. Margen chico extra por si dos dígitos empatan.
_MIN_SCORE = 0.65
_MIN_MARGIN = 0.03


def _raw_vec(crop_bgr: np.ndarray) -> np.ndarray | None:
    """Crop BGR → vector crudo (gris, recorte central, resize fijo) SIN normalizar. La resta del
    template promedio y la normalización las hace el matcher (necesita el promedio del set)."""
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return None
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY) if crop_bgr.ndim == 3 else crop_bgr
    h, w = gray.shape[:2]
    y0, y1, x0, x1 = _CENTRAL
    cen = gray[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    if cen.size == 0:
        return None
    return cv2.resize(cen, (_TPL_W, _TPL_H), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()


class SlotDigitMatcher:
    """Clasifica el dígito de slot (1-6) de un crop de badge por NCC del residuo (crop − promedio)
    contra referencias reales."""

    def __init__(self, refs_raw: dict[int, list[np.ndarray]]):
        all_raw = [r for vs in refs_raw.values() for r in vs if r is not None]
        self._mean = np.mean(all_raw, axis=0) if all_raw else None
        self._refs: dict[int, list[np.ndarray]] = {}
        for d, vs in refs_raw.items():
            res = [self._residual(r) for r in vs if r is not None]
            res = [v for v in res if v is not None]
            if res:
                self._refs[d] = res

    def _residual(self, raw: np.ndarray | None) -> np.ndarray | None:
        """raw − template promedio → media 0 / norma 1 (para NCC vía producto punto)."""
        if raw is None or self._mean is None:
            return None
        v = raw - self._mean
        v = v - v.mean()
        n = np.linalg.norm(v)
        return v / n if n > 1e-6 else None

    @property
    def n_refs(self) -> int:
        return sum(len(vs) for vs in self._refs.values())

    @classmethod
    def from_resources(cls, refs_dir: Path | None = None) -> "SlotDigitMatcher":
        """Carga las referencias de `slot_digits/` (nombre `<digito>_*.png`). Nunca lanza: si el
        directorio falta o algún archivo no lee, se omite (feature opcional, display-only)."""
        d = Path(refs_dir) if refs_dir is not None else _REFS_DIR
        refs_raw: dict[int, list[np.ndarray]] = {}
        try:
            for p in sorted(d.glob("*.png")):
                try:
                    digit = int(p.name.split("_", 1)[0])
                except (ValueError, IndexError):
                    continue
                if not (1 <= digit <= 6):
                    continue
                img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
                raw = _raw_vec(img)
                if raw is not None:
                    refs_raw.setdefault(digit, []).append(raw)
        except OSError:
            log.debug("No se pudieron cargar refs de slot_digits", exc_info=True)
        return cls(refs_raw)

    def identify(self, crop_bgr: np.ndarray) -> tuple[int | None, float]:
        """Devuelve (slot 1-6, score) del dígito más parecido, o (None, score) si abstiene por
        score/margen. Score = mejor NCC del residuo (∈ [-1, 1])."""
        return self.identify_raw(_raw_vec(crop_bgr))

    def score_vector(self, crop_bgr: np.ndarray) -> dict[int, float]:
        """Score NCC del residuo por cada dígito 1-6 (sin abstención), para decisiones con contexto
        (p.ej. corrección monótona de la grilla S5). {} si el crop no produce residuo."""
        q = self._residual(_raw_vec(crop_bgr))
        if q is None or not self._refs:
            return {}
        return {d: max(float(q @ r) for r in vs) for d, vs in self._refs.items()}

    def identify_raw(self, raw: np.ndarray | None) -> tuple[int | None, float]:
        """Como `identify` pero desde un vector crudo (`_raw_vec`). Núcleo del scoring; separa la
        extracción del crop del matching (útil para el test leave-one-out)."""
        q = self._residual(raw)
        if q is None or not self._refs:
            return None, 0.0
        per_digit = {d: max(float(q @ r) for r in vs) for d, vs in self._refs.items()}
        ranked = sorted(per_digit.items(), key=lambda kv: kv[1], reverse=True)
        best_d, best_s = ranked[0]
        second_s = ranked[1][1] if len(ranked) > 1 else -1.0
        if best_s < _MIN_SCORE or (best_s - second_s) < _MIN_MARGIN:
            return None, best_s
        return best_d, best_s

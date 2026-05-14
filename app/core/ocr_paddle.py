"""
Hito 2.4.3 — Backend OCR: PaddleOCR (números densos, substats con dígitos).
Lazy-load: solo inicializa en primera invocación para no bloquear el arranque.

Nota: en sistemas Windows con MAX_PATH limitado, paddlepaddle/paddleocr
se instalan en un path corto (D:\\paddle_site). Este módulo agrega ese
path automáticamente si paddleocr no es importable desde site-packages.
"""
from __future__ import annotations

import sys

import numpy as np

from app.core.ocr_backend import OcrBackend

_PADDLE_SITE = r"D:\paddle_site"


def _ensure_paddle_site() -> bool:
    """Agrega D:\\paddle_site a sys.path si existe y paddleocr no es importable."""
    if _PADDLE_SITE in sys.path:
        return True
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        pass
    import os
    if os.path.isdir(_PADDLE_SITE):
        sys.path.insert(0, _PADDLE_SITE)
        return True
    return False


_ensure_paddle_site()


class PaddleBackend(OcrBackend):
    """
    Adapter sobre PaddleOCR. Mejor que Tesseract para números pequeños
    y texto con anti-aliasing en fondos oscuros (ej. valores de substats).
    """

    def __init__(self, lang: str = "es", use_gpu: bool = False):
        self._lang = lang
        self._use_gpu = use_gpu
        self._ocr = None  # lazy-loaded

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                _ensure_paddle_site()
                kwargs = dict(
                    use_textline_orientation=False,
                    lang=self._lang,
                )
                # Detectar parámetros soportados por la versión instalada
                import inspect
                sig = inspect.signature(PaddleOCR.__init__)
                if "use_gpu" in sig.parameters:
                    kwargs["use_gpu"] = self._use_gpu
                self._ocr = PaddleOCR(**kwargs)
            except ImportError as e:
                raise RuntimeError(
                    "paddleocr no instalado. Ejecutar: pip install paddleocr"
                ) from e
        return self._ocr

    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        # PaddleOCR no usa PSM — el parámetro se ignora para compatibilidad
        ocr = self._get_ocr()
        try:
            result = ocr.ocr(img, cls=False)
        except Exception:
            return "", 0.0

        if not result or not result[0]:
            return "", 0.0

        texts = []
        confs = []
        for line in result[0]:
            if line and len(line) >= 2:
                txt = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                conf = float(line[1][1]) if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 0.5
                texts.append(txt.strip())
                confs.append(conf)

        text = " ".join(texts).strip()
        avg_conf = (sum(confs) / len(confs)) if confs else 0.0
        return text, round(avg_conf, 3)

    def text_with_bboxes(self, img: np.ndarray) -> list[tuple[str, float, tuple[int, int, int, int]]]:
        """
        Devuelve [(texto, confianza, (x1,y1,x2,y2)), ...] con bboxes reales
        detectados por PaddleOCR. Cada bbox es la bounding box del polígono
        cuadrilátero que devuelve el detector DBNet.
        """
        ocr = self._get_ocr()
        try:
            result = ocr.ocr(img, cls=False)
        except Exception:
            return []

        if not result or not result[0]:
            return []

        out: list[tuple[str, float, tuple[int, int, int, int]]] = []
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            polygon, (text, conf) = line[0], line[1]
            if not polygon or len(polygon) < 4:
                continue
            xs = [int(p[0]) for p in polygon]
            ys = [int(p[1]) for p in polygon]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)
            txt = str(text).strip()
            conf_val = float(conf) if conf else 0.5
            if txt:
                out.append((txt, conf_val, (x1, y1, x2, y2)))

        return out

    def number(self, img: np.ndarray) -> tuple[float, float]:
        import re
        text, conf = self.text(img)
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if not m:
            return 0.0, 0.0
        return float(m.group(1)), conf

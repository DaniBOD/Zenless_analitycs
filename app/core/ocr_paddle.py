"""
Hito 2.4.3 — Backend OCR: PaddleOCR (números densos, substats con dígitos).
Lazy-load: solo inicializa en primera invocación para no bloquear el arranque.
"""
from __future__ import annotations

import numpy as np

from app.core.ocr_backend import OcrBackend


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
                self._ocr = PaddleOCR(
                    use_angle_cls=False,
                    lang=self._lang,
                    use_gpu=self._use_gpu,
                    show_log=False,
                )
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

    def number(self, img: np.ndarray) -> tuple[float, float]:
        import re
        text, conf = self.text(img)
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if not m:
            return 0.0, 0.0
        return float(m.group(1)), conf

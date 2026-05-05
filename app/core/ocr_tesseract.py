"""
Hito 2.4.2 — Backend OCR: Tesseract (texto + nombres de stats).
Preprocesa la imagen antes de enviarla a Tesseract.
"""
from __future__ import annotations

import re

import numpy as np

from app.core.ocr_backend import OcrBackend


class TesseractBackend(OcrBackend):
    """Adapter sobre pytesseract con preprocesado para UI de ZZZ."""

    def __init__(self, tesseract_cmd: str | None = None):
        try:
            import pytesseract
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._tess = pytesseract
        except ImportError as e:
            raise RuntimeError(
                "pytesseract no instalado. Ejecutar: pip install pytesseract"
            ) from e

    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        processed = self.preprocess(img)
        config = f"--psm {psm} --oem 3"
        try:
            data = self._tess.image_to_data(
                processed, lang=lang, config=config,
                output_type=self._tess.Output.DICT,
            )
        except Exception:
            return "", 0.0

        words = []
        confs = []
        for word, conf in zip(data["text"], data["conf"]):
            word = word.strip()
            if word and conf != -1:
                words.append(word)
                confs.append(int(conf))

        text = " ".join(words).strip()
        avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return text, round(avg_conf, 3)

    def number(self, img: np.ndarray) -> tuple[float, float]:
        processed = self.preprocess(img)
        # PSM 8 = single word; digits + % only
        config = "--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789.%"
        try:
            raw = self._tess.image_to_string(processed, config=config).strip()
        except Exception:
            return 0.0, 0.0

        # Parse float with optional %
        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if not m:
            return 0.0, 0.0
        val = float(m.group(1))
        # Confidence from data mode
        _, conf = self.text(img, psm=8)
        return val, conf

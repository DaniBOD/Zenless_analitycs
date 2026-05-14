"""
Hito 2.4.2 — Backend OCR: Tesseract (texto + nombres de stats).
Preprocesa la imagen antes de enviarla a Tesseract.

Pipeline de preprocesado optimizado para UI oscura de ZZZ:
1. Upscale 3x con INTER_CUBIC (Tesseract necesita >300dpi efectivos para texto pequeño)
2. Invertir grayscale (texto blanco sobre negro → negro sobre blanco)
3. Threshold Otsu (separación clara texto/background)
4. Sin denoising agresivo (destruye el texto a tamaño pequeño)
"""
from __future__ import annotations

import re

import cv2
import numpy as np

from app.core.ocr_backend import OcrBackend


# Factor de upscale para texto pequeño en UIs. Tesseract trabaja mejor con
# texto de altura >= 30 px. La mayoría de ROIs de ZZZ tienen altura ~20-40 px
# nativa, así que 3x sube a 60-120 px (más holgado para el OCR).
UPSCALE_FACTOR = 3


def _autodetect_tesseract_cmd() -> str | None:
    """Busca tesseract.exe en rutas Windows típicas + env var TESSERACT_CMD."""
    import os
    import shutil

    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd

    found = shutil.which("tesseract")
    if found:
        return found

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


class TesseractBackend(OcrBackend):
    """Adapter sobre pytesseract con preprocesado para UI de ZZZ."""

    def __init__(self, tesseract_cmd: str | None = None):
        try:
            import pytesseract
            if tesseract_cmd is None:
                tesseract_cmd = _autodetect_tesseract_cmd()
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._tess = pytesseract
        except ImportError as e:
            raise RuntimeError(
                "pytesseract no instalado. Ejecutar: pip install pytesseract"
            ) from e

    @staticmethod
    def preprocess(img: np.ndarray) -> np.ndarray:
        """
        Pipeline optimizado para texto blanco-amarillo sobre fondo oscuro
        (UI de ZZZ). Override del preprocess base de OcrBackend.
        """
        if img is None or img.size == 0:
            return img

        # 1. A grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

        # 2. Upscale 3x para Tesseract — INTER_CUBIC preserva bordes mejor que LINEAR
        h, w = gray.shape
        gray_up = cv2.resize(
            gray, (w * UPSCALE_FACTOR, h * UPSCALE_FACTOR),
            interpolation=cv2.INTER_CUBIC,
        )

        # 3. Invertir: texto blanco/claro → texto negro sobre fondo claro
        inverted = cv2.bitwise_not(gray_up)

        # 4. Binarización Otsu (encuentra threshold óptimo automáticamente)
        _, binary = cv2.threshold(
            inverted, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        return binary

    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        processed = self.preprocess(img)
        if processed is None or processed.size == 0:
            return "", 0.0
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

    def text_with_bboxes(self, img: np.ndarray) -> list[tuple[str, float, tuple[int, int, int, int]]]:
        """Tesseract no expone bboxes de detección — devuelve vacío."""
        return []

    def number(self, img: np.ndarray) -> tuple[float, float]:
        processed = self.preprocess(img)
        if processed is None or processed.size == 0:
            return 0.0, 0.0
        # PSM 7 = single line; digits + % + punto decimal
        config = "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789.%"
        try:
            raw = self._tess.image_to_string(processed, config=config).strip()
        except Exception:
            return 0.0, 0.0

        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if not m:
            return 0.0, 0.0
        val = float(m.group(1))
        _, conf = self.text(img, psm=7)
        return val, conf

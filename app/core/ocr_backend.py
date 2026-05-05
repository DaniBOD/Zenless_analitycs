"""
Hito 2.4.1 — Interfaz abstracta para backends OCR.
Permite intercambiar Tesseract <-> PaddleOCR sin cambiar el parser.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class OcrBackend(ABC):
    """Interfaz mínima que deben cumplir todos los backends OCR."""

    @abstractmethod
    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        """
        Devuelve (texto_limpio, confianza 0-1).
        psm: Tesseract page-segmentation mode (6=bloque, 7=línea única).
        """

    @abstractmethod
    def number(self, img: np.ndarray) -> tuple[float, float]:
        """
        Devuelve (valor_numérico, confianza 0-1).
        Optimizado para ROIs que contienen solo dígitos/porcentaje.
        """

    @staticmethod
    def preprocess(img: np.ndarray) -> np.ndarray:
        """
        Pipeline de preprocesado estándar compartido por todos los backends.
        Entrada: BGR (numpy array). Salida: grayscale binarizado.
        """
        import cv2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        # Denoising leve para texto sobre fondo oscuro ZZZ
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        # Binarización adaptativa (mejor que global para fondos no uniformes)
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )
        return binary

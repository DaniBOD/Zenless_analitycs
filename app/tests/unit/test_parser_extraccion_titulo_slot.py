"""El slot del título del panel DETAIL de S22 cuando el OCR rompe el "(1)".

QA en vivo 2026-10-01 (farmeo por baterías): el disco "Hado emplumado (1)" no se detectaba. En la
captura nativa 2560×1440 PaddleOCR lee el título como `Hadoemplumado()` (conf 0,99) —se come el
"1"— y a otras escalas como `(i)`. Sin "(N)" el panel se descartaba en silencio.

- Pasada de rescate con el alias de dígitos de `parser_sustitucion` (misma autoridad, B1).
- Paréntesis vacío → una segunda lectura de la franja con margen.
- Sin paréntesis sigue sin haber slot: un material ("×3") nunca es un disco (RNF-02).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import parser_extraccion as pe

_FX = Path(__file__).resolve().parents[1] / "fixtures" / "s22_titulo_slot1_parentesis_vacio.png"
_W, _H = 2560, 1440


class _OcrFalso:
    """Devuelve una lectura por llamada, en orden."""

    def __init__(self, *lecturas: str):
        self.lecturas = list(lecturas)
        self.llamadas = 0

    def text_with_bboxes(self, _img):
        t = self.lecturas[min(self.llamadas, len(self.lecturas) - 1)]
        self.llamadas += 1
        return [(t, 0.99, (0, 0, 10, 10))]


def _frame() -> np.ndarray:
    return np.zeros((_H, _W, 3), np.uint8)


@pytest.mark.parametrize("leido, slot", [("Salönhuracanado (i)", 1), ("Hadoemplumado(l)", 1),
                                         ("Hadoemplumado(|)", 1), ("Firmamentollameante (4)", 4)])
def test_el_alias_rescata_el_digito(leido, slot):
    nombre, got = pe._read_detail_title(_frame(), _OcrFalso(leido))
    assert got == slot
    assert nombre and "(" not in nombre


def test_el_parentesis_vacio_se_relee_con_margen():
    ocr = _OcrFalso("Hadoemplumado()", "Hadoemplumado(1)")
    assert pe._read_detail_title(_frame(), ocr) == ("Hadoemplumado", 1)
    assert ocr.llamadas == 2


def test_si_la_relectura_tampoco_lo_trae_se_abstiene():
    ocr = _OcrFalso("Hadoemplumado()", "Hadoemplumado()")
    assert pe._read_detail_title(_frame(), ocr) == (None, None)


@pytest.mark.parametrize("leido", ["Créditoproxy", "Materialx3", "Hadoemplumado"])
def test_sin_parentesis_no_hay_slot(leido):
    ocr = _OcrFalso(leido)
    assert pe._read_detail_title(_frame(), ocr) == (None, None)
    assert ocr.llamadas == 1, "la relectura es sólo para el paréntesis vacío"


@pytest.mark.skipif(not _FX.exists(), reason="fixture de la franja no presente")
def test_la_franja_real_del_slot_1():
    """La franja tal cual la capturó la app en vivo, puesta en su ROI de un frame 2560×1440."""
    try:
        from app.core.ocr_paddle import PaddleBackend
        ocr = PaddleBackend()
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    franja = cv2.imdecode(np.fromfile(str(_FX), np.uint8), cv2.IMREAD_COLOR)
    frame = _frame()
    x, y, w, h = pe._DETAIL_TITLE_ROI
    x0, y0 = int(x * _W), int(y * _H)
    frame[y0:y0 + franja.shape[0], x0:x0 + franja.shape[1]] = franja
    from app.core.capturer import crop_roi
    assert crop_roi(frame, pe._DETAIL_TITLE_ROI).shape == franja.shape, "la franja no cae en su ROI"
    nombre, slot = pe._read_detail_title(frame, ocr)
    assert slot == 1
    assert nombre and "emplumado" in nombre.lower()

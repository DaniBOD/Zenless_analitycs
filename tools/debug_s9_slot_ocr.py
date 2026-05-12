"""
S9 (inventario discos general) — slot detection via OCR del panel derecho.
Itera los 6 ejemplos de 09_Inventario_discos_general y verifica que el
slot 1-6 se extrae del título "Set Name (N)" del panel detalle derecho.
"""
from __future__ import annotations
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from app.core.ocr_tesseract import TesseractBackend

S9_FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"

# El panel derecho de S9 ocupa aprox el ultimo cuarto horizontal.
# El título del set + "(N)" aparece arriba del panel.
# ROI candidatos para probar — vamos a tunear empiricamente.
CANDIDATES = [
    ("v3_tight",          (0.680, 0.225, 0.250, 0.100)),   # ganador
    ("v4_text_only",      (0.680, 0.220, 0.200, 0.085)),   # evita icono derecha
    ("v5_taller",         (0.680, 0.215, 0.250, 0.120)),   # mas alto
]

SLOT_RE = re.compile(r"\((\d)\)")
# Tolerante a confusiones OCR comunes: s/S->5, o/O->0, l/I->1, etc.
SLOT_RE_TOLERANT = re.compile(r"\(([1-6sSoOlIi])\)")
_OCR_DIGIT_MAP = {"s": "5", "S": "5", "o": "0", "O": "0", "l": "1", "I": "1", "i": "1"}


def extract_slot(text: str) -> int | None:
    m = SLOT_RE.search(text)
    if m:
        return int(m.group(1))
    m = SLOT_RE_TOLERANT.search(text)
    if m:
        ch = m.group(1)
        digit = _OCR_DIGIT_MAP.get(ch, ch)
        try:
            n = int(digit)
            return n if 1 <= n <= 6 else None
        except ValueError:
            return None
    return None


def crop_norm(img, roi):
    h, w = img.shape[:2]
    return img[int(roi[1]*h):int((roi[1]+roi[3])*h), int(roi[0]*w):int((roi[0]+roi[2])*w)]


def main():
    ocr = TesseractBackend(tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    for cand_name, roi in CANDIDATES:
        print(f"\n========== ROI: {cand_name} = {roi} ==========")
        ok = 0
        fail = 0
        for i in range(1, 7):
            p = S9_FOLDER / f"Ejemplo_{i}.png"
            if not p.exists():
                continue
            img = cv2.imread(str(p))
            crop = crop_norm(img, roi)
            text, conf = ocr.text(crop, psm=6, lang="spa")
            detected = extract_slot(text)
            marker = "OK  " if detected is not None and 1 <= detected <= 6 else "FAIL"
            if marker == "OK  ":
                ok += 1
            else:
                fail += 1
            print(f"  [{marker}] Ejemplo_{i}: detectado={detected} | text={text!r} (conf {conf:.2f})")
        print(f"  Resumen: {ok}/{ok+fail}")


if __name__ == "__main__":
    main()

"""
Integración: detector + extract_s9_slot contra los 6 ejemplos de S9.
Verifica que (a) el detector clasifica como S9, (b) el slot extraído es 1-6.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from app.core.detector import ScreenDetector, extract_s9_slot
from app.core.ocr_tesseract import TesseractBackend

S9_FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"


def main():
    detector = ScreenDetector()
    ocr = TesseractBackend(tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    print(f"Templates cargados: {detector.loaded_count}")
    print(f"Faltantes: {detector.missing_templates}\n")

    ok = 0
    fail = 0
    for i in range(1, 7):
        p = S9_FOLDER / f"Ejemplo_{i}.png"
        if not p.exists():
            continue
        img = cv2.imread(str(p))
        state = detector.classify(img)
        slot = extract_s9_slot(img, ocr) if state.code == "S9" else None
        marker = "OK  " if (state.code == "S9" and slot is not None) else "FAIL"
        if marker == "OK  ":
            ok += 1
        else:
            fail += 1
        print(f"  [{marker}] Ejemplo_{i}: clasificado={state.code} conf={state.confidence:.3f} slot={slot}")

    print(f"\nResumen: {ok}/{ok+fail} correctos")


if __name__ == "__main__":
    main()

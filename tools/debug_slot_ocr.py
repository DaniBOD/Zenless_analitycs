"""
Slot 1-6 OCR detection test. Itera los 12 screenshots y verifica que cada
slot se extrae correctamente del titulo "Set Name (N)".
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

SLOT_FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/14_Slots_equipamiento"
TITLE_ROI = (0.310, 0.115, 0.300, 0.070)
SLOT_RE = re.compile(r"\((\d)\)")


def crop_norm(img, roi):
    h, w = img.shape[:2]
    return img[int(roi[1]*h):int((roi[1]+roi[3])*h), int(roi[0]*w):int((roi[0]+roi[2])*w)]


def main():
    ocr = TesseractBackend(tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    ok = 0
    fail = 0
    for slot in range(1, 7):
        for variant in [1, 2]:
            p = SLOT_FOLDER / f"Ejemplo_Slot{slot}_{variant}.png"
            if not p.exists():
                continue
            img = cv2.imread(str(p))
            crop = crop_norm(img, TITLE_ROI)
            text, conf = ocr.text(crop, psm=6, lang="spa")
            m = SLOT_RE.search(text)
            detected = int(m.group(1)) if m else None
            ok_marker = "OK  " if detected == slot else "FAIL"
            (ok := ok + 1) if detected == slot else (fail := fail + 1)
            print(f"  [{ok_marker}] Slot{slot}_{variant}: esperado={slot} detectado={detected} | text={text!r} (conf {conf:.2f})")

    print(f"\nResumen: {ok}/{ok+fail} correctos")


if __name__ == "__main__":
    main()


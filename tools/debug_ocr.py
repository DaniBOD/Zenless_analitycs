"""
Debug del OCR: toma un screenshot, recorta un ROI conocido y muestra
qué texto extrae Tesseract con distintas configuraciones.

Uso:
    python tools/debug_ocr.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import cv2
import numpy as np
import pytesseract

# Ubicación binario tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def load_img(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def crop_roi(img: np.ndarray, roi: list[float]) -> np.ndarray:
    h, w = img.shape[:2]
    x = int(roi[0] * w); y = int(roi[1] * h)
    rw = int(roi[2] * w); rh = int(roi[3] * h)
    return img[y:y + rh, x:x + rw]


def try_ocr(name: str, img: np.ndarray, lang: str = "spa"):
    """Prueba múltiples PSMs y reporta."""
    print(f"\n--- {name} ({img.shape[1]}x{img.shape[0]}) ---")

    # Guardar para inspección visual
    out_dir = REPO / "audit" / "debug_ocr_crops"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / f"{name}.png"
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(str(save_path))

    # Variante 1: imagen original BGR → grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("  [gray]")
    for psm in [6, 7, 8, 11, 12]:
        try:
            txt = pytesseract.image_to_string(gray, lang=lang, config=f"--psm {psm} --oem 3").strip()
            txt_safe = txt[:60].replace("\n", " | ")
            print(f"    psm={psm}: {txt_safe!r}")
        except Exception as e:
            print(f"    psm={psm}: ERROR {e}")

    # Variante 2: upscale 2x + grayscale
    h, w = gray.shape
    gray_2x = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    save_path_2x = out_dir / f"{name}_2x.png"
    ok, buf = cv2.imencode(".png", gray_2x)
    if ok:
        buf.tofile(str(save_path_2x))
    print("  [gray 2x]")
    for psm in [6, 7]:
        txt = pytesseract.image_to_string(gray_2x, lang=lang, config=f"--psm {psm} --oem 3").strip()
        print(f"    psm={psm}: {txt[:60].replace(chr(10), ' | ')!r}")

    # Variante 3: invertir (texto blanco sobre negro → texto negro sobre blanco)
    inverted = cv2.bitwise_not(gray)
    save_path_inv = out_dir / f"{name}_inv.png"
    ok, buf = cv2.imencode(".png", inverted)
    if ok:
        buf.tofile(str(save_path_inv))
    print("  [inverted (texto negro sobre blanco)]")
    for psm in [6, 7]:
        txt = pytesseract.image_to_string(inverted, lang=lang, config=f"--psm {psm} --oem 3").strip()
        print(f"    psm={psm}: {txt[:60].replace(chr(10), ' | ')!r}")

    # Variante 4: invertido + upscale 2x
    inverted_2x = cv2.resize(inverted, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    save_path_inv2x = out_dir / f"{name}_inv2x.png"
    ok, buf = cv2.imencode(".png", inverted_2x)
    if ok:
        buf.tofile(str(save_path_inv2x))
    print("  [inverted 2x]")
    for psm in [6, 7]:
        txt = pytesseract.image_to_string(inverted_2x, lang=lang, config=f"--psm {psm} --oem 3").strip()
        print(f"    psm={psm}: {txt[:60].replace(chr(10), ' | ')!r}")

    # Variante 5: threshold Otsu sobre invertido
    _, otsu = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    save_path_otsu = out_dir / f"{name}_otsu.png"
    ok, buf = cv2.imencode(".png", otsu)
    if ok:
        buf.tofile(str(save_path_otsu))
    print("  [otsu sobre invertido]")
    for psm in [6, 7]:
        txt = pytesseract.image_to_string(otsu, lang=lang, config=f"--psm {psm} --oem 3").strip()
        print(f"    psm={psm}: {txt[:60].replace(chr(10), ' | ')!r}")


def main():
    import tomllib

    s3_img = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "02_Detalle_Disco_Desde_Resultado" / "Ejemplo_1.png"
    img = load_img(s3_img)
    print(f"Imagen S3 (Ejemplo_1.png): {img.shape[1]}x{img.shape[0]}")

    # Cargar ROIs
    with open(REPO / "app" / "config" / "rois.toml", "rb") as f:
        rois = tomllib.load(f)

    section = rois["modal_detalle_s3"]

    # Probar título (debería decir "Fábula Yunkui (1)")
    titulo = crop_roi(img, section["titulo"])
    try_ocr("S3_titulo_esperado_FabulaYunkui1", titulo)

    # Mainstat nombre (debería decir "PV")
    main_n = crop_roi(img, section["main_stat_nombre"])
    try_ocr("S3_mainstat_nombre_esperado_PV", main_n)

    # Mainstat valor (debería decir "550")
    main_v = crop_roi(img, section["main_stat_valor"])
    try_ocr("S3_mainstat_valor_esperado_550", main_v)

    # Sub1 nombre (debería decir "Ataque")
    sub1_n = crop_roi(img, section["sub1_nombre"])
    try_ocr("S3_sub1_nombre_esperado_Ataque", sub1_n)

    print(f"\n\nCrops guardados en audit\\debug_ocr_crops\\")


if __name__ == "__main__":
    main()

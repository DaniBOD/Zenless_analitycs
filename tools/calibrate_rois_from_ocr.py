"""
Calibración inversa de ROIs: ejecuta OCR full-image y muestra las coordenadas
REALES (normalizadas) donde Tesseract detecta cada palabra. Permite verificar
si los ROIs en rois.toml apuntan a las posiciones correctas.

Uso:
    python tools/calibrate_rois_from_ocr.py <ruta-screenshot>

Ejemplo:
    python tools/calibrate_rois_from_ocr.py Documentacion/Screenshots_Triggers/Discos_Triggers/02_Detalle_Disco_Desde_Resultado/Ejemplo_1.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

REPO = Path(__file__).resolve().parent.parent


def load_img(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def main():
    if len(sys.argv) < 2:
        # Default a Ejemplo_1.png de S3
        img_path = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "02_Detalle_Disco_Desde_Resultado" / "Ejemplo_1.png"
    else:
        img_path = Path(sys.argv[1])

    if not img_path.exists():
        print(f"ERROR: no existe {img_path}")
        sys.exit(1)

    img = load_img(img_path)
    h, w = img.shape[:2]
    print(f"Imagen: {img_path.name} ({w}x{h})")
    print()

    # OCR full-image con sparse text + español
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Upscale x1.5 para mejor accuracy
    gray_up = cv2.resize(gray, (int(w * 1.5), int(h * 1.5)), interpolation=cv2.INTER_CUBIC)

    config = "--psm 11 --oem 3"
    data = pytesseract.image_to_data(
        gray_up, lang="spa", config=config,
        output_type=pytesseract.Output.DICT,
    )

    print(f"{'TEXTO':<25} {'conf':>5}  {'x_norm':>7} {'y_norm':>7} {'w_norm':>7} {'h_norm':>7}  pixels")
    print("-" * 110)

    interesting_words = []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        conf = int(data["conf"][i])
        if not txt or conf < 0:
            continue
        # Filtrar palabras muy chicas / ruido
        if len(txt) < 2 and not txt.isdigit():
            continue
        # Coordenadas del bounding box (en imagen upscaled)
        x_px = data["left"][i]
        y_px = data["top"][i]
        w_px = data["width"][i]
        h_px = data["height"][i]
        # Convertir a normalizadas respecto a imagen ORIGINAL (de-upscale)
        # gray_up = imagen * 1.5, así que dividimos por 1.5*size_original
        x_norm = (x_px / 1.5) / w
        y_norm = (y_px / 1.5) / h
        w_norm = (w_px / 1.5) / w
        h_norm = (h_px / 1.5) / h

        print(f"  {txt[:23]:<23}  {conf:>3}%  {x_norm:>7.4f} {y_norm:>7.4f} {w_norm:>7.4f} {h_norm:>7.4f}  ({int(x_px/1.5)},{int(y_px/1.5)},{int(w_px/1.5)}x{int(h_px/1.5)})")
        interesting_words.append((txt, x_norm, y_norm, w_norm, h_norm, conf))

    print()
    print(f"Total palabras detectadas: {len(interesting_words)}")
    print()
    print("Sugerencias de ROIs para rois.toml:")

    # Buscar palabras clave del modal de disco
    keywords = {
        "Fábula": "titulo",
        "Yunkui": "titulo (continuación)",
        "Nana": "titulo",
        "Jazz": "titulo",
        "Nivel": "nivel",
        "PV": "main_stat_nombre",
        "Ataque": "main_stat_nombre o sub1_nombre",
        "Defensa": "sub_*_nombre",
        "Crítico": "sub_*_nombre",
        "Daño": "sub_*_nombre",
        "Perforación": "sub_*_nombre",
        "Maestría": "sub_*_nombre",
        "Anomalía": "sub_*_nombre (parte)",
    }
    for txt, x, y, w_, h_, conf in interesting_words:
        for kw, hint in keywords.items():
            if kw in txt:
                print(f"  → {txt!r} (likely {hint}): [{x:.3f}, {y:.3f}, {w_:.3f}, {h_:.3f}]")


if __name__ == "__main__":
    main()

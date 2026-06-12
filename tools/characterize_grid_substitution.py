"""Hito 5.0 — Caracterización (READ-ONLY) del flujo grilla/sustitución.

NO escribe DB ni nada persistente. Solo mide, sobre los screenshots de ejemplo:
  1. Qué estado da el detector (raw template+verify, y classify completo).
  2. La señal de "grilla de candidatos a la IZQUIERDA" (densidad de bordes en
     x∈[0.02,0.20]) que debería separar el modo-grilla del detalle-por-hexágono.
  3. Para el modal de sustitución (15_): el banner central oscuro (banda de baja
     varianza horizontal en y≈0.45-0.62) como firma del modal.

Uso:  .venv\\Scripts\\python.exe tools\\characterize_grid_substitution.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.detector import ScreenDetector, STATE_DESCRIPTIONS  # noqa: E402

SHOTS_DIR = ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"

# (etiqueta, ruta relativa, lo que esperamos que sea)
SHOTS = [
    ("grid/Nangong Blues(1)",  "04_Inventario_Disco_Vista_Individual/Ejemplo_11_nangong.png", "grilla, candidato NO equipado"),
    ("grid/Nangong Voz(5)",    "04_Inventario_Disco_Vista_Individual/Ejemplo_12_nangong.png", "grilla, candidato equipado x otro"),
    ("grid/Lucia 13",          "04_Inventario_Disco_Vista_Individual/Ejemplo_13_Lucia.png",   "grilla"),
    ("grid/Lucia 14",          "04_Inventario_Disco_Vista_Individual/Ejemplo_14_Lucia.png",   "grilla"),
    ("inv/Ejemplo_1",          "04_Inventario_Disco_Vista_Individual/Ejemplo_1.png",          "inventario indiv?"),
    ("inv/Ejemplo_8",          "04_Inventario_Disco_Vista_Individual/Ejemplo_8.png",          "inventario indiv?"),
    ("inv/Ejemplo_9",          "04_Inventario_Disco_Vista_Individual/Ejemplo_9.png",          "inventario indiv?"),
    ("inv/Ejemplo_10",         "04_Inventario_Disco_Vista_Individual/Ejemplo_10.png",         "titulo 2 lineas"),
    ("subst/Ejemplo_1",        "15_sustitucion_disco_confirmacion/Ejemplo_1.png",             "modal sustitucion"),
    ("subst/Ejemplo_2",        "15_sustitucion_disco_confirmacion/Ejemplo_2.png",             "modal sustitucion"),
    ("subst/Ejemplo_3",        "15_sustitucion_disco_confirmacion/Ejemplo_3.png",             "modal sustitucion"),
    ("subst/Ejemplo_4",        "15_sustitucion_disco_confirmacion/Ejemplo_4.png",             "modal sustitucion"),
    ("subst/Ejemplo_5",        "15_sustitucion_disco_confirmacion/Ejemplo_5.png",             "modal sustitucion"),
    ("subst/Ejemplo_6",        "15_sustitucion_disco_confirmacion/Ejemplo_6.png",             "modal sustitucion"),
    ("subst/Ejemplo_7",        "15_sustitucion_disco_confirmacion/Ejemplo_7.png",             "modal sustitucion"),
    # Referencia: S17 puro por hexágono (sin grilla) para contraste del control.
    ("ref/Slot1_1",            "14_Slots_equipamiento/Ejemplo_Slot1_1.png",                   "S17 puro (control)"),
    ("ref/Slot4_1",            "14_Slots_equipamiento/Ejemplo_Slot4_1.png",                   "S17 puro (control)"),
]


def left_grid_edge_frac(frame: np.ndarray) -> float:
    """Densidad de bordes (Canny) en la columna izquierda x∈[0.02,0.20],
    y∈[0.12,0.95]. Alta = grilla de thumbnails; baja = fondo liso (S17 puro)."""
    h, w = frame.shape[:2]
    x0, x1 = int(0.02 * w), int(0.20 * w)
    y0, y1 = int(0.12 * h), int(0.95 * h)
    band = frame[y0:y1, x0:x1]
    if band.size == 0:
        return 0.0
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return float((edges > 0).mean())


def center_banner_darkband(frame: np.ndarray) -> float:
    """Firma del modal de sustitución: una banda horizontal central (y≈0.45-0.62)
    muy oscura y uniforme sobre todo el ancho. Devuelve la fracción de filas de esa
    banda cuyo brillo medio < 60 (modal oscurece el fondo + banner negro)."""
    h, w = frame.shape[:2]
    y0, y1 = int(0.44 * h), int(0.63 * h)
    band = frame[y0:y1, :]
    if band.size == 0:
        return 0.0
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    row_means = gray.mean(axis=1)
    return float((row_means < 60).mean())


def main() -> int:
    det = ScreenDetector()
    print(f"Detector OK · {det.loaded_count} templates\n")
    hdr = f"{'etiqueta':<22} {'raw':<5} {'classify':<9} {'L-grid':>7} {'dark-band':>9}  esperado"
    print(hdr)
    print("-" * len(hdr))
    for label, rel, expected in SHOTS:
        p = SHOTS_DIR / rel
        if not p.exists():
            print(f"{label:<22} {'--':<5} {'--':<9} {'--':>7} {'--':>9}  (FALTA {rel})")
            continue
        frame = cv2.imread(str(p))
        if frame is None:
            print(f"{label:<22} (no se pudo leer)")
            continue
        raw = det._verify(det._template_match(frame), frame)
        full = det.classify(frame)
        lg = left_grid_edge_frac(frame)
        db = center_banner_darkband(frame)
        print(f"{label:<22} {raw.code:<5} {full.code:<9} {lg:>7.3f} {db:>9.3f}  {expected}")
    print("\nLeyenda: raw = template+verify (sin state-machine); classify = pipeline completo.")
    print("L-grid alto ⇒ grilla de candidatos; dark-band alto ⇒ modal de sustitución.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
tools/calibrate_rois_s18.py — utilidad para validar ROIs S18 contra fixtures reales.

Carga las ROIs actuales de rois.toml, las dibuja encima de cada fixture
atributos_base_ejemplo_N.png, y corre Tesseract sobre cada crop para
mostrar qué texto extrae. Permite ajustar las ROIs iterativamente hasta
que los valores leídos coincidan con los esperados.

Uso:
  python tools/calibrate_rois_s18.py                # imprime resultados
  python tools/calibrate_rois_s18.py --save out.png # dibuja overlay
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.ocr_tesseract import TesseractBackend  # noqa: E402

ROIS_PATH = ROOT / "app" / "config" / "rois.toml"
FIXTURES = sorted((ROOT / "app" / "tests" / "fixtures").glob("atributos_base_ejemplo_*.png"))

KEYS = [
    "agent_info",
    "nivel_nombre", "nivel_valor",
    "pv_nombre", "pv_valor",
    "defensa_nombre", "defensa_valor",
    "prob_crit_nombre", "prob_crit_valor",
    "tasa_anomalia_nombre", "tasa_anomalia_valor",
    "tasa_perforacion_nombre", "tasa_perforacion_valor",
    "ataque_nombre", "ataque_valor",
    "impacto_nombre", "impacto_valor",
    "dano_crit_nombre", "dano_crit_valor",
    "maestria_anomalia_nombre", "maestria_anomalia_valor",
    "recup_energia_nombre", "recup_energia_valor",
]


def load_rois() -> dict[str, list[float]]:
    with open(ROIS_PATH, "rb") as f:
        return tomllib.load(f)["perfil_agente_atributos"]


def crop(img: np.ndarray, roi: list[float]) -> np.ndarray:
    h, w = img.shape[:2]
    x, y, rw, rh = roi
    return img[int(y*h):int((y+rh)*h), int(x*w):int((x+rw)*w)]


def run_ocr_on_fixture(fixture: Path, rois: dict, ocr: TesseractBackend) -> dict[str, str]:
    data = np.fromfile(str(fixture), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    results = {}
    for key in KEYS:
        if key not in rois:
            results[key] = "<MISSING_ROI>"
            continue
        crop_img = crop(img, rois[key])
        if crop_img.size < 100:
            results[key] = "<EMPTY_CROP>"
            continue
        try:
            text, conf = ocr.text(crop_img, psm=7)
            results[key] = f"{text!r} (conf={conf:.2f})"
        except Exception as e:
            results[key] = f"<ERROR: {e}>"
    return results


def draw_overlay(fixture: Path, rois: dict, save_to: Path) -> None:
    data = np.fromfile(str(fixture), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    for key in KEYS:
        if key not in rois:
            continue
        x, y, rw, rh = rois[key]
        x1, y1 = int(x * w), int(y * h)
        x2, y2 = int((x + rw) * w), int((y + rh) * h)
        color = (0, 255, 0) if "_valor" in key else (0, 255, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, key, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    cv2.imencode(".png", img)[1].tofile(str(save_to))
    print(f"Overlay guardado en {save_to}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", type=Path, help="Path para guardar overlay PNG")
    parser.add_argument("--fixture", type=int, default=1, help="Número de fixture (1-7)")
    args = parser.parse_args()

    if not FIXTURES:
        print("ERROR: no se encontraron fixtures en app/tests/fixtures/")
        sys.exit(1)

    rois = load_rois()
    fixture = FIXTURES[args.fixture - 1]
    print(f"Fixture: {fixture.name}")
    print(f"ROIs cargadas: {len(rois)}\n")

    if args.save:
        draw_overlay(fixture, rois, args.save)

    print("OCR Tesseract por ROI:")
    print("-" * 80)
    ocr = TesseractBackend()
    results = run_ocr_on_fixture(fixture, rois, ocr)
    for key, val in results.items():
        marker = " OK " if val and "''" not in val and "<" not in val else " ?? "
        print(f"  {key:30s} {marker} {val}")


if __name__ == "__main__":
    main()

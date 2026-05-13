"""Tests de regresión — FPs conocidos que NO deben clasificarse como capturables."""
import sys
from pathlib import Path
import cv2
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.detector import ScreenDetector, CAPTURE_DISC_STATES


FP_SCREENSHOTS = [
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Dispara_disco_descarte.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_1.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_2.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_3.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_4.png",
]

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("rel_path", FP_SCREENSHOTS)
def test_fp_no_capture(rel_path):
    """Ningún FP screenshot debe clasificarse como estado capturable."""
    path = REPO / rel_path
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")

    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")

    detector = ScreenDetector()
    state = detector.classify(img)

    assert state.code not in CAPTURE_DISC_STATES, (
        f"FP {rel_path} clasificado como {state.code} (conf={state.confidence:.3f}, "
        f"tmpl={state.template_name}) — debe ser NO capturable"
    )
    assert state.code != "S12" or state.template_name != "", (
        f"FP {rel_path} debe tener template_name informativo aunque sea S12"
    )


def test_dark_frame_filter_detects_fp_screenshot():
    """Verificar que el filtro de frame oscuro detecta correctamente el FP conocido."""
    path = REPO / FP_SCREENSHOTS[0]
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")

    img = cv2.imread(str(path))
    assert bool(ScreenDetector._is_dark_frame(img)), (
        "El FP screenshot debe ser detectado como frame oscuro"
    )

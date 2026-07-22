"""
Tests de `read_s17_action_button` — la SEGUNDA señal del feature "disco libre equipado"
(2026-07-22). Corren sobre capturas REALES del juego, no sobre fakes: el valor de esta
lectura está en que aísla el botón del medio por posición, y eso solo se prueba con el
layout de verdad.

Recordatorio de semántica (corrección de Daniel): el botón NO habla del disco, habla del
SLOT DESTINO. 'Equipar' = el PJ tiene ese slot vacío; 'Reemplazar' = ya tiene uno ahí y
habrá un desplazado; 'Desequipar' = el disco ya lo lleva puesto este PJ.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from app.core.parser_disc_s17 import read_s17_action_button

REPO_ROOT = Path(__file__).resolve().parents[3]
TRIGGERS = REPO_ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
LIBRES = TRIGGERS / "17_Inventario_Disco_Vista_Individual_libres"
OCUPADOS = TRIGGERS / "04_Inventario_Disco_Vista_Individual"


@pytest.fixture(scope="module")
def ocr():
    paddle = pytest.importorskip("paddleocr", reason="PaddleOCR no instalado")  # noqa: F841
    from app.core.ocr_paddle import PaddleBackend
    return PaddleBackend()


def _frame(path: Path):
    if not path.exists():
        pytest.skip(f"Fixture ausente: {path}")
    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")
    return img


@pytest.mark.parametrize("nombre,esperado", [
    ("Ejemplo_2_(equipar).png", "equipar"),
    ("Ejemplo_4_(equipar).png", "equipar"),
    ("Ejemplo_1_(reemplazar).png", "reemplazar"),
    ("Ejemplo_3_(reemplazar).png", "reemplazar"),
])
def test_lee_el_boton_en_discos_libres(ocr, nombre, esperado):
    assert read_s17_action_button(_frame(LIBRES / nombre), ocr) == esperado


def test_lee_desequipar_en_un_disco_ya_equipado(ocr):
    assert read_s17_action_button(_frame(OCUPADOS / "Ejemplo_1.png"), ocr) == "desequipar"


def test_el_desequipar_rapido_no_se_cuela(ocr):
    """REGRESIÓN: 'Desequipar rápido' es OTRO botón (cx_norm 0.639) y aporta un 'desequipar'
    fantasma. Si se eligiera por presencia del texto en vez de por posición, TODO disco libre
    leería 'desequipar' → el check daría por equipado algo que nunca se equipó."""
    assert read_s17_action_button(_frame(LIBRES / "Ejemplo_2_(equipar).png"), ocr) != "desequipar"


def test_frame_vacio_o_none_devuelve_none(ocr):
    import numpy as np
    assert read_s17_action_button(None, ocr) is None
    assert read_s17_action_button(np.zeros((0, 0, 3), np.uint8), ocr) is None


def test_ocr_que_explota_no_propaga(ocr):
    """Ante un backend roto, abstenerse (None) — nunca romper el ciclo del monitor."""
    import numpy as np

    class _OcrRoto:
        def text_with_bboxes(self, img):
            raise RuntimeError("boom")

    frame = np.zeros((1439, 2557, 3), np.uint8)
    assert read_s17_action_button(frame, _OcrRoto()) is None


def test_elige_por_posicion_no_por_orden():
    """Con un OCR falso que devuelve los 3 botones, debe quedarse con el del CENTRO
    (cx_norm≈0.772) sin importar en qué orden vengan las líneas."""
    import numpy as np
    W, H = 2557, 1439
    x0 = int(0.55 * W)

    def _bb(cx_norm):
        cx = cx_norm * W - x0
        return (int(cx - 40), 10, int(cx + 40), 40)

    class _OcrFijo:
        def text_with_bboxes(self, img):
            return [
                ("Mejorar", 1.0, _bb(0.905)),
                ("Desequipar", 1.0, _bb(0.639)),   # el "rápido", debe ignorarse
                ("Equipar", 1.0, _bb(0.772)),      # el de acción
            ]

    frame = np.zeros((H, W, 3), np.uint8)
    assert read_s17_action_button(frame, _OcrFijo()) == "equipar"

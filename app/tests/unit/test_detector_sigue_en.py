"""`ScreenDetector.sigue_en`: el atajo "sigue en la misma pantalla" (hito "El ritmo de Daniel", fase 2).

Re-matchea sólo el template del estado confirmado donde lo encontró la última clasificación completa.
Lo que tiene que cumplir, con capturas reales del desmontaje (2559×1439, mismo tamaño entre sí):
  - una S11 sigue siendo S11;
  - con el diálogo de confirmación (S25) o el "Obtenido" (S24) encima, NO sigue (medido sobre la
    grabación 20261003_111858: 0 frames de otra pantalla pasan);
  - sin ubicación aprendida, con otra resolución o para un estado fuera de la lista: None.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ESTADOS_QUE_SIGUEN, ScreenDetector

DIR = Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "12_Desmontaje"


def _cargar(nombre: str) -> np.ndarray:
    ruta = DIR / nombre
    if not ruta.exists():
        pytest.skip(f"falta la captura {nombre}")
    return cv2.imdecode(np.fromfile(str(ruta), np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def det_s11():
    """Un detector que ya clasificó una S11 completa (así aprendió dónde está su template)."""
    det = ScreenDetector(use_state_machine=False)
    st = det.classify(_cargar("Ejemplo_2.png"))
    assert st.code == "S11"
    return det


def test_una_s11_sigue_siendo_s11(det_s11):
    st = det_s11.sigue_en("S11", _cargar("Ejemplo_3.png"))
    assert st is not None and st.code == "S11" and st.method == "sigue"


def test_con_la_confirmacion_encima_no_sigue(det_s11):
    assert det_s11.sigue_en("S11", _cargar("Ejemplo_8_(Confirmacion).png")) is None


def test_con_el_obtenido_encima_no_sigue(det_s11):
    assert det_s11.sigue_en("S11", _cargar("Ejemplo_7_(Post_demontaje).png")) is None


def test_sin_ubicacion_aprendida_no_afirma_nada():
    det = ScreenDetector(use_state_machine=False)
    assert det.sigue_en("S11", _cargar("Ejemplo_3.png")) is None


def test_otra_resolucion_no_usa_la_ubicacion_vieja(det_s11):
    frame = _cargar("Ejemplo_3.png")
    otro = cv2.copyMakeBorder(frame, 0, 1, 0, 1, cv2.BORDER_REPLICATE)
    assert det_s11.sigue_en("S11", otro) is None


def test_un_estado_fuera_de_la_lista_no_toma_el_atajo():
    """S25 comparte template con S23/S29: se desambigua por verificación en `classify`. Aunque el
    detector ya sepa dónde está su template, el atajo no se toma."""
    det = ScreenDetector(use_state_machine=False)
    confirmacion = _cargar("Ejemplo_8_(Confirmacion).png")
    assert det.classify(confirmacion).code == "S25"
    assert "S25" not in ESTADOS_QUE_SIGUEN
    assert det.sigue_en("S25", confirmacion) is None


def test_clasificar_completo_sigue_dando_lo_mismo(det_s11):
    """Aprender ubicaciones no cambia lo que contesta `classify`."""
    assert det_s11.classify(_cargar("Ejemplo_8_(Confirmacion).png")).code == "S25"
    assert det_s11.classify(_cargar("Ejemplo_3.png")).code == "S11"

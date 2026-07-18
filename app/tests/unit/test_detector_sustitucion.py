"""Detección del diálogo de sustitución de disco entre PJs (S23).

En el juego, al equipar en un PJ un disco que otro ya tiene, aparece un modal:
"{PJ} equipa actualmente {set} ({slot}). ¿Deseas sustituirlo?" con botones Cancelar/Confirmar.

El template es la fila de botones (invariante entre swaps), pero "Cancelar/Confirmar" es genérico
de ZZZ → `_verify_s23` confirma por OCR el texto exclusivo "sustituirlo"/"equipa actualmente".
Los negativos importan: ningún otro diálogo de confirmación debe clasificar como S23.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenDetector

_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Discos_Triggers" / "15_sustitucion_disco_confirmacion")
_S23_FX = sorted(_FX.glob("Ejemplo_*.png"))
_FP_DIR = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
           / "Triggers_Generales" / "Falsos_positivos")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not _S23_FX, reason="capturas S23 no presentes")
@pytest.mark.parametrize("fx", _S23_FX, ids=lambda p: p.name)
def test_dialogo_de_sustitucion_es_s23(fx):
    """Los 7 fixtures del diálogo → S23 (template de botones + verify de texto)."""
    st = ScreenDetector().classify(_load(fx))
    assert st.code == "S23", f"{fx.name} → {st.code} (conf={st.confidence:.2f}, verif={st.verification})"


@pytest.mark.skipif(not _S23_FX, reason="capturas S23 no presentes")
def test_verify_confirma_el_texto_sustituir():
    """La verificación secundaria debe apoyarse en el texto del diálogo, no solo en los botones."""
    st = ScreenDetector(use_state_machine=False).classify(_load(_S23_FX[0]))
    assert st.verification and "sustituir" in st.verification


@pytest.mark.skipif(not _FP_DIR.exists(), reason="corpus de negativos no presente")
def test_los_negativos_no_disparan_s23():
    """Ninguna de las pantallas del corpus de falsos positivos debe clasificar como S23
    (el template de botones no matchea a ≥0.85, y aun matcheando `_verify_s23` lo bloquea)."""
    det = ScreenDetector(use_state_machine=False)
    for f in sorted(_FP_DIR.glob("*.png")):
        img = _load(f)
        if img is None:
            continue
        assert det.classify(img).code != "S23", f"{f.name} disparó S23 (FP)"


def test_s23_registrado_en_el_detector():
    """Guardas de registro: threshold, transiciones (entra desde S8/S17, sale al flujo de
    equipamiento), descripción y no-captura."""
    from app.core.detector import (
        THRESHOLD_BY_STATE, _VALID_TRANSITIONS, STATE_DESCRIPTIONS, NON_CAPTURE_STATES,
        _VERIFICATION_REGISTRY,
    )
    assert THRESHOLD_BY_STATE["S23"] == 0.85
    assert "S23" in NON_CAPTURE_STATES
    assert "S23" in STATE_DESCRIPTIONS
    assert "S23" in _VERIFICATION_REGISTRY
    assert "S23" in _VALID_TRANSITIONS["S17"] and "S23" in _VALID_TRANSITIONS["S8"]
    assert _VALID_TRANSITIONS["S23"] >= {"S17", "S8", "S12"}

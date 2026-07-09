"""Detección de las pantallas de la tienda de música de Orphie ("Plan de entrenamiento").

S4 (selector de set a evocar) comparte el chrome "Plan de entrenamiento" con S15 (menú de
personajes) → el template de S15 lo eclipsa (0.96) y S4 no tiene template propio. Se
desambigua por AUSENCIA de la grilla de retratos coloridos en el ROI del gramófono: S4 es
el gramófono metálico oscuro (colorful ≤0.014), S15 son retratos de agentes (colorful ≥0.184).

S5 (resultado de afinación) tiene template propio pero es frágil (una de las 2 capturas se
escapaba a S12) → se endurece en Fase B.

Fixtures reales; sin OCR (RNF-06). Cada test usa un detector fresco (la state-machine no
afecta por ser no-estricta, pero así es determinista)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenDetector

REPO = Path(__file__).resolve().parents[3]
_TRG = REPO / "Documentacion" / "Screenshots_Triggers"
_S4 = _TRG / "Discos_Triggers" / "18_Seleccion_set_farmeo_tienda_musica"
_S15 = _TRG / "Triggers_Generales" / "Menu_Personajes"
_S5 = _TRG / "Discos_Triggers" / "11_Tienda_Musica_Afinacion"

_S4_FX = sorted(_S4.glob("Ejemplo_*.png"))
_S15_FX = sorted(_S15.glob("Ejemplo_*.png"))
_S5_FX = sorted(_S5.glob("*.png"))


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not _S4_FX, reason="capturas S4 no presentes")
@pytest.mark.parametrize("fx", _S4_FX, ids=lambda p: p.name)
def test_selector_tienda_musica_es_s4(fx):
    """Las 9 capturas del selector (folder 18) → S4 (antes eclipsadas a S15)."""
    assert ScreenDetector().classify(_load(fx)).code == "S4"


@pytest.mark.skipif(not _S15_FX, reason="capturas S15 no presentes")
@pytest.mark.parametrize("fx", _S15_FX, ids=lambda p: p.name)
def test_menu_personajes_sigue_s15(fx):
    """El menú de personajes real (grilla de retratos) NO se degrada a S4 (no regresión)."""
    assert ScreenDetector().classify(_load(fx)).code == "S15"


@pytest.mark.skipif(not _S5_FX, reason="capturas S5 no presentes")
@pytest.mark.parametrize("fx", _S5_FX, ids=lambda p: p.name)
def test_resultado_afinacion_es_s5(fx):
    """Ambas capturas del resultado de afinación (folder 11) → S5. La 2ª (disco (4) seleccionado)
    se escapaba a S12 con el template ancho del top; el template TIGHT del header lo fija."""
    assert ScreenDetector().classify(_load(fx)).code == "S5"

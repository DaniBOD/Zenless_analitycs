"""Detección del popup 'Materiales recuperados' (S20) — vuelto de sobrantes al MAXEAR un disco.

Aparece entre S10 (modal upgrade) y S17 (inventario), exige click manual de Confirmar → demora
la S17. Antes caía a S12 ('no reconocida') y, además de ensuciar el log, no había ancla para
sostener el pendiente PRE→POST. El template apunta al título centrado (único de este popup).

Fixtures reales 2559×1439; sin OCR (RNF-06). Detector fresco por test (state-machine no-estricta)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenDetector

REPO = Path(__file__).resolve().parents[3]
_UP = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "07_Upgrade_POST_animacion_confirmacion"

_REFUND = _UP / "Ejemplo_1(vuelto_materiales).png"
# NON-S20 del mismo folder: no deben clasificar como S20 (evita FP en el flujo de upgrade).
_NON_S20 = [
    _UP / "Ejemplo_1(detallado).png",
    _UP / "Ejemplo_1(pre-15-max).png",
    _UP / "Ejemplo_2(pre-15-max).png",
    _UP / "Ejemplo_3(pre-15-max).png",
]


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not _REFUND.exists(), reason="captura vuelto de materiales no presente")
def test_popup_vuelto_materiales_es_s20():
    assert ScreenDetector().classify(_load(_REFUND)).code == "S20"


@pytest.mark.parametrize("fx", _NON_S20, ids=lambda p: p.name)
def test_pantallas_upgrade_no_son_s20(fx):
    if not fx.exists():
        pytest.skip(f"no presente: {fx.name}")
    assert ScreenDetector().classify(_load(fx)).code != "S20"

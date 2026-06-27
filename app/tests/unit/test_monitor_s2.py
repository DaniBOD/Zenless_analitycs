"""Handler de RESULTADOS de farmeo (S2) en el monitor (`_process_s2_resultado`).

S2 es display-only: detecta discos tier S en la grilla (`parse_s2_resultado`) y emite un
resumen por diagnóstico, con el contexto de confianza dado por `FarmSession` (flujo
S13→S14→S2 = farmeo real vs otro "resultado de desafío"). No persiste ni puntúa (eso es S3).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S2 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "01_Pantalla_Resultado_Desafio"


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _monitor(on_diagnostic, farm_session=None):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    return mon.Monitor(ocr=_paddle(), detector=None,
                       on_diagnostic=on_diagnostic,
                       farm_session=farm_session if farm_session is not None else FarmSession())


@pytest.mark.skipif(not (_S2 / "Ejemplo_1.png").exists(), reason="capturas S2 no presentes")
def test_s2_resumen_contexto_flujo():
    """Tras pasar por S13 (set-select), el S2 se reporta con contexto=flujo (alta confianza)."""
    from app.core.detector import ScreenState
    diags = []
    m = _monitor(on_diagnostic=lambda msg: diags.append(msg))
    dummy = np.zeros((1439, 2559, 3), dtype=np.uint8)
    m._dispatch_state(dummy, ScreenState("S13", 1.0, "s13_set"))          # arma la sesión
    fr = cv2.imdecode(np.fromfile(str(_S2 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S2", 1.0, "s2_resultado"))
    farmeo = [d for d in diags if "farmeo" in d.lower()]
    assert farmeo, f"esperaba un resumen de farmeo, diags={diags}"
    assert "flujo" in farmeo[-1].lower()


@pytest.mark.skipif(not (_S2 / "Ejemplo_1.png").exists(), reason="capturas S2 no presentes")
def test_s2_resumen_tentativo_sin_flujo():
    """Sin S13/S14 previos, el S2 se reporta como tentativo (no hubo contexto de flujo)."""
    from app.core.detector import ScreenState
    diags = []
    m = _monitor(on_diagnostic=lambda msg: diags.append(msg))
    fr = cv2.imdecode(np.fromfile(str(_S2 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S2", 1.0, "s2_resultado"))
    farmeo = [d for d in diags if "farmeo" in d.lower()]
    assert farmeo, f"esperaba un resumen de farmeo, diags={diags}"
    assert "tentativo" in farmeo[-1].lower()


@pytest.mark.skipif(not (_S2 / "Ejemplo_1.png").exists(), reason="capturas S2 no presentes")
def test_s2_reporta_una_sola_vez_por_entrada():
    """El resumen se emite 1× por entrada a S2, no en cada cadencia."""
    from app.core.detector import ScreenState
    diags = []
    m = _monitor(on_diagnostic=lambda msg: diags.append(msg))
    fr = cv2.imdecode(np.fromfile(str(_S2 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S2", 1.0, "s2_resultado")
    m._dispatch_state(fr, st)
    m._dispatch_state(fr, st)
    m._dispatch_state(fr, st)
    farmeo = [d for d in diags if "farmeo" in d.lower()]
    assert len(farmeo) == 1, f"esperaba 1 resumen, hubo {len(farmeo)}: {farmeo}"

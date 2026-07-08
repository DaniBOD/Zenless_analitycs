"""Detalle por disco en S2 (`_process_s2_resultado` → `_process_s2_tiles`) — Fase B.

Además del resumen S-only, cuando hay una predicción de S13 vigente el monitor itera los tiles
de la grilla y emite una línea display-only por disco: slot (OCR) + set (matcher restringido a
los 2 candidatos predichos). No persiste ni puntúa.

Se inyectan matcher y OCR falsos para testear el WIRING de forma determinista (la precisión del
matcher sobre tiles reales es parte de la QA en vivo).
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.avatar_descriptor import MatchResult
from app.core.detector import ScreenState

REPO = Path(__file__).resolve().parents[3]
_S2 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "01_Pantalla_Resultado_Desafio"


class _FakeOcr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return "1", 0.9   # slot 1 para todos (determinista)


class _FakeMatcher:
    """Devuelve siempre el primer candidato con conf alta."""
    def identify(self, bgr_or_desc, candidate_en):
        if not candidate_en:
            return MatchResult(None, 0.0, 0.0, False, [])
        return MatchResult(candidate_en[0], 0.88, 0.2, False, [])


def _monitor(diags):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    return mon.Monitor(
        ocr=_FakeOcr(), detector=None,
        on_diagnostic=diags.append,
        farm_session=FarmSession(),
        set_badge_matcher=_FakeMatcher(),
    )


@pytest.mark.skipif(not (_S2 / "Ejemplo_1.png").exists(), reason="capturas S2 no presentes")
def test_s2_emite_linea_por_disco_con_prediccion():
    diags: list[str] = []
    m = _monitor(diags)
    # Predicción vigente de S13 (los 2 sets del nodo).
    m._farm_session.set_prediction(
        "El piloto y el meca rebelde",
        [(52, "Wuthering Salon"), (53, "The Sky Ablaze")],
        time.monotonic(),
    )
    fr = cv2.imdecode(np.fromfile(str(_S2 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S2", 1.0, "s2_resultado"))

    discos = [d for d in diags if d.startswith("[disco]")]
    assert len(discos) == 8, f"esperaba 8 líneas de disco, hubo {len(discos)}: {diags}"
    # cada línea trae slot y el set candidato.
    assert all("Wuthering Salon" in d for d in discos)
    assert all("slot 1" in d for d in discos)


@pytest.mark.skipif(not (_S2 / "Ejemplo_1.png").exists(), reason="capturas S2 no presentes")
def test_s2_sin_prediccion_no_emite_por_disco():
    """Sin S13 previo (sin predicción) → no se afirma set por disco (abstención)."""
    diags: list[str] = []
    m = _monitor(diags)
    fr = cv2.imdecode(np.fromfile(str(_S2 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S2", 1.0, "s2_resultado"))
    assert not [d for d in diags if d.startswith("[disco]")]

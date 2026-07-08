"""Handler CONTINUO del modal de drop (S3) en el monitor (`_process_disc_s3_continuous`).

S3 replica el patrón aggregator/maturity de S9/S17 pero sobre el modal centrado del drop: sin
dueño (un drop no está equipado) y sin warmup. Emite vía on_disc cuando el disco madura o tras
el techo de ciclos; el controller lo enruta a `_build_payload` (score + toast). Tests de frame
real (PaddleOCR); se saltean si Paddle o las capturas no están.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S3 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "02_Detalle_Disco_Desde_Resultado"


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _monitor(on_disc):
    import app.core.monitor as mon
    return mon.Monitor(ocr=_paddle(), detector=None, on_disc=on_disc)


def _load(name):
    return cv2.imdecode(np.fromfile(str(_S3 / name), np.uint8), cv2.IMREAD_COLOR)


class _NullOcr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return "", 0.0


def test_s3_reentrada_resetea_captura():
    """Abrir otro disco desde S2 (re-entrar a S3) reinicia la captura AUNQUE la firma sea similar
    (dos discos del mismo set) → cada disco abierto se puede capturar. El dedup por identidad
    evita duplicar. Regresión del checklist de farmeo (QA 2026-07-08)."""
    import app.core.monitor as mon
    from app.core.detector import ScreenState
    m = mon.Monitor(ocr=_NullOcr(), detector=None)
    blank = np.zeros((1439, 2559, 3), np.uint8)
    m._s3_emitted = True                             # simular disco anterior ya emitido
    m._s3_agg_sig = m._s3_disc_signature(blank)      # ancla = misma firma → NO "nuevo" por firma
    m._prev_state_code = "S2"                        # venimos de S2 (abrir otro disco)
    m._dispatch_state(blank, ScreenState("S3", 1.0, "s3_drop"))
    assert m._s3_emitted is False                    # el reset por RE-ENTRADA lo reinició


@pytest.mark.skipif(not (_S3 / "Ejemplo_1.png").exists(), reason="capturas S3 no presentes")
def test_s3_emite_disco_del_drop():
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    m._dispatch_state(_load("Ejemplo_1.png"), ScreenState("S3", 1.0, "s3_drop"))
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    d, st = emitted[0]
    assert st.code == "S3"
    assert d.slot == 1
    assert d.main_stat_canon == "HP"


@pytest.mark.skipif(not (_S3 / "Ejemplo_1.png").exists(), reason="capturas S3 no presentes")
def test_s3_dedup_una_emision_por_drop():
    """El mismo drop (firma estable) emite 1× aunque la cadencia repita el frame."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    fr = _load("Ejemplo_1.png")
    st = ScreenState("S3", 1.0, "s3_drop")
    for _ in range(3):
        m._dispatch_state(fr, st)
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"


@pytest.mark.skipif(not (_S3 / "Ejemplo_1.png").exists() or not (_S3 / "Ejemplo_3.png").exists(),
                    reason="capturas S3 no presentes")
def test_s3_cambio_de_drop_reemite():
    """Cambiar de drop (firma distinta) resetea el aggregator y vuelve a emitir."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    st = ScreenState("S3", 1.0, "s3_drop")
    m._dispatch_state(_load("Ejemplo_1.png"), st)
    m._dispatch_state(_load("Ejemplo_3.png"), st)
    assert len(emitted) == 2, f"esperaba 2 emisiones (distinto disco), hubo {len(emitted)}"
    assert {emitted[0][0].slot, emitted[1][0].slot} == {1, 4}

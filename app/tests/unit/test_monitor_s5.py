"""Handler CONTINUO del resultado de afinación (S5) en el monitor (`_process_disc_s5_continuous`).

S5 replica el patrón aggregator/maturity de S3 sobre la ficha izquierda del resultado de
afinación (el usuario clickea cada disco de la grilla → se re-extrae). Emite vía on_disc al
madurar; dedup por identidad + feedback 'ya capturado'. Tests de frame real (PaddleOCR)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S5 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "11_Tienda_Musica_Afinacion"


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
    return cv2.imdecode(np.fromfile(str(_S5 / name), np.uint8), cv2.IMREAD_COLOR)


class _NullOcr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return "", 0.0

    def text_with_bboxes(self, img):
        return []


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion.png").exists(), reason="capturas S5 no presentes")
def test_s5_emite_disco_afinacion():
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    m._dispatch_state(_load("Tienda_musica_afinacion.png"), ScreenState("S5", 1.0, "s5_afinacion"))
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    d, st = emitted[0]
    assert st.code == "S5"
    assert d.slot == 3
    assert d.main_stat_canon == "DEF"


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion.png").exists(), reason="capturas S5 no presentes")
def test_s5_dedup_una_emision():
    """El mismo disco (firma estable) emite 1× aunque la cadencia repita el frame."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    fr = _load("Tienda_musica_afinacion.png")
    st = ScreenState("S5", 1.0, "s5_afinacion")
    for _ in range(3):
        m._dispatch_state(fr, st)
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_2.png").exists(), reason="capturas S5 no presentes")
def test_s5_cambio_de_disco_reemite():
    """Clickear otro disco de la grilla (firma distinta: slot 3 → 4) resetea y vuelve a emitir."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    st = ScreenState("S5", 1.0, "s5_afinacion")
    m._dispatch_state(_load("Tienda_musica_afinacion.png"), st)
    m._dispatch_state(_load("Tienda_musica_afinacion_2.png"), st)
    assert len(emitted) == 2, f"esperaba 2 emisiones (distinto disco), hubo {len(emitted)}"
    assert {emitted[0].slot, emitted[1].slot} == {3, 4}


def test_s5_no_re_emite_disco_ya_capturado():
    """Re-abrir un disco ya capturado avisa 'ya capturado' y NO re-emite (dedup por identidad)."""
    import app.core.monitor as mon
    from app.core.detector import ScreenState
    import types
    emitted, diags = [], []
    m = mon.Monitor(ocr=_NullOcr(), detector=None,
                    on_disc=lambda d, st: emitted.append(d), on_diagnostic=diags.append)
    st = ScreenState("S5", 1.0, "s5_afinacion")
    sub = types.SimpleNamespace(nombre_canon="DEF%", nombre_raw="DEF%", rolls=0, valor=4.8)
    d = types.SimpleNamespace(
        set_name_canon="Nana a la luz cenicienta", set_name_raw="Nana a la luz cenicienta",
        slot=3, main_stat_canon="DEF", main_stat_raw="DEF", main_valor=46.0, nivel=0,
        confianza_global=0.9, subs=[sub])
    m._emit_s5_disc(d, st)
    m._s5_emitted = False
    m._emit_s5_disc(d, st)
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    assert any("ya capturado" in x for x in diags), diags

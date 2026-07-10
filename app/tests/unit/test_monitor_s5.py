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


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_3.png").exists(), reason="fixture 10 discos no presente")
def test_s5_preview_grilla_al_entrar():
    """Al entrar a S5, el monitor emite 1× un preview `[disco] slot N · <set>` por cada disco de
    la grilla (antes de ver detalles), como el resumen por-disco de S2. Fixture de 10 discos."""
    import sqlite3
    from app.core.detector import ScreenState
    from app.db.repositories import DiscSetRepo
    import app.core.monitor as mon
    diags = []
    con = sqlite3.connect(str(REPO / "db" / "danibod_zzz_v2.db")); con.row_factory = sqlite3.Row
    m = mon.Monitor(ocr=_paddle(), detector=None, on_diagnostic=diags.append, set_repo=DiscSetRepo(con))
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), ScreenState("S5", 1.0, "s5_afinacion"))
    preview = [d for d in diags if d.startswith("[disco]")]
    assert len(preview) == 10, f"esperaba 10 líneas de preview, hubo {len(preview)}: {preview}"
    assert all("Firmamento llameante" in d for d in preview), preview
    assert any("slot 6" in d for d in preview) and any("slot 2" in d for d in preview), preview


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_4.png").exists(), reason="fixtures re-afinación no presentes")
def test_s5_reafinacion_reemite_preview_desde_misma_pantalla():
    """Re-afinar desde la MISMA pantalla de resultados (botón 'Afinar ×N', sin salir de S5) genera
    una tanda nueva (slots distintos) → el preview se re-emite. La secuencia de slots de la grilla
    (no la firma de imagen, que el highlight de selección arruina) detecta la nueva tanda."""
    import sqlite3
    from app.core.detector import ScreenState
    from app.db.repositories import DiscSetRepo
    import app.core.monitor as mon
    diags = []
    con = sqlite3.connect(str(REPO / "db" / "danibod_zzz_v2.db")); con.row_factory = sqlite3.Row
    m = mon.Monitor(ocr=_paddle(), detector=None, on_diagnostic=diags.append, set_repo=DiscSetRepo(con))
    st = ScreenState("S5", 1.0, "s5_afinacion")
    # Tanda A (slots 2,2,2,2,3,4,4,5,5,6) y luego re-afinar → Tanda B (1,1,1,1,4,4,5,6,6,6),
    # ambas dispatchadas como S5 consecutivas (prev=S5 en la 2ª → NO hay reset por entrada).
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), st)
    n_after_A = len([d for d in diags if d.startswith("[disco]")])
    m._dispatch_state(_load("Tienda_musica_afinacion_4.png"), st)
    preview = [d for d in diags if d.startswith("[disco]")]
    assert n_after_A == 10, f"tanda A: esperaba 10 preview, hubo {n_after_A}"
    assert len(preview) == 20, f"tras re-afinar: esperaba 20 (10+10), hubo {len(preview)}: {preview[-12:]}"
    assert any("slot 1" in d for d in preview), "la tanda B (slots 1) no se previsualizó"


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

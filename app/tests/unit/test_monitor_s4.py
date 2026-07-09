"""Handler del selector de tienda de música (S4) en el monitor (`_process_s4_music_selector`).

Con OCR real + DiscSetRepo real: al despachar un frame S4 el monitor OCRiza el género, lo
resuelve a set_id, lee el slot preseleccionado del hexágono y guarda la predicción en
FarmSession + emite un diagnóstico display-only. No persiste ni puntúa.

Necesita PaddleOCR + la DB viva → se marca skip si el OCR no está disponible."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenState

REPO = Path(__file__).resolve().parents[3]
_S4 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "18_Seleccion_set_farmeo_tienda_musica"
_DB = REPO / "db" / "danibod_zzz_v2.db"


def _load(name: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(_S4 / name), np.uint8), cv2.IMREAD_COLOR)


def _monitor(diags):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    from app.db.repositories import DiscSetRepo
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return mon.Monitor(
        ocr=PaddleBackend(), detector=None,
        on_diagnostic=diags.append,
        farm_session=FarmSession(),
        set_repo=DiscSetRepo(con),
    )


@pytest.mark.skipif(not (_S4 / "Ejemplo_5.png").exists(), reason="capturas S4 no presentes")
@pytest.mark.parametrize("name,set_id,slot", [
    ("Ejemplo_5.png", 32, "slot 5"),   # Punk Hormonal + slot 5
    ("Ejemplo_7.png", 30, "slot 6"),   # Metal Colmilludo + slot 6
    ("Ejemplo_1.png", 52, "aleatorio"),  # Salón huracanado, sin slot preseleccionado
])
def test_s4_predice_set_y_slot(name, set_id, slot):
    diags: list[str] = []
    m = _monitor(diags)
    m._dispatch_state(_load(name), ScreenState("S4", 0.90, "music_selector_override"))
    # Diagnóstico display-only emitido con el slot correcto.
    tienda = [d for d in diags if d.startswith("[tienda]")]
    assert tienda, f"{name}: sin diagnóstico de tienda ({diags})"
    assert slot in tienda[-1], f"{name}: {tienda[-1]!r} no contiene {slot!r}"
    # Predicción guardada en FarmSession con el set_id correcto.
    pred = m._farm_session.predicted(time.monotonic())
    assert pred is not None, f"{name}: FarmSession sin predicción"
    assert pred[1][0][0] == set_id, f"{name}: set_id {pred[1][0][0]} (esp. {set_id})"

"""Parser de la ficha del resultado de afinación (S5, tienda de música).

S5 reusa el motor de S3 con UNA columna (la ficha es vertical y angosta → nombres largos se
envuelven a 2 líneas, como en la grilla 2×2 de S3). Verifica sobre las 2 capturas reales que
extrae set/slot/main/substats correctos, incluyendo los substats de nombre largo envuelto
("Probabilidad de Crítico", "Maestría de Anomalía"). Necesita PaddleOCR → skip si no está."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S5 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "11_Tienda_Musica_Afinacion"
_DB = REPO / "db" / "danibod_zzz_v2.db"


def _load(name: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(_S5 / name), np.uint8), cv2.IMREAD_COLOR)


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion.png").exists(), reason="capturas S5 no presentes")
def test_s5_disco_3_moonlight():
    from app.core.parser_disc_s3 import parse_disc_s5
    from app.db.repositories import DiscSetRepo
    d = parse_disc_s5(_load("Tienda_musica_afinacion.png"), _paddle())
    con = sqlite3.connect(str(_DB)); con.row_factory = sqlite3.Row
    assert DiscSetRepo(con).resolve_id(d.set_name_raw) == 35   # Nana a la luz cenicienta
    assert d.slot == 3
    assert d.rareza == "S"
    assert d.main_stat_canon == "DEF" and d.main_valor == 46.0
    subs = {(s.nombre_canon or s.nombre_raw) for s in d.subs}
    assert "DEF%" in subs and "HP" in subs   # PV=HP; substats cortos


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_2.png").exists(), reason="capturas S5 no presentes")
def test_s5_disco_4_substats_envueltos():
    """El disco (4) tiene 'Maestría de Anomalía' (nombre largo que se envuelve a 2 líneas) → debe
    coalescerse a un solo substat, no partirse en 'Maestría de' + 'Anomalía' fantasma."""
    from app.core.parser_disc_s3 import parse_disc_s5
    from app.db.repositories import DiscSetRepo
    d = parse_disc_s5(_load("Tienda_musica_afinacion_2.png"), _paddle())
    con = sqlite3.connect(str(_DB)); con.row_factory = sqlite3.Row
    assert DiscSetRepo(con).resolve_id(d.set_name_raw) == 35
    assert d.slot == 4
    assert d.main_stat_canon == "Daño Crítico" and d.main_valor == 12.0
    canons = {(s.nombre_canon or s.nombre_raw) for s in d.subs}
    assert any("Anomal" in c for c in canons), canons     # Maestría de Anomalía, no partido
    assert not any(c.strip() in ("Maestría de", "Maestria de") for c in canons), canons

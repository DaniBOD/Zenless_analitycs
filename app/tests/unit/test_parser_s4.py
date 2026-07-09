"""Lecturas del selector de tienda de música (S4): slot del hexágono + género→set.

`read_preselected_slot` es geometría pura (sin OCR, determinista) → se testea sobre las 9
capturas reales. `read_music_genre` + resolución a set_id necesita OCR (PaddleOCR) → se marca
skip si no está disponible; valida que el nombre del género resuelve al set correcto de la DB
pese al ruido OCR (tildes, 'DEMO', espacios perdidos)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_s4 import read_preselected_slot, read_music_genre

REPO = Path(__file__).resolve().parents[3]
_S4 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "18_Seleccion_set_farmeo_tienda_musica"


def _load(name: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(_S4 / name), np.uint8), cv2.IMREAD_COLOR)


# Slot preseleccionado esperado por captura (leído visualmente del hexágono).
_SLOT_EXPECTED = {
    "Ejemplo_1.png": None, "Ejemplo_2.png": None, "Ejemplo_3.png": 1,
    "Ejemplo_4.png": 3, "Ejemplo_5.png": 5, "Ejemplo_6.png": 2,
    "Ejemplo_7.png": 6, "Ejemplo_8.png": 5, "Ejemplo_9.png": None,
}


@pytest.mark.skipif(not (_S4 / "Ejemplo_1.png").exists(), reason="capturas S4 no presentes")
@pytest.mark.parametrize("name,slot", list(_SLOT_EXPECTED.items()))
def test_read_preselected_slot(name, slot):
    assert read_preselected_slot(_load(name)) == slot


def test_read_preselected_slot_frame_vacio():
    assert read_preselected_slot(np.zeros((1439, 2559, 3), np.uint8)) is None
    assert read_preselected_slot(None) is None


# Género (OCR) → set_id esperado.
_GENRE_EXPECTED = {
    "Ejemplo_1.png": 52,  # Salón huracanado
    "Ejemplo_4.png": 33,  # Metal infernal
    "Ejemplo_7.png": 30,  # Metal colmilludo (con prefijo 'DEMO' del vinilo)
    "Ejemplo_9.png": 40,  # Tecno tetraodóntido
}


@pytest.mark.skipif(not (_S4 / "Ejemplo_1.png").exists(), reason="capturas S4 no presentes")
@pytest.mark.parametrize("name,set_id", list(_GENRE_EXPECTED.items()))
def test_read_genre_resuelve_a_set(name, set_id):
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    import sqlite3
    from app.db.repositories import DiscSetRepo
    con = sqlite3.connect(str(REPO / "db" / "danibod_zzz_v2.db"))
    con.row_factory = sqlite3.Row
    repo = DiscSetRepo(con)
    genre = read_music_genre(_load(name), PaddleBackend())
    assert genre, f"{name}: género vacío"
    assert repo.resolve_id(genre) == set_id, f"{name}: {genre!r} → {repo.resolve_id(genre)} (esp. {set_id})"

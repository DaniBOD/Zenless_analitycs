"""Regresión sobre frames REALES de la grilla S17 (carpeta 16_discos_pj_grilla,
provista por el usuario 2026-06-11). Valida el fix de localización del tile resaltado
por FORMA (anillo cuadrado-hueco, no max-área que elegía barras/arte dorado) + la
identificación del dueño por badge. Se saltea si los frames no están presentes (no se
versionan los PNG de 2.7 MB)."""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / "Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla"

pytestmark = pytest.mark.skipif(
    not FOLDER.is_dir() or not (FOLDER / "Ejemplo1_1.png").exists(),
    reason="frames reales de grilla no presentes (no versionados)",
)


def _rd(name):
    p = FOLDER / name
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def test_selected_tile_bbox_es_cuadrado_no_degenerado():
    """El bbox del tile resaltado debe ser ~cuadrado (aspect≈1), nunca la tira 5:1 de
    la barra 'Nivel' que el viejo argmax(área) elegía → recorte de badge inservible."""
    from app.core.detector import _selected_grid_tile_bbox
    bb = _selected_grid_tile_bbox(_rd("Ejemplo1_1.png"))
    assert bb is not None
    _x, _y, w, h = bb
    aspect = w / h
    assert 0.78 <= aspect <= 1.28, f"bbox no cuadrado (aspect={aspect:.2f}): {bb}"
    assert w >= 120 and h >= 120, f"bbox demasiado chico (degenerado): {bb}"


def test_badge_pipeline_round_trip_y_discrimina():
    """El grid-badge NO matchea el arte -ico (otra fuente, como S8/S18); solo matchea
    badges COSECHADOS. Con la cosecha inyectada, el pipeline crop→descriptor→match
    debe (a) reconocer el mismo badge y (b) discriminar el de OTRO disco. Valida el
    fix de localización + el descriptor sobre frames reales sin depender de la
    cobertura de la librería del usuario (aislada por conftest)."""
    from app.core.detector import crop_grid_selected_badge
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier()
    nangong = crop_grid_selected_badge(_rd("Ejemplo1_1.png"))   # equipado por Nangong
    otro = crop_grid_selected_badge(_rd("Ejemplo1_2.png"))      # otro disco/dueño
    assert nangong is not None and otro is not None
    ident.learn_s17(nangong, "Nangong Yu")                      # cosecha el badge real
    owner = ident.identify_s17(nangong)
    assert owner is not None and owner[0] == "Nangong Yu", owner
    # el badge de OTRO disco no debe colapsar a Nangong (discrimina)
    other_owner = ident.identify_s17(otro)
    assert other_owner is None or other_owner[0] != "Nangong Yu", other_owner


def test_no_degenera_en_frames_sin_aro():
    """En frames donde el aro no es visible (mid-scroll), el localizador devuelve None
    (badge ausente) en vez de un crop basura — el viejo bug daba bbox 143×28 con
    descriptor degenerado (dist 0 a varios PJs)."""
    from app.core.detector import _selected_grid_tile_bbox
    # Ejemplo1_4 / _8: el diag mostró que NO hay anillo cuadrado (transición/scroll).
    for fname in ["Ejemplo1_4.png", "Ejemplo1_8.png"]:
        bb = _selected_grid_tile_bbox(_rd(fname))
        if bb is not None:
            _x, _y, w, h = bb
            assert 0.78 <= w / h <= 1.28, f"{fname}: bbox degenerado reapareció: {bb}"

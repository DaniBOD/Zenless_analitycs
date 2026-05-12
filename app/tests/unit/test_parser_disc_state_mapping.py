"""
Test unit puro de parser_disc.roi_section_for_state — no requiere Tesseract.
Verifica que cada estado se mapea a la sección correcta de rois.toml.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from app.core.parser_disc import roi_section_for_state, _STATE_TO_ROI_SECTION


REPO = Path(__file__).resolve().parents[3]
ROIS_TOML = REPO / "app" / "config" / "rois.toml"


def test_known_states_map_to_existing_sections():
    """Cada estado conocido debe mapear a una sección que existe en rois.toml."""
    with open(ROIS_TOML, "rb") as f:
        rois = tomllib.load(f)

    for state, section in _STATE_TO_ROI_SECTION.items():
        assert section in rois, f"estado {state} apunta a sección inexistente '{section}'"


def test_unknown_state_falls_back_to_s3():
    """Estados no mapeados deben caer al default S3."""
    assert roi_section_for_state("S99") == "modal_detalle_s3"
    assert roi_section_for_state("") == "modal_detalle_s3"


@pytest.mark.parametrize("state,section", [
    ("S3",  "modal_detalle_s3"),
    ("S6",  "modal_detalle_s6"),
    ("S7",  "modal_detalle_s7"),
    ("S10", "modal_upgrade_s10"),
])
def test_explicit_state_mapping(state, section):
    assert roi_section_for_state(state) == section


def test_required_keys_present_per_state():
    """Cada sección de modal_detalle_* debe tener las ROIs mínimas para parsear un disco."""
    with open(ROIS_TOML, "rb") as f:
        rois = tomllib.load(f)

    required_modal_detalle = {
        "titulo", "main_stat_nombre", "main_stat_valor",
        "sub1_nombre", "sub1_valor", "sub2_nombre", "sub2_valor",
        "sub3_nombre", "sub3_valor", "sub4_nombre", "sub4_valor",
        "rareza_borde",
    }
    for section_name in ["modal_detalle_s3", "modal_detalle_s6", "modal_detalle_s7"]:
        section = rois[section_name]
        missing = required_modal_detalle - set(section.keys())
        assert not missing, f"{section_name} le faltan ROIs: {missing}"
        # nivel también requerido en S3/S6/S7 (S10 no tiene)
        assert "nivel" in section, f"{section_name} no tiene 'nivel'"

    # S10 tiene chips de exp en lugar de "nivel"
    s10 = rois["modal_upgrade_s10"]
    for key in ["exp_actual", "exp_progreso", "exp_total", "boton_mejorar"]:
        assert key in s10, f"modal_upgrade_s10 no tiene '{key}'"


def test_roi_values_are_normalized_floats():
    """Toda ROI debe ser una lista de 4 floats en el rango [0, 1]."""
    with open(ROIS_TOML, "rb") as f:
        rois = tomllib.load(f)

    for section_name, section in rois.items():
        for key, value in section.items():
            if not isinstance(value, list) or len(value) != 4:
                continue
            for i, coord in enumerate(value):
                assert isinstance(coord, (int, float)), \
                    f"{section_name}.{key}[{i}] no es número: {coord!r}"
                assert 0.0 <= coord <= 1.0, \
                    f"{section_name}.{key}[{i}] fuera de rango [0,1]: {coord}"

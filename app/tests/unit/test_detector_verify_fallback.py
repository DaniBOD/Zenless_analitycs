"""Fallback de verificación en `classify`: si el candidato top de template FALLA su
verificación secundaria, el pipeline cae al siguiente candidato que superó su umbral, en
vez de a S12.

Regresión concreta (QA farmeo 2026-07-07): el template de S2 matchea la pantalla S13
(selección de set de farmeo) a ~0.90 por chrome oscuro común. En frames de transición
donde el match de S13 baja un poco, S2 gana el template, `_verify_s2` no halla franjas de
disco y degrada a S12 → parpadeo S13↔S12 en bucle. Con el fallback, S13 sobrevive.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenDetector


def _detector_con_dos_fakes():
    """Detector real con `_templates` reemplazados por dos plantillas sintéticas: una 'S2'
    (match exacto → gana el template) y una 'S13' (match algo menor, pero pasa su umbral).
    El frame NO tiene franjas de rareza → `_verify_s2` falla."""
    det = ScreenDetector()
    det._state_machine = None  # sin state-machine: aislar la lógica de fallback

    rng = np.random.default_rng(42)
    patron = rng.integers(0, 256, size=(40, 40, 3), dtype=np.uint8)

    # Frame oscuro con el patrón en dos ubicaciones (S2 a la izq, S13 a la der).
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    frame[20:60, 20:60] = patron
    frame[20:60, 320:360] = patron

    # S2 con ruido leve → match alto pero <1.0 (así el degrade ×0.7 cae bajo el umbral 0.70,
    # como el caso real ~0.91 en vivo). S13 con ruido mayor → match algo menor, pero ≥0.70.
    ruido_s2 = rng.integers(-6, 7, size=patron.shape, dtype=np.int16)
    s2_tmpl = np.clip(patron.astype(np.int16) + ruido_s2, 0, 255).astype(np.uint8)
    ruido_s13 = rng.integers(-30, 31, size=patron.shape, dtype=np.int16)
    s13_tmpl = np.clip(patron.astype(np.int16) + ruido_s13, 0, 255).astype(np.uint8)

    det._templates = [
        {"code": "S2", "name": "fake_s2", "img": s2_tmpl},
        {"code": "S13", "name": "fake_s13", "img": s13_tmpl},
    ]
    return det, frame


def test_fallback_s2_falla_verify_cae_a_s13_no_s12():
    det, frame = _detector_con_dos_fakes()

    # Sanidad: S2 es el candidato top (match mayor) y ambos superan su umbral.
    passing, _ = det._template_candidates(frame)
    codes = [c.code for c in passing]
    assert codes[0] == "S2", f"esperaba S2 como top, got {[(c.code, c.confidence) for c in passing]}"
    assert "S13" in codes

    # `_verify_s2` sobre un frame sin franjas → S2 se degrada; el pipeline cae a S13.
    state = det.classify(frame)
    assert state.code == "S13", (
        f"esperaba fallback a S13, got {state.code} (conf={state.confidence}, "
        f"tmpl={state.template_name})"
    )


def test_sin_fallback_si_top_sobrevive_verify():
    """Si el candidato top NO tiene verificación (o la pasa), gana él directamente — el
    fallback no debe cambiar el comportamiento normal."""
    det, frame = _detector_con_dos_fakes()
    # Recodificar el top como S13 (sin verify) y el segundo como S2: el top debe ganar tal cual.
    det._templates[0]["code"] = "S13"
    det._templates[0]["name"] = "fake_top_s13"
    det._templates[1]["code"] = "S2"
    det._templates[1]["name"] = "fake_snd_s2"
    state = det.classify(frame)
    assert state.code == "S13"

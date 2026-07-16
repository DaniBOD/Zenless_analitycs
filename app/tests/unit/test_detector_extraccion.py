"""Detección del flujo de extracción por baterías (S21).

El farmeo por baterías es `S13 → S21 (modal de usos) → auto-combate → "Obtenido"`. Antes de
este estado, los 4 frames del modal caían a S12/dark_frame_filter (ningún template matcheaba:
el desenfoque del fondo tumba el match de S13, cuyo umbral es 0.70).

Los negativos importan tanto como los positivos: S21 se superpone SOBRE S13, así que hay que
verificar que la S13 plana sigue siendo S13 y que el modal no la eclipsa (ni al revés).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenDetector

_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Discos_Triggers" / "20_Extraccion_Baterias")

# Los 4 fixtures del modal de usos (el sufijo del nombre NO es el valor de N en todos, pero
# eso es irrelevante para la detección: es el mismo modal).
_S21_FX = [_FX / n for n in ("Seleccion_baterias_uso.png", "Seleccion_nodo_2.png",
                             "Seleccion_nodo_3.png", "Seleccion_nodo_4.png")]
_OBTENIDO_FX = sorted(_FX.glob("Resultados_discos*.png"))


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not all(p.exists() for p in _S21_FX), reason="capturas S21 no presentes")
@pytest.mark.parametrize("fx", _S21_FX, ids=lambda p: p.name)
def test_modal_de_usos_es_s21(fx):
    assert ScreenDetector().classify(_load(fx)).code == "S21"


@pytest.mark.skipif(not (_FX / "Seleccion_nodo.png").exists(), reason="captura S13 no presente")
def test_la_s13_plana_no_se_confunde_con_s21():
    """`Seleccion_nodo.png` es una S13 normal (sin modal encima) → debe seguir siendo S13.
    Regresión: el template de S21 no debe robarle el match a la pantalla que lo hospeda."""
    assert ScreenDetector().classify(_load(_FX / "Seleccion_nodo.png")).code == "S13"


@pytest.mark.skipif(not _OBTENIDO_FX, reason="capturas 'Obtenido' no presentes")
@pytest.mark.parametrize("fx", _OBTENIDO_FX, ids=lambda p: p.name)
def test_el_modal_obtenido_no_es_s21(fx):
    """El otro modal del mismo flujo ("Obtenido") no debe disparar S21."""
    assert ScreenDetector().classify(_load(fx)).code != "S21"

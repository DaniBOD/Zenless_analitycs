"""Lectura de la grilla de resultados de farmeo (S2) — `parse_s2_resultado`.

S2 ("Resultados del desafío") muestra una grilla PARCIAL de drops (colapsa con "▼" y el
desmontaje automático manda muchos a materiales) → el conteo exacto NO es confiable. Por
ahora solo detectamos los discos **tier S (dorados)**, que siempre aparecen en la grilla
(dirección del usuario 2026-06-27). El valor es el GATE: "hay un disco S farmeado" + un
conteo best-effort. Combinado con el contexto de flujo (`FarmSession`) sube la confianza de
que el S2 es un farmeo real y no otro "resultado de desafío".
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_s2 import parse_s2_resultado

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize("name", ["s2_resultado_ejemplo_1.png", "s2_resultado_ejemplo_2.png"])
def test_detecta_discos_tier_s(name):
    frame = cv2.imread(str(FIXTURES / name))
    assert frame is not None, f"falta fixture {name}"
    res = parse_s2_resultado(frame)
    assert res.has_s_discs is True
    assert res.gold_frac > 0.02
    assert res.n_s_approx >= 1


def test_frame_negro_no_detecta():
    frame = np.zeros((1439, 2559, 3), dtype=np.uint8)
    res = parse_s2_resultado(frame)
    assert res.has_s_discs is False
    assert res.n_s_approx == 0


# Los discos S pueden caer en CUALQUIER columna del grid. Ejemplo_7: 2 discos S (slots 5 y 6)
# en las columnas izquierdas → la región angosta vieja los perdía ("sin disco visible"). El
# conteo sobre el grid completo debe dar 2. (Regresión QA farmeo 2026-07-07.)
_RES = (Path(__file__).parent.parent.parent.parent / "Documentacion" / "Screenshots_Triggers"
        / "Discos_Triggers" / "01_Pantalla_Resultado_Desafio")


@pytest.mark.skipif(not (_RES / "Ejemplo_7.png").exists(), reason="capturas S2 no presentes")
def test_cuenta_discos_s_columna_izquierda_ejemplo_7():
    frame = cv2.imdecode(np.fromfile(str(_RES / "Ejemplo_7.png"), np.uint8), cv2.IMREAD_COLOR)
    res = parse_s2_resultado(frame)
    assert res.has_s_discs is True
    assert res.n_s_approx == 2, f"esperaba 2 discos S (slot 5 y 6), got {res.n_s_approx}"

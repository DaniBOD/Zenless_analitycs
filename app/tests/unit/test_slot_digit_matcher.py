"""Matcher del dígito de slot S2 por template (NCC) — `SlotDigitMatcher`.

El dígito de slot del tile S2 es un glifo estilizado chico que PaddleOCR lee mal de forma
crónica ('5'↔'S', '6'→'5', '4'→'2'). Como son 6 glifos fijos, la NCC del RESIDUO (crop − badge
promedio) contra recortes reales (app/resources/slot_digits/) es robusta. Test clave:
leave-one-out sobre las 30 referencias (cada crop clasificado contra las OTRAS, con el promedio
recomputado) → separa 1-6 sin OCR, incluyendo el '6'.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.slot_digit_matcher import SlotDigitMatcher, _raw_vec, _REFS_DIR

_REFS = sorted(_REFS_DIR.glob("*.png")) if _REFS_DIR.exists() else []


def _digit_of(p: Path) -> int:
    return int(p.name.split("_", 1)[0])


def _load(p: Path):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not _REFS, reason="refs de slot_digits no presentes")
def test_carga_las_referencias():
    m = SlotDigitMatcher.from_resources()
    assert m.n_refs == len(_REFS)
    assert m.n_refs >= 24
    assert set(_digit_of(p) for p in _REFS) == {1, 2, 3, 4, 5, 6}


@pytest.mark.skipif(len(_REFS) < 12, reason="refs de slot_digits insuficientes")
def test_leave_one_out_clasifica_todos():
    """Cada referencia, clasificada contra TODAS las demás (excluida ella misma, promedio
    recomputado sin ella), debe dar su propio dígito o abstenerse — NUNCA otro dígito. Es la
    prueba de que la NCC del residuo separa 1-6 (incl. el '6' que el OCR confunde)."""
    raw_by_digit: dict[int, list[np.ndarray]] = defaultdict(list)
    items = []  # (digit, raw, name)
    for p in _REFS:
        raw = _raw_vec(_load(p))
        assert raw is not None, p.name
        raw_by_digit[_digit_of(p)].append(raw)
        items.append((_digit_of(p), raw, p.name))

    wrong, abst = [], []
    for d, raw, name in items:
        # reconstruir refs SIN este crop (el matcher recomputa el promedio con lo que reciba)
        refs = {dd: [r for r in rs] for dd, rs in raw_by_digit.items()}
        refs[d] = [r for r in refs[d] if r is not raw]
        got, score = SlotDigitMatcher(refs).identify_raw(raw)
        if got is None:
            abst.append((name, round(score, 3)))
        elif got != d:
            wrong.append((name, d, got, round(score, 3)))
    assert not wrong, f"clasificados a OTRO dígito: {wrong}"
    assert len(abst) <= 2, f"demasiadas abstenciones: {abst}"


@pytest.mark.skipif(not _REFS, reason="refs de slot_digits no presentes")
def test_identify_reconoce_un_representante_por_digito():
    """identify() con el set COMPLETO reconoce un representante de cada dígito (el '6' incluido)."""
    m = SlotDigitMatcher.from_resources()
    seen: dict[int, Path] = {}
    for p in _REFS:
        seen.setdefault(_digit_of(p), p)
    for d, p in seen.items():
        got, score = m.identify(_load(p))
        assert got == d, f"{p.name}: esperaba {d}, dio {got} (score={score:.3f})"


def test_abstiene_con_ruido():
    """Ruido aleatorio (no un dígito) → abstención, no un slot inventado."""
    m = SlotDigitMatcher.from_resources()
    if m.n_refs == 0:
        pytest.skip("sin refs")
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (64, 77, 3), dtype=np.uint8)
    got, _ = m.identify(noise)
    assert got is None


def test_crop_vacio_devuelve_none():
    m = SlotDigitMatcher.from_resources()
    got, score = m.identify(np.zeros((0, 0, 3), np.uint8))
    assert got is None and score == 0.0

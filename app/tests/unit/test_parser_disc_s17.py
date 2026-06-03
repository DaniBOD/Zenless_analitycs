"""
Tests del parser espacial de S17 (disco equipado) — `parse_disc_s17`.

Corren sobre OCR cacheado (app/tests/fixtures/s17_ocr/*.json), generado con
PaddleOCR sobre 8 capturas reales 2559×1439. Esto los hace rápidos (sin
re-correr OCR) y deterministas.
"""
import json
from pathlib import Path

import pytest

from app.core.parser_disc_s17 import _parse_s17_from_lines

_FIX = Path(__file__).resolve().parent.parent / "fixtures" / "s17_ocr"


def _load(name: str):
    d = json.loads((_FIX / name).read_text(encoding="utf-8"))
    lines = [(t, c, tuple(bb)) for t, c, bb in d["lines"]]
    return _parse_s17_from_lines(lines, d["W"], d["H"])


def _subs_map(parsed):
    """Mapa {canon: (valor, unidad, rolls)} de substats canonizados."""
    return {
        s.nombre_canon: (s.valor, s.unidad, s.rolls)
        for s in parsed.subs if s.nombre_canon
    }


def test_ejemplo1_jazz_slot1_hp():
    r = _load("Ejemplo_1.json")
    assert r.set_name_raw == "Jazz caótico"
    assert r.slot == 1
    assert r.nivel == 15
    assert r.main_stat_canon == "HP"
    assert r.main_valor == 2200.0
    m = _subs_map(r)
    # ATK% (3%, 0 rolls) y ATK flat (38, 1 roll) coexisten — desambiguados por unidad
    assert m["ATK%"] == (3.0, "%", 0)
    assert m["ATK"] == (38.0, "flat", 1)
    assert m["Daño Crítico"] == (9.6, "%", 1)
    assert m["Maestría de Anomalía"] == (27.0, "flat", 2)


def test_ejemplo8_slot6_tasa_anomalia():
    """Slot 6 main = 'Tasa de Anomalía' 30% (NO 'Maestría de Anomalía')."""
    r = _load("Ejemplo_8.json")
    assert r.slot == 6
    assert r.main_stat_canon == "Tasa de Anomalía"
    assert r.main_valor == 30.0
    assert r.main_unidad == "%"
    # y NO debe haber nota de main inválido para el slot
    assert not any("main_invalido" in n for n in r.notas), r.notas


def test_ejemplo9_slot4_maestria_flat():
    """Slot 4 main = 'Maestría de Anomalía' flat (distinta de Tasa)."""
    r = _load("Ejemplo_9.json")
    assert r.slot == 4
    assert r.main_stat_canon == "Maestría de Anomalía"
    assert r.main_valor == 92.0
    assert r.main_unidad == "flat"


def test_titulo_dos_lineas():
    """Sets de nombre largo parten el título en 2 líneas; el slot va al final."""
    r2 = _load("Ejemplo_2.json")
    assert r2.set_name_raw == "Nana a la luz cenicienta"
    assert r2.slot == 1
    r4 = _load("Ejemplo_4.json")
    assert r4.set_name_raw == "Monarca del Pináculo"
    assert r4.slot == 1
    r10 = _load("Ejemplo_10.json")
    assert r10.set_name_raw == "Melodia de Faetón"
    assert r10.slot == 2


@pytest.mark.parametrize("name", [
    "Ejemplo_1.json", "Ejemplo_2.json", "Ejemplo_3.json", "Ejemplo_4.json",
    "Ejemplo_5.json", "Ejemplo_8.json", "Ejemplo_9.json", "Ejemplo_10.json",
])
def test_estructura_basica(name):
    """Invariantes en todas las capturas: slot 1-6, nivel 15, 4 substats, rolls ≤ 5."""
    r = _load(name)
    assert 1 <= r.slot <= 6, f"slot={r.slot}"
    assert r.nivel == 15
    assert len(r.subs) == 4, f"{len(r.subs)} substats"
    assert sum(s.rolls for s in r.subs) <= 5
    assert r.main_stat_canon is not None
    # main válido para su slot (no debe emitir nota de invalidez)
    assert not any("main_invalido" in n for n in r.notas), r.notas


@pytest.mark.parametrize("name", [
    "Ejemplo_1.json", "Ejemplo_3.json", "Ejemplo_4.json",
    "Ejemplo_5.json", "Ejemplo_8.json", "Ejemplo_9.json", "Ejemplo_10.json",
])
def test_substats_todas_canonizadas(name):
    """Todas las substats deben canonizar (tolera el caso OCR 'Dafo' de Ej.2 aparte)."""
    r = _load(name)
    sin_canon = [s.nombre_raw for s in r.subs if s.nombre_canon is None]
    assert not sin_canon, f"{name}: substats sin canon: {sin_canon}"

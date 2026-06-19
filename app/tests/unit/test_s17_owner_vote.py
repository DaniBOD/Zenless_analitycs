"""Tests de la política de voto grid+detail del dueño S17 (Fase 5R.L.3).

`_decide_s17_owner` combina los acumuladores SEPARADOS grid/detail con garantía RNF-02:
el grid es primario (sus reads son 0-wrong); el detail sube yield en NOLOC del grid pero
solo PROPONE dueño bajo guard (score acumulado + dominancia). La propiedad clave: el
detail NUNCA puede introducir un PJ que contradiga al grid (el viejo imán no mete wrongs).
"""
from app.core.monitor import (
    _decide_s17_owner,
    _DET_SOLO_MIN_SCORE,
    _DET_SOLO_DOMINANCE,
)


def test_grid_solo_manda():
    owner, src = _decide_s17_owner({"Vivian": 0.9}, {})
    assert owner == "Vivian" and src == "grid"


def test_grid_y_detail_coinciden_corrobora():
    owner, src = _decide_s17_owner({"Vivian": 0.9}, {"Vivian": 1.8})
    assert owner == "Vivian" and src == "grid+det"


def test_grid_primario_el_detail_no_puede_pisar():
    """RNF-02: aunque el detail vote OTRO PJ con score altísimo (el viejo imán),
    el grid manda → el imán no puede meter un wrong."""
    owner, src = _decide_s17_owner({"Vivian": 0.85}, {"Nangong Yu": 2.4})
    assert owner == "Vivian" and src == "grid"


def test_detail_solo_fuerte_propone():
    """Grid en NOLOC (sin votos), detail fuerte + dominante → propone dueño."""
    owner, src = _decide_s17_owner({}, {"Burnice": _DET_SOLO_MIN_SCORE + 0.1})
    assert owner == "Burnice" and src == "det"


def test_detail_solo_un_frame_confiable_propone():
    """Caso real QA 2026-06-18: grid NOLOC, detalle con UN frame confiable (conf 1.00 /
    0.81) → debe proponer (antes el umbral 1.30 lo dejaba 'incierto')."""
    assert _decide_s17_owner({}, {"Yanagi": 1.00}) == ("Yanagi", "det")
    assert _decide_s17_owner({}, {"Seth": 0.81}) == ("Seth", "det")


def test_detail_solo_debil_se_abstiene():
    """Detail solo pero score bajo el guard → incierto (abstención, RNF-02)."""
    owner, src = _decide_s17_owner({}, {"Burnice": _DET_SOLO_MIN_SCORE - 0.2})
    assert owner is None and src is None


def test_detail_solo_sin_dominancia_se_abstiene():
    """Dos PJs del detail con scores parejos (empate cerrado) → incierto."""
    s = _DET_SOLO_MIN_SCORE + 0.5
    owner, src = _decide_s17_owner({}, {"Soukaku": s, "Ben": s / _DET_SOLO_DOMINANCE + 0.01})
    assert owner is None and src is None


def test_detail_solo_dominante_un_competidor_chico_pasa():
    s = _DET_SOLO_MIN_SCORE + 0.5
    owner, src = _decide_s17_owner({}, {"Soukaku": s, "Ben": 0.2})
    assert owner == "Soukaku" and src == "det"


def test_vacio_incierto():
    owner, src = _decide_s17_owner({}, {})
    assert owner is None and src is None

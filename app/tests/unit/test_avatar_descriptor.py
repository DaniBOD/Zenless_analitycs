"""Fase 5R — tests del descriptor robusto de identidad por ícono."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.avatar_descriptor import (
    AvatarMatcher,
    build_descriptor,
    build_name_map,
    descriptor_distance,
)

REFS = Path(__file__).resolve().parents[3] / "app" / "resources" / "avatar_refs"
REJECT = Path(__file__).resolve().parents[3] / "app" / "resources" / "avatar_reject"


def _ref(name: str) -> np.ndarray:
    img = cv2.imread(str(REFS / f"{name}.png"))
    assert img is not None, f"falta ref {name}.png"
    return img


@pytest.fixture(scope="module")
def matcher() -> AvatarMatcher:
    return AvatarMatcher.from_folders(REFS)


def test_from_folders_carga_roster(matcher):
    assert len(matcher.names) >= 40  # roster completo (~53)


def test_build_descriptor_none_en_vacio():
    assert build_descriptor(None) is None
    assert build_descriptor(np.zeros((0, 0, 3), np.uint8)) is None


def test_self_match_identifica(matcher):
    r = matcher.match(_ref("Ellen"))
    assert r.name == "Ellen"
    assert r.conf > 0.9           # self-match → distancia ~0
    assert r.margin > 0.05


def test_refs_distintos_separados():
    a = build_descriptor(_ref("Ellen"))
    b = build_descriptor(_ref("Nicole"))
    assert descriptor_distance(a, b) > 0.15


def test_self_distance_casi_cero():
    a = build_descriptor(_ref("Lycaon"))
    assert descriptor_distance(a, a) < 1e-4


def test_abstiene_en_ruido(matcher):
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    r = matcher.match(noise)
    assert r.name is None         # ruido → baja conf/margen → abstención


def test_reject_set_descarta():
    img = _ref("Ellen")
    # 1 ref (Lucy) + reject = la propia query (Ellen). El reject queda más cerca.
    m = AvatarMatcher(
        refs={"Lucy": build_descriptor(_ref("Lucy"))},
        rejects=[build_descriptor(img)],
        min_conf=0.0, min_margin=0.0,
    )
    r = m.match(img)
    assert r.rejected is True
    assert r.name is None


def test_add_reference_override_hibrido():
    m = AvatarMatcher()
    assert m.add_reference("Cosechado", _ref("Ellen")) is True
    assert "Cosechado" in m.names
    r = m.match(_ref("Ellen"))
    assert r.name == "Cosechado"  # la ref agregada gana


def test_match_sin_refs_devuelve_none():
    m = AvatarMatcher()
    r = m.match(_ref("Ellen"))
    assert r.name is None and r.top == []


def test_build_name_map_alias_y_passthrough():
    roster = ["César", "Jane", "Ellen", "N.º 11"]
    nm = build_name_map(["Caesar", "Jane-Doe", "Ellen", "Soldier-11", "Aria"], roster)
    assert nm["Caesar"] == "César"      # alias por acento
    assert nm["Jane-Doe"] == "Jane"     # alias guion
    assert nm["Soldier-11"] == "N.º 11"  # alias traducción
    assert nm["Ellen"] == "Ellen"       # match directo
    assert nm["Aria"] == "Aria"         # no en roster → stem tal cual


def test_reject_desde_folder_descarta_no_pj():
    m = AvatarMatcher.from_folders(REFS, REJECT)
    assert len(m._rejects) > 0
    r = m.match(cv2.imread(str(REJECT / "disc_a.png")))
    assert r.rejected is True
    assert r.name is None


def test_multi_ref_acumula_con_cap():
    """Multi-ref: add_reference acumula varios badges por PJ (cosecha) con cap."""
    m = AvatarMatcher()
    for _ in range(8):
        m.add_reference("X", _ref("Ellen"), max_per_name=5)
    assert len(m._refs["X"]) == 5            # cap respetado
    r = m.match(_ref("Ellen"))
    assert r.name == "X" and r.conf > 0.9    # matchea por min-distancia sobre sus refs


def test_multi_ref_min_distance_cubre_dos_caras():
    """Un PJ con 2 refs distintas (cosechas en distinto estilo) matchea cualquiera."""
    m = AvatarMatcher()
    m.add_reference("PJ", _ref("Ellen"))
    m.add_reference("PJ", _ref("Lycaon"))
    assert m.match(_ref("Ellen")).name == "PJ"
    assert m.match(_ref("Lycaon")).name == "PJ"


def _desaturate(bgr: np.ndarray, factor: float = 0.12) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = (hsv[:, :, 1].astype(np.float32) * factor).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_pj_gris_detectado_y_matchea_por_luminancia(matcher):
    """PJ no obtenido (gris): se detecta como desaturado y matchea su ref a color
    por luminancia (el filtro gris preserva la luz)."""
    grey = _desaturate(_ref("Ellen"))
    d = build_descriptor(grey)
    assert d.is_gray                       # detectado como gris
    r = matcher.match(grey)
    assert r.name == "Ellen"               # matchea la ref a color por canal L


def test_pj_color_no_es_gris():
    """Un avatar a color normal NO se marca como gris."""
    assert build_descriptor(_ref("Nicole")).is_gray is False

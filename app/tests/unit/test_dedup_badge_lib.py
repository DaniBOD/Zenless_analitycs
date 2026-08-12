"""Tests de `tools/dedup_badge_lib.py` — la limpieza de refs clonadas.

La herramienta existe porque `BadgeSurface.learn` corta la fuente pero no desocupa las ranuras que
los clones ya ocupan, y el techo de `_MAX_REFS_PER_NAME` sigue bloqueando cosecha real hasta que se
limpien (spec 2026-08-11).
"""
from __future__ import annotations

import collections
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.avatar_descriptor import AvatarDescriptor, AvatarMatcher, descriptor_distance
from app.core.badge_surface import _CLON_MAX_DIST

REPO = Path(__file__).resolve().parents[3]
_REFS = REPO / "app" / "resources" / "avatar_refs"


def _tool():
    """Importa la herramienta por NOMBRE SUELTO, con `tools/` en el path y sacándolo después.

    NO se puede hacer `from tools.dedup_badge_lib import ...`: eso registra el `tools/` del repo
    como `sys.modules['tools']` y **le tapa el suyo a PaddleOCR**, que internamente hace
    `from tools.infer import ...`. El síntoma es brutal y no señala acá — 592 tests de OCR
    fallando con "paddleocr no instalado" en la suite completa, mientras el archivo solo pasa.
    Es el mismo patrón que usa `test_audit_badge_lib.py`.
    """
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import dedup_badge_lib
        return dedup_badge_lib
    finally:
        sys.path.remove(str(REPO / "tools"))


def _cara(name):
    img = cv2.imread(str(_REFS / name))
    if img is None:
        pytest.skip(f"assets no disponibles: {name}")
    return img


def _libreria(tmp_path, entradas):
    """Escribe un .npz con las (clase, imagen) dadas, repeticiones incluidas."""
    m = AvatarMatcher()
    for clase, img in entradas:
        m.add_reference(clase, img, max_per_name=99)
    p = tmp_path / "lib.npz"
    m.save(p)
    return p


def _refs_por_clase(p):
    return collections.Counter(str(x) for x in np.load(str(p), allow_pickle=True)["names"])


def test_el_dry_run_no_toca_el_archivo(tmp_path, capsys):
    """Un audit no muta su objeto de estudio: se verifica por sha256, no por el docstring."""
    p = _libreria(tmp_path, [("Ellen", _cara("Ellen.png"))] * 4)
    antes = hashlib.sha256(p.read_bytes()).hexdigest()
    assert _tool().procesar(p, dry_run=True, save_snapshot=False) == 0
    assert hashlib.sha256(p.read_bytes()).hexdigest() == antes
    assert "dry-run" in capsys.readouterr().out


def test_colapsa_los_clones_y_deja_una(tmp_path):
    p = _libreria(tmp_path, [("Ellen", _cara("Ellen.png"))] * 4)
    assert _refs_por_clase(p)["Ellen"] == 4
    _tool().procesar(p, dry_run=False, save_snapshot=False)
    assert _refs_por_clase(p)["Ellen"] == 1


def test_no_pierde_ninguna_clase(tmp_path):
    """Perder una clase es peor que tener clones: el PJ deja de poder nombrarse."""
    entradas = ([("Ellen", _cara("Ellen.png"))] * 3
                + [("Nicole", _cara("Nicole.png"))] * 2
                + [("Lucy", _cara("Lucy.png"))])
    p = _libreria(tmp_path, entradas)
    _tool().procesar(p, dry_run=False, save_snapshot=False)
    assert set(_refs_por_clase(p)) == {"Ellen", "Nicole", "Lucy"}


def test_conserva_la_variacion_real(tmp_path):
    """Dos imágenes distintas de la misma clase NO son clones y las dos sobreviven."""
    p = _libreria(tmp_path, [("Ellen", _cara("Ellen.png")), ("Ellen", _cara("Nicole.png"))])
    _tool().procesar(p, dry_run=False, save_snapshot=False)
    assert _refs_por_clase(p)["Ellen"] == 2


def test_el_resultado_no_deja_pares_clonados(tmp_path):
    """El invariante de salida, medido sobre el archivo escrito."""
    entradas = [("Ellen", _cara("Ellen.png"))] * 3 + [("Ellen", _cara("Nicole.png"))] * 2
    p = _libreria(tmp_path, entradas)
    _tool().procesar(p, dry_run=False, save_snapshot=False)
    d = np.load(str(p), allow_pickle=True)
    ds = [AvatarDescriptor(d["hist"][i], d["ncc"][i], d["regions"][i], d["gray"][i],
                           bool(d["is_gray"][i])) for i in range(len(d["names"]))]
    for a in range(len(ds)):
        for b in range(a + 1, len(ds)):
            if str(d["names"][a]) == str(d["names"][b]):
                assert descriptor_distance(ds[a], ds[b], None, False) > _CLON_MAX_DIST


def test_planificar_no_escribe(tmp_path):
    """`planificar` es la parte pura: se puede llamar para reportar sin riesgo."""
    p = _libreria(tmp_path, [("Ellen", _cara("Ellen.png"))] * 3)
    antes = hashlib.sha256(p.read_bytes()).hexdigest()
    keep, resumen = _tool().planificar(p)
    assert len(keep) == 1 and resumen["Ellen"] == (3, 1)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == antes


def test_escribir_conserva_el_formato_que_la_app_carga(tmp_path):
    """El .npz resultante tiene que poder cargarse con `load_merge`, o la limpieza deja a la app
    sin librería — que es exactamente el fallo que ya costó dos vaciados."""
    p = _libreria(tmp_path, [("Ellen", _cara("Ellen.png"))] * 3)
    keep, _ = _tool().planificar(p)
    _tool().escribir(p, keep)
    m = AvatarMatcher()
    assert m.load_merge(p) == 1
    assert "Ellen" in m._refs

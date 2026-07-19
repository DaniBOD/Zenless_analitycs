"""Tests del contrato REUSABLE de `app/core/badge_surface.py` (5R.L.8 / B1).

`BadgeSurface` = crop_fn + AvatarMatcher + librería propia + canonicalización al
roster + gating de persistencia + presencia estructural, empaquetados para que una
pantalla nueva (S9/S23) declare su superficie sin re-implementar el boilerplate.
`AgentIdentifier` compone tres (row/grid/detail) manteniendo su API histórica.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.avatar_descriptor import AvatarMatcher
from app.core.badge_surface import BadgeOutcome, BadgeSurface

REPO = Path(__file__).resolve().parents[3]
_REFS = REPO / "app" / "resources" / "avatar_refs"


def _cara(name="Ellen.png"):
    img = cv2.imread(str(_REFS / name))
    assert img is not None
    return img


def _surface(tmp_path, **kw):
    kw.setdefault("crop_fn", lambda frame: frame)      # la "pantalla" ya entrega el crop
    kw.setdefault("matcher", AvatarMatcher())
    kw.setdefault("library_path", tmp_path / "surf.npz")
    kw.setdefault("canonicalize", lambda n: {"lucia": "Lucía"}.get(n.lower(), n))
    return BadgeSurface(name="test_surf", **kw)


def test_learn_canonicaliza_y_persiste(tmp_path):
    """learn() canonicaliza el label por el roster ANTES de guardar — la lección del
    bug 2026-06-18 (claves en minúscula → prune_to_roster vació la librería)."""
    s = _surface(tmp_path)
    assert s.learn(_cara(), "Lucia") is True
    assert "Lucía" in s.matcher._refs                  # clave canónica, no el label crudo
    assert (tmp_path / "surf.npz").exists()            # persistida
    # canonicalize devuelve None → label fuera del roster → NO aprende
    s2 = _surface(tmp_path, canonicalize=lambda n: None,
                  library_path=tmp_path / "s2.npz", matcher=AvatarMatcher())
    assert s2.learn(_cara(), "Permiso") is False
    assert not s2.matcher._refs


def test_learn_respeta_el_gate_de_persistencia(tmp_path):
    """persist_gate=False (readonly sin modo cosecha) → learn inerte, no escribe."""
    s = _surface(tmp_path, persist_gate=lambda: False)
    assert s.learn(_cara(), "Ellen") is False
    assert not s.matcher._refs and not (tmp_path / "surf.npz").exists()


def test_sample_devuelve_outcome_completo(tmp_path):
    """sample(frame) = crop + match + presencia en un paso. Con crop y match sobre el
    guard → nombre; sin crop → ausente."""
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    out = s.sample(_cara())
    assert isinstance(out, BadgeOutcome)
    assert out.present is True and out.name == "Ellen" and out.conf >= 0.80
    # crop_fn devuelve None (no localizó) → ausente, sin naming
    s_no = _surface(tmp_path, crop_fn=lambda f: None,
                    library_path=tmp_path / "s3.npz", matcher=AvatarMatcher())
    out2 = s_no.sample(_cara())
    assert out2.present is False and out2.name is None and out2.crop is None


def test_sample_presencia_estructural_independiente_del_naming(tmp_path):
    """presence_fn (p.ej. cara-vs-texto del detalle) manda sobre la presencia aunque
    el matcher no pueda nombrar: el caso Jane a nivel superficie."""
    s = _surface(tmp_path, presence_fn=lambda crop: True)   # clasificador dice: es cara
    out = s.sample(_cara("Nicole.png"))                     # librería vacía → sin nombre
    assert out.present is True and out.name is None
    s2 = _surface(tmp_path, presence_fn=lambda crop: False,  # clasificador dice: texto
                  library_path=tmp_path / "s4.npz", matcher=AvatarMatcher())
    out2 = s2.sample(_cara())
    assert out2.present is False


def test_guard_de_naming_se_abstiene_bajo_umbral(tmp_path):
    """Un match bajo el guard devuelve name=None (RNF-02) pero conserva conf/margin."""
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    out = s.sample(_cara("Nicole.png"))                 # otra cara: sim < guard
    assert out.name is None
    assert out.conf < 0.80 or out.rejected


def test_load_merge_reincorpora_lo_persistido(tmp_path):
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    fresh = _surface(tmp_path, matcher=AvatarMatcher())
    assert fresh.load() == 1
    assert "Ellen" in fresh.matcher._refs


def test_agent_identifier_expone_surfaces():
    """AgentIdentifier compone las 3 superficies históricas y las expone por nombre
    (la vía de entrada para consumidores nuevos)."""
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier(autoload=False)
    assert set(ident.surfaces) >= {"row", "grid", "detail"}
    assert ident.surfaces["grid"].matcher is ident._badge
    assert ident.surfaces["detail"].matcher is ident._detbadge
    assert ident.surfaces["row"].matcher is ident._row

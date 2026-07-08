"""Matcher de sets por badge/render del disco (`SetBadgeMatcher`) — Fase B.

En S2 cada tile muestra el render del disco (arte del set). Este matcher reconoce el SET
(no la rareza) a partir de ese render, restringido a las 2 clases predichas por S13. Reusa el
descriptor de `avatar_descriptor.AvatarMatcher` con center-crop del disco (descarta el badge
"RARITY S/A/B", la marca de agua y el marco → invariante al tier).

Test OFFLINE (leave-one-out sobre los 81 package badges): valida que el descriptor discrimina
los 2 sets de cada nodo tratando S/A/B como la MISMA clase. Es condición necesaria; el gap
render-package vs tile-in-game es riesgo aceptado (§8.1: fallback = cosecha de tiles reales).
"""
from __future__ import annotations

import glob
import tomllib
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.asset_resolver import SET_BADGES_DIR
from app.core.avatar_descriptor import AvatarMatcher, build_descriptor
from app.core.set_badge_matcher import (
    SetBadgeMatcher,
    crop_package_disc,
    en_from_badge_filename,
)

_TOML = Path(__file__).resolve().parents[2] / "resources" / "farm_nodes.toml"


def _nodes() -> list[dict]:
    with open(_TOML, "rb") as f:
        return tomllib.load(f)["nodes"]


@pytest.fixture(scope="module")
def descs() -> dict[str, dict[str, object]]:
    """{nombre_en: {tier: descriptor}} desde los 81 package badges, cropeado 1× (rápido)."""
    out: dict[str, dict[str, object]] = {}
    for p in sorted(glob.glob(str(SET_BADGES_DIR / "*.webp"))):
        stem = Path(p).stem
        en = en_from_badge_filename(stem)
        tier = stem[-1]
        img = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
        d = build_descriptor(crop_package_disc(img))
        assert d is not None, p
        out.setdefault(en, {})[tier] = d
    return out


def test_filename_parse_a_nombre_en():
    assert en_from_badge_filename("Drive_Disc_Dawn%27s_Bloom_S") == "Dawn's Bloom"
    assert en_from_badge_filename("Drive_Disc_The_Sky_Ablaze_A") == "The Sky Ablaze"
    assert en_from_badge_filename("Drive_Disc_Astral_Voice_B") == "Astral Voice"


def test_from_package_badges_carga_27_sets():
    m = SetBadgeMatcher.from_package_badges()
    # 27 sets × 3 tiers (Branch & Blade Song sin badge). Cada set = 1 clase multi-ref.
    assert len(m.names) == 27
    assert "Dawn's Bloom" in m.names
    assert "Branch & Blade Song" not in m.names


def _matcher_excluding(descs, held_en, held_tier) -> SetBadgeMatcher:
    """AvatarMatcher con todas las refs salvo (held_en, held_tier) → leave-one-out."""
    refs: dict[str, list] = {}
    for en, tiers in descs.items():
        for tier, d in tiers.items():
            if en == held_en and tier == held_tier:
                continue
            refs.setdefault(en, []).append(d)
    return SetBadgeMatcher(AvatarMatcher(refs=refs))


def test_leave_one_out_separa_los_2_sets_de_cada_nodo(descs):
    """Para cada nodo, el badge held-out de un set (excluido de refs) matchea ese set y no el
    otro candidato del nodo (tratando S/A/B como misma clase)."""
    fallos: list[str] = []
    total = 0
    for node in _nodes():
        cand = [en for en in node["sets_en"] if en in descs]
        if len(cand) < 2:
            continue  # nodo degradado (Branch & Blade Song sin badge) → sin par que separar
        for en in cand:
            for tier in descs[en]:
                total += 1
                m = _matcher_excluding(descs, en, tier)
                res = m.identify(descs[en][tier], cand)
                if res.name != en:
                    fallos.append(f"{en}/{tier} (nodo {node['titulo_es']}) → {res.name} conf={res.conf}")
    assert total > 0
    # Umbral de robustez: el descriptor sobre renders limpios debe separar >90% de los pares.
    tasa_ok = 1.0 - len(fallos) / total
    assert tasa_ok >= 0.90, f"separación {tasa_ok:.0%} ({len(fallos)}/{total}); fallos:\n" + "\n".join(fallos)


def test_identify_abstiene_si_no_hay_candidatos(descs):
    m = SetBadgeMatcher.from_package_badges()
    res = m.identify(descs["Dawn's Bloom"]["S"], [])
    assert res.name is None

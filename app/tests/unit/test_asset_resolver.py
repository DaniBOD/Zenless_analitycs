"""
Tests del asset_resolver — verifica que cada set/agente de la DB resuelve a
un archivo existente, y que los overrides irregulares funcionan.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.asset_resolver import (
    SET_LOGOS_DIR,
    SPLASH_ARTS_DIR,
    PJ_STATS_DIR,
    agent_avatar_path,
    set_logo_path,
    _normalize_for_pj_stats,
    _normalize_for_splash,
    _set_filename_from_en,
)


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_name,expected", [
    ("Astra Yao",       "Astra_Yao"),
    ("César",           "Cesar"),
    ("Lucía",           "Lucia"),
    ("Antón",           "Anton"),
    ("Pan Yinhu",       "Pan_Yinhu"),
    ("Ju Fufu",         "Ju_Fufu"),
])
def test_normalize_for_pj_stats(input_name, expected):
    assert _normalize_for_pj_stats(input_name) == expected


@pytest.mark.parametrize("input_name,expected", [
    ("Astra Yao",       "Astra-Yao"),
    ("César",           "Cesar"),
    ("Pan Yinhu",       "Pan-Yinhu"),
])
def test_normalize_for_splash(input_name, expected):
    assert _normalize_for_splash(input_name) == expected


@pytest.mark.parametrize("input_en,expected_filename", [
    ("Astral Voice",       "Drive_Disc_Astral_Voice_Icon.webp"),
    ("Chaos Jazz",         "Drive_Disc_Chaos_Jazz_Icon.webp"),
    ("Branch & Blade Song", "Drive_Disc_Branch_%26_Blade_Song_Icon.webp"),
    ("Dawn's Bloom",       "Drive_Disc_Dawn%27s_Bloom_Icon.webp"),
])
def test_set_filename_from_en(input_en, expected_filename):
    assert _set_filename_from_en(input_en) == expected_filename


# ---------------------------------------------------------------------------
# Cobertura real contra disco (smoke tests)
# ---------------------------------------------------------------------------

# Sets que SÍ deben tener archivo (sample mínimo de los 26)
SAMPLE_SETS_EN = [
    "Yunkui Tales",
    "Branch & Blade Song",
    "Dawn's Bloom",
    "Astral Voice",
    "Chaos Jazz",
    "Polar Metal",
    "Puffer Electro",
    "Moonlight Lullaby",
    "Woodpecker Electro",
]


@pytest.mark.parametrize("nombre_en", SAMPLE_SETS_EN)
def test_set_logo_path_exists(nombre_en):
    p = set_logo_path(nombre_en)
    assert p is not None, f"No se encontró logo para set '{nombre_en}'"
    assert p.exists(), f"Path devuelto no existe: {p}"


def test_set_logo_path_returns_none_for_unknown():
    assert set_logo_path("Fake Nonexistent Set") is None
    assert set_logo_path(None) is None
    assert set_logo_path("") is None


# Agentes con overrides irregulares (los más sensibles)
IRREGULAR_AGENTS = [
    "Sporos",      # → Seed
    "Gatillo",     # → Trigger
    "Cissia",      # → cissia (lowercase + _)
    "César",       # → Caesar
    "Astra Yao",   # → Astra-yao (lowercase)
    "Orfia y Magas",  # → Orphie
    "N.º 11",   # MASCULINE ORDINAL (ord)
    "N.º 0: Anby",
]


@pytest.mark.parametrize("nombre", IRREGULAR_AGENTS)
@pytest.mark.parametrize("variant", ["extend", "ico"])
def test_irregular_agent_resolves(nombre, variant):
    p = agent_avatar_path(nombre, variant=variant)
    assert p is not None, f"No se encontró avatar para '{nombre}' variant={variant}"
    assert p.exists(), f"Path devuelto no existe: {p}"


def test_agent_avatar_returns_none_for_unknown():
    assert agent_avatar_path("Fake Agent", variant="extend") is None
    assert agent_avatar_path(None) is None
    assert agent_avatar_path("") is None


def test_agent_avatar_pj_stats_variant():
    p = agent_avatar_path("Yanagi", variant="pj_stats")
    assert p is not None
    assert p.suffix == ".jpeg"
    assert p.parent == PJ_STATS_DIR


def test_agent_avatar_extend_variant():
    p = agent_avatar_path("Yanagi", variant="extend")
    assert p is not None
    assert p.suffix == ".webp"
    assert "extend" in p.name
    assert p.parent == SPLASH_ARTS_DIR


def test_agent_avatar_ico_variant():
    p = agent_avatar_path("Burnice", variant="ico")
    assert p is not None
    assert "ico" in p.name
    assert p.parent == SPLASH_ARTS_DIR


def test_agent_avatar_invalid_variant():
    assert agent_avatar_path("Yanagi", variant="invalid") is None


# ---------------------------------------------------------------------------
# Cobertura full contra DB (test de integración liviano)
# ---------------------------------------------------------------------------

# Agentes con onboarding PARCIAL (assets diferidos por diseño — RNF-02). Quedan exentos
# del check de Pj_stats hasta que se complete el onboarding (se captura su screenshot
# HoYoLAB). Ver audit/onboarding_billy_estelar_20260612.md. Sus splash -extend/-ico SÍ
# existen y se verifican normalmente.
# Velina (id 48) y Pyrois (id 49): onboarding parcial vigente — faltan thresholds/splash/IA
# y su Pj_stats.jpeg HoYoLAB. Ver memoria project_velina_onboarding / project_pyrois_onboarding.
_PJ_STATS_DEFERIDO = {"Billy Estelar", "Velina", "Pyrois"}


def test_full_coverage_against_db():
    """Verifica que TODOS los sets y agentes resuelven (-extend siempre; Pj_stats salvo
    onboarding parcial diferido)."""
    pytest.importorskip("sqlite3")
    from app.db.connection import get_connection
    from app.db.repositories import AgentRepo, DiscSetRepo

    con = get_connection()
    try:
        # Sets
        set_misses = []
        for s in DiscSetRepo(con).get_all():
            if set_logo_path(s.nombre_en) is None:
                set_misses.append(f"{s.nombre} ({s.nombre_en})")
        assert not set_misses, f"Sets sin logo: {set_misses}"

        # Agents
        agent_misses_extend = []
        agent_misses_pj = []
        for a in AgentRepo(con).get_all():
            if agent_avatar_path(a.nombre, variant="extend") is None:
                agent_misses_extend.append(a.nombre)
            if a.nombre not in _PJ_STATS_DEFERIDO and agent_avatar_path(a.nombre, variant="pj_stats") is None:
                agent_misses_pj.append(a.nombre)
        assert not agent_misses_extend, f"Agentes sin -extend.webp: {agent_misses_extend}"
        assert not agent_misses_pj, f"Agentes sin Pj_stats.jpeg: {agent_misses_pj}"
    finally:
        con.close()

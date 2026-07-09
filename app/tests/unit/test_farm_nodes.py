"""Catálogo de nodos de farmeo (S13) — `FarmNodeCatalog`.

En S13 el juego muestra el título del nodo a farmear. El catálogo mapea ese título
(por OCR, insensible a tildes/ñ/mayúsculas) → los 2 sets que dropea el nodo, resueltos
a `set_id` vía nombre_en. Fase A del plan de predicción de sets (display-only).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from app.core.farm_nodes import FarmNode, FarmNodeCatalog, best_predicted_set_id

_TOML = Path(__file__).resolve().parents[2] / "resources" / "farm_nodes.toml"


def _toml_nodes() -> list[dict]:
    with open(_TOML, "rb") as f:
        return tomllib.load(f)["nodes"]


def _full_set_ids() -> dict[str, int]:
    """{nombre_en: id} sintético que cubre los 28 sets del toml (ids arbitrarios estables)."""
    ens: list[str] = []
    for n in _toml_nodes():
        ens.extend(n["sets_en"])
    return {en: i + 1 for i, en in enumerate(dict.fromkeys(ens))}


@pytest.fixture
def catalog() -> FarmNodeCatalog:
    return FarmNodeCatalog.from_toml(_TOML, _full_set_ids())


def test_toml_tiene_14_nodos_de_2_sets():
    nodes = _toml_nodes()
    assert len(nodes) == 14
    assert all(len(n["sets_en"]) == 2 for n in nodes)


def test_matchea_los_14_titulos_exactos(catalog):
    for n in _toml_nodes():
        node = catalog.match_title(n["titulo_es"])
        assert node is not None, n["titulo_es"]
        assert node.titulo_es == n["titulo_es"]
        assert len(node.sets) == 2


def test_resuelve_los_28_en_a_set_id(catalog):
    # Con el mapa completo, ningún set queda sin resolver.
    assert catalog.unresolved == []
    for node in catalog.nodes:
        for s in node.sets:
            assert s.set_id is not None


def test_match_insensible_a_tildes_y_enie(catalog):
    # OCR pierde tildes de forma inconsistente y puede bajar la ñ.
    node = catalog.match_title("la torre y el canon")
    assert node is not None
    assert node.titulo_es == "La torre y el cañón"


def test_match_tolera_ruido_ocr_alrededor(catalog):
    # El OCR del título suele capturar iconos/flechas alrededor.
    node = catalog.match_title("  ★ Puños y balas  ▼ ")
    assert node is not None
    assert node.titulo_es == "Puños y balas"


def test_titulo_desconocido_devuelve_none(catalog):
    assert catalog.match_title("Pantalla de resultados del desafío") is None
    assert catalog.match_title("") is None


def test_warn_si_un_en_no_resuelve():
    # Falta 'The Sky Ablaze' en el mapa de sets → ese set queda con set_id None
    # y el catálogo lo reporta en `unresolved` (RNF-02: no inventar).
    ids = _full_set_ids()
    del ids["The Sky Ablaze"]
    cat = FarmNodeCatalog.from_toml(_TOML, ids)
    assert "The Sky Ablaze" in cat.unresolved
    piloto = cat.match_title("El piloto y el meca rebelde")
    assert piloto is not None
    faltante = [s for s in piloto.sets if s.nombre_en == "The Sky Ablaze"][0]
    assert faltante.set_id is None


# --- best_predicted_set_id: fallback de set por predicción cuando el OCR cambia una palabra ---

# Los 2 sets del nodo 'Engaños y baluartes' (ES): id 42 Aria brillante, id 50 Balada de aguas blancas.
_ENGANOS = [(42, "Aria brillante"), (50, "Balada de aguas blancas")]


def test_pred_set_resuelve_palabra_mal_leida():
    """OCR leyó 'Aria radiante' (brillante→radiante, que _norm_key no arregla). Con los 2 sets
    predichos, el correcto gana por lejos → resuelve al id 42 (regresión QA farmeo 2026-07-09)."""
    assert best_predicted_set_id("Aria radiante", _ENGANOS) == 42


def test_pred_set_match_exacto_ish():
    assert best_predicted_set_id("Balada de aguas blancas", _ENGANOS) == 50


def test_pred_set_insensible_a_tildes():
    assert best_predicted_set_id("aria brillante", _ENGANOS) == 42


def test_pred_set_abstiene_si_ninguno_llega_al_piso():
    """Nombre que no se parece a ninguno de los 2 candidatos → None (no adivina)."""
    assert best_predicted_set_id("Fabula Yunkui", _ENGANOS) is None


def test_pred_set_abstiene_si_empatan():
    """Dos candidatos casi equidistantes del OCR (dentro del margen) → None."""
    cands = [(1, "Aria brillante"), (2, "Aria brillante")]  # mismo nombre, distinto id → empate real
    assert best_predicted_set_id("Aria brillante", cands) is None


def test_pred_set_vacio_o_none():
    assert best_predicted_set_id(None, _ENGANOS) is None
    assert best_predicted_set_id("Aria brillante", []) is None

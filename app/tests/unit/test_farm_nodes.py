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


def test_toml_bien_formado():
    """Cada nodo dropea 2 sets, y ni los títulos ni los sets se repiten.

    Un set repetido entre dos nodos no es un typo inofensivo: la predicción de S13 pasaría a
    restringir el matcher a la pareja equivocada, y sin ruido en el log."""
    nodes = _toml_nodes()
    assert len(nodes) == 15                      # v3.1 (2026-09-05): +1 nodo nuevo
    assert all(len(n["sets_en"]) == 2 for n in nodes)
    titulos = [n["titulo_es"] for n in nodes]
    assert len(set(titulos)) == len(titulos), "títulos de nodo repetidos"
    todos = [en for n in nodes for en in n["sets_en"]]
    assert len(set(todos)) == len(todos), "un set aparece en más de un nodo"


def test_matchea_todos_los_titulos_exactos(catalog):
    for n in _toml_nodes():
        node = catalog.match_title(n["titulo_es"])
        assert node is not None, n["titulo_es"]
        assert node.titulo_es == n["titulo_es"]
        assert len(node.sets) == 2


def test_resuelve_todos_los_en_a_set_id(catalog):
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


# --- Cobertura contra el catálogo real de la DB (2026-09-05) ----------------------------------
#
# El nodo de la v3.1 ("Espina veloz y garra desgarradora") estuvo semanas sin cargar y nada lo
# dijo: `farm_nodes.toml` resuelve por `nombre_en`, los dos sets nuevos tenían ese campo en NULL,
# y un set que no está en ningún nodo simplemente no se predice — en silencio. Esto lo vuelve
# ROJO en cuanto un patch agrega sets, que es cuando hace falta enterarse.

_DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


def _sets_de_la_db() -> dict[str, int]:
    import sqlite3
    con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        return {r[1]: r[0] for r in con.execute(
            "SELECT id, nombre_en FROM disc_sets WHERE nombre_en IS NOT NULL")}
    finally:
        con.close()


@pytest.mark.skipif(not _DB.exists(), reason="DB de dominio no presente")
def test_todos_los_sets_de_la_db_pertenecen_a_un_nodo():
    """Cada set del catálogo tiene su nodo. Si sale rojo, llegó un set nuevo sin nodo.

    Mira TODAS las filas, no sólo las que ya tienen `nombre_en`. Filtrar por ese campo sería
    repetir la ceguera que dejó pasar el caso: los dos sets de la v3.1 entraron con `nombre_en`
    NULL, y un set sin nombre inglés no puede estar en ningún nodo **por construcción** — así
    que el test se habría auto-excusado justo en el único caso que tenía que detectar."""
    import sqlite3
    con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        filas = con.execute("SELECT id, nombre, nombre_en FROM disc_sets").fetchall()
    finally:
        con.close()

    sin_en = [f"{r[0]} {r[1]}" for r in filas if not r[2]]
    assert not sin_en, f"sets sin nombre_en (no pueden entrar a ningún nodo): {sin_en}"

    en_nodos = {en for n in _toml_nodes() for en in n["sets_en"]}
    faltan = sorted(f"{r[0]} {r[1]} ({r[2]})" for r in filas if r[2] not in en_nodos)
    assert not faltan, f"sets sin nodo de farmeo: {faltan}"


@pytest.mark.skipif(not _DB.exists(), reason="DB de dominio no presente")
def test_todos_los_sets_del_toml_existen_en_la_db():
    """Y al revés: un `sets_en` que no resuelve deja el nodo a medias, también en silencio."""
    db = set(_sets_de_la_db())
    huerfanos = sorted({en for n in _toml_nodes() for en in n["sets_en"]} - db)
    assert not huerfanos, f"nombres_en del toml que no existen en disc_sets: {huerfanos}"


@pytest.mark.skipif(not _DB.exists(), reason="DB de dominio no presente")
def test_el_nodo_de_la_v31_resuelve_contra_la_db_real():
    """El caso concreto, con los ids reales: Hado emplumado + Rosa espinosa."""
    cat = FarmNodeCatalog.from_toml(_TOML, _sets_de_la_db())
    node = cat.match_title("Espina veloz y garra desgarradora")
    assert node is not None
    assert {s.nombre_en for s in node.sets} == {"Feathered Fate", "Thorned Rose"}
    assert all(s.set_id is not None for s in node.sets)

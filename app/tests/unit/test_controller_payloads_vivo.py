"""Lo que la vista en vivo necesita de los payloads que ya existían (2026-09-12).

Dos agujeros que aparecieron al renderizar la vista con datos reales, no leyendo código:

1. **El drop decía "Nivel ?"** — `_build_payload` (el payload de `disc_detected`, pensado para el
   toast de recomendación) nunca incluyó el nivel, y el valor del principal viajaba sólo como texto
   redondeado (`"30.0%"`). Se suman `nivel`, `main_valor` y `main_unidad`. El toast no los lee.
2. **El W-Engine no tenía ícono** — `weapon_seen` no trae `nombre_en`, y `engine_icon_path` resuelve
   primero por el nombre inglés: sin él, de las 34 armas del inventario con ícono quedaban 3. El
   controller lo resuelve contra el catálogo y manda `icono` y `dueno_avatar` ya armados.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE weapons (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,
                              nombre_en TEXT, rareza TEXT);
        INSERT INTO weapons VALUES (1, 'Rotor de cañón', 'Cannon Rotor', 'A');
        INSERT INTO weapons VALUES (2, 'Tránsito herciano', NULL, 'S');
    """)
    yield c
    c.close()


def _ctrl(con=None):
    from app.ui.controller import MonitorController
    c = MonitorController()
    c._con = con
    return c


def _ev(**kw):
    base = {"nombre": "Rotor de cañón", "en_catalogo": True, "rareza": "A", "nivel": 60,
            "nivel_max": 60, "refinamiento": 5, "stat": "ATQ% 25%", "dueno": None,
            "tenencia": "libre", "cambio": False}
    base.update(kw)
    return base


def _emitido(c, ev):
    recibidos = []
    c.weapon_seen.connect(recibidos.append)
    c._on_weapon_seen_from_monitor(ev)
    assert len(recibidos) == 1
    return recibidos[0]


# --- W-Engine: ícono y avatar -----------------------------------------------------------------

def test_el_arma_trae_su_icono_resuelto_por_el_nombre_ingles(qapp, con):
    p = _emitido(_ctrl(con), _ev())
    assert p["icono"] and p["icono"].endswith("W-Engine_Cannon_Rotor.webp")


def test_sin_nombre_ingles_cae_al_slug_espanol(qapp, con):
    p = _emitido(_ctrl(con), _ev(nombre="Tránsito herciano"))
    assert p["icono"] and p["icono"].endswith("transito_herciano.webp")


def test_arma_desconocida_sin_icono_y_sin_romper(qapp, con):
    p = _emitido(_ctrl(con), _ev(nombre="Arma rara que no existe", en_catalogo=False))
    assert p["icono"] is None
    assert p["nombre"] == "Arma rara que no existe"


def test_el_texto_del_arte_pegado_igual_encuentra_el_icono(qapp, con):
    """La primera versión de este test usaba `Anhelo marcato ESTRUENDO` como "arma sin ícono" — y
    resolvía, con razón: es el caso del texto del arte pegado al nombre (2026-09-11), y el prefijo
    con borde de palabra encuentra `anhelo_marcato.webp`, que ES su ícono."""
    p = _emitido(_ctrl(con), _ev(nombre="Anhelo marcato ESTRUENDO", en_catalogo=False))
    assert p["icono"] and p["icono"].endswith("anhelo_marcato.webp")


def test_sin_conexion_no_rompe_el_evento(qapp):
    """El toast y la vista reciben el evento aunque no se pueda resolver el ícono."""
    p = _emitido(_ctrl(None), _ev(nombre="Tránsito herciano"))
    assert "icono" in p
    assert p["nombre"] == "Tránsito herciano"


def test_el_arma_con_dueno_trae_su_avatar(qapp, con):
    from app.core.asset_resolver import agent_avatar_path
    esperado = agent_avatar_path("Evelyn", variant="ico")
    assert esperado is not None, "la ref de Evelyn tiene que existir para que este test mida algo"
    p = _emitido(_ctrl(con), _ev(dueno="Evelyn", tenencia="equipada"))
    assert p["dueno_avatar"] == str(esperado)


def test_el_arma_libre_no_trae_avatar(qapp, con):
    p = _emitido(_ctrl(con), _ev(dueno=None, tenencia="libre"))
    assert p["dueno_avatar"] is None


def test_el_toast_sigue_recibiendo_lo_de_siempre(qapp, con):
    """Los campos que ya leía el toast no cambian."""
    p = _emitido(_ctrl(con), _ev(cambio=True))
    for k in ("nombre", "en_catalogo", "rareza", "nivel", "nivel_max", "refinamiento", "stat",
              "dueno", "tenencia", "cambio", "tenencia_previa"):
        assert k in p, k


# --- el drop: nivel y valor crudo -------------------------------------------------------------

class _SetRepoVacio:
    def resolve_id(self, _n):
        return None

    def get_all(self):
        return []

    def get_archetypes_for_set(self, _sid):
        return []


def _drop(**kw):
    from app.core.parser_disc import DiscParsed
    base = dict(set_name_raw="Fuego carmesí", set_name_canon="Fuego carmesí", slot=2,
                main_stat_raw="ATK", main_stat_canon="ATK", main_valor=2200.0,
                main_unidad="flat", nivel=0, rareza="S", subs=[], confianza_global=0.9)
    base.update(kw)
    return DiscParsed(**base)


def test_el_drop_trae_nivel_y_valor_crudo(qapp):
    c = _ctrl(None)
    c._disc_set_repo = _SetRepoVacio()
    c._agent_repo = SimpleNamespace(get_all=lambda: [], get_by_id=lambda _i: None)
    c._archetype_repo = SimpleNamespace(get_all=lambda: [], get_by_id=lambda _i: None)
    c._scoring_ctx = None
    p = c._build_payload(_drop(), SimpleNamespace(code="S3"))
    assert p["nivel"] == 0, "el nivel 0 es un nivel, no un None"
    assert p["main_valor"] == 2200.0
    assert p["main_unidad"] == "flat"


def test_la_vista_prefiere_los_campos_crudos_del_drop():
    from app.ui.live.view import drop_como_observacion
    o = drop_como_observacion({"set": "X", "slot": 2, "rarity": "S", "main": "Ataque %",
                               "main_value": "30.0%", "main_valor": 30.4, "main_unidad": "%",
                               "nivel": 9, "subs_detail": []})
    assert o["main_valor"] == 30.4, "el texto redondeado perdía el decimal"
    assert o["nivel"] == 9

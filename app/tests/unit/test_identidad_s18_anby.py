"""QA en vivo del 2026-09-25: la ficha de Anby se guardó en la fila de N.º 0: Anby.

Daniel pasó por la ficha de Anby ("Anby Demara", Eléctrico, Aturdidor) para registrar sus stats
después de un swap, y `agent_sync` escribió PV 11.385 / ATK 1.150 / Impacto 160 en N.º 0: Anby
(ATK 2.909, Impacto 93). Se restauró desde el backup. Dos causas, las dos en este texto:

1. El rol. El OCR leyó "pV" y no leyó "MAX": el banner se cortaba en "PV" con mayúsculas, así que
   no se cortó, tomó 200 caracteres con la etiqueta "Ataque 1150", y "ataque" se busca antes que
   "aturdidor" → rol Ataque (el de N.º 0).
2. El nombre. "0 Ciudad" y el subtítulo espaciado "A n b y" traen sueltas la "n" y el "0": las
   palabras de "N.º 0: Anby" parecían leídas enteras, y la regla de DOMINADOS (Billy vs Billy
   Estelar) sacó a Anby de los candidatos. Con el rol bien leído, N.º 0 igual ganaba.
Cada causa sola alcanzaba para el error.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core import parser_agent_stats as p
from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH

#: OCR full-frame de Paddle sobre el S18 de Anby en vivo (2026-09-25), tal cual.
OCR_ANBY = (
    "0 Ciudad GUIDE THE INTERNAL SPA A Liebres Astutas Anby Demara W A n b y Aturdidor Nivel 60 "
    "Eléctrico pV 11 385 Ataque 1150 Defensa 1047 Impacto 160 Probabilidad de 48.2 % Dao Critico "
    "69.2 % Critico Tasa de Anomalia 94 Maestria de Anomalia 129 0 % Recuperación de Tasa de "
    "Perforacion 1.2 Energia Atributos secundarios Preparaciön 19 activos para el combate CINENA 6/6 "
    "Atributos base Habilidades Equipamiento"
)


def test_el_banner_se_corta_en_pv_aunque_venga_en_minuscula():
    banner = p._banner_rol_elem_region(OCR_ANBY)
    assert "Ataque" not in banner
    assert p._canon_rol(banner) == "Aturdimiento"
    assert p._canon_elemento(banner) == "Eléctrico"


@pytest.mark.parametrize("texto", ["Nivel 60 MAX Eléctrico Aturdidor PV 11 385 Ataque 1150",
                                   "Nivel 60 Eléctrico Aturdidor Pv 11 385 Ataque 1150"])
def test_el_corte_sigue_andando_con_pv_en_mayuscula(texto):
    assert p._canon_rol(p._banner_rol_elem_region(texto)) == "Aturdimiento"


@pytest.fixture
def roster_sin_stats(monkeypatch):
    """El roster real, recargado, y SIN la identificación por stats: una vez guardada la ficha de
    Anby, la capa por stats la reconocería sola y este test no probaría el nombre."""
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    monkeypatch.setattr(p, "_ROSTER_CACHE", None)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None)
    monkeypatch.setattr(p, "_identify_by_stats", lambda _stats: None)
    yield
    p._ROSTER_CACHE = None
    p._NO_POSEIDOS_CACHE = None


def test_letras_sueltas_no_dominan_a_anby(roster_sin_stats):
    """Con el rol BIEN leído (el arreglo 1 no alcanza): la "n" y el "0" sueltos no la dominan."""
    assert p._match_agent(p._name_region(OCR_ANBY), "Aturdimiento", "Eléctrico")[0] == "Anby"


def test_billy_estelar_sigue_dominando_a_billy(roster_sin_stats):
    """La regla de DOMINADOS sigue viva para palabras enteras (QA 2026-09-24)."""
    assert p._match_agent("Billy Kid Estelar", "Ataque", "Físico")[0] == "Billy Estelar"


class _Ocr:
    def text(self, img, psm=None):
        return ("", 0.0) if psm == 7 else (OCR_ANBY, 0.97)


def test_la_ficha_de_anby_sale_identificada(roster_sin_stats):
    r = p.parse_agent_stats(np.zeros((1440, 2560, 3), np.uint8), _Ocr())
    assert (r.agente_nombre, r.rol, r.elemento) == ("Anby", "Aturdimiento", "Eléctrico")

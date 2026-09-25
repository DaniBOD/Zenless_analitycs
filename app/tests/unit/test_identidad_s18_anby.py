"""QA en vivo del 2026-09-25: la ficha de Anby se guardó en la fila de N.º 0: Anby.

Daniel pasó por la ficha de Anby ("Anby Demara", Eléctrico, Aturdidor) para registrar sus stats
después de un swap, y `agent_sync` escribió PV 11.385 / ATK 1.150 / Impacto 160 en N.º 0: Anby
(ATK 2.909, Impacto 93). Se restauró desde el backup. Dos causas, las dos en este texto:

1. El rol. El OCR leyó "pV" y no leyó "MAX": el banner se cortaba en "PV" con mayúsculas, así que
   no se cortó, tomó 200 caracteres con la etiqueta "Ataque 1150", y "ataque" se busca antes que
   "aturdidor" → rol Ataque (el de N.º 0).
"""
from __future__ import annotations

import pytest

from app.core import parser_agent_stats as p

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

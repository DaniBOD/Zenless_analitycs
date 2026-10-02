"""Los rolls de un substat del panel DETAIL de S22 salen del VALOR, no del "+N" chiquito.

QA en vivo 2026-10-02 10:34: el Obtenido leyó "Maestría de Anomalía 18" con 0 rolls; vale 9 por
mejora, así que son 1. Con el roll mal, la memoria de la tanda no reconoció al #443 ya mejorado y
lo insertó otra vez (#444). El valor se lee bien; el "+1" es un glifo de pocos píxeles.
La tabla es `VALOR_POR_MEJORA` (medida sobre 386 discos, una sola autoridad).
"""
from __future__ import annotations

import pytest

from app.core import parser_extraccion as pe
from app.core.parser_disc import DiscParsed, SubstatParsed


def _disc(subs) -> DiscParsed:
    return DiscParsed(set_name_raw="Hado emplumado", set_name_canon=None, slot=3,
                      main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0,
                      main_unidad="flat", nivel=15, rareza="S",
                      subs=[SubstatParsed(n, n, v, u, r, 0.95) for n, v, u, r in subs])


def test_el_caso_del_444():
    d = _disc([("ATK%", 9.0, "%", 2), ("Maestría de Anomalía", 18.0, "flat", 0),
               ("ATK", 38.0, "flat", 1), ("Perforación", 9.0, "flat", 0)])
    pe._rolls_desde_valor(d)
    assert [s.rolls for s in d.subs] == [2, 1, 1, 0]


@pytest.mark.parametrize("nombre, valor, unidad, rolls", [
    ("Prob. Crítica", 12.0, "%", 4), ("Daño Crítico", 9.6, "%", 1), ("DEF%", 4.8, "%", 0),
    ("HP", 336.0, "flat", 2), ("DEF", 45.0, "flat", 2), ("HP%", 6.0, "%", 1),
])
def test_cada_stat_con_su_valor_por_mejora(nombre, valor, unidad, rolls):
    d = _disc([(nombre, valor, unidad, 0)])
    pe._rolls_desde_valor(d)
    assert d.subs[0].rolls == rolls


def test_un_valor_que_no_divide_limpio_deja_lo_que_leyo_el_ocr():
    """28 de ATK = 1,47 mejoras (mala lectura u otro rango): no se inventa un roll (RNF-02)."""
    d = _disc([("ATK", 28.0, "flat", 1)])
    pe._rolls_desde_valor(d)
    assert d.subs[0].rolls == 1


@pytest.mark.parametrize("sub", [
    ("ATK", None, "flat", 2),                 # sin valor
    ("Impacto", 18.0, "flat", 1),             # no está en la tabla
    ("ATK", 19.0 * 8, "flat", 3),             # 7 mejoras: imposible (máximo 5)
])
def test_sin_dato_confiable_no_se_toca(sub):
    d = _disc([sub])
    pe._rolls_desde_valor(d)
    assert d.subs[0].rolls == sub[3]


def test_parse_detail_disc_los_aplica(monkeypatch):
    import app.core.parser_disc_s17 as s17
    monkeypatch.setattr(pe, "_read_detail_title", lambda _f, _o: ("Hadoemplumado", 3))
    monkeypatch.setattr(s17, "_parse_s17_from_lines",
                        lambda *a, **k: _disc([("Maestría de Anomalía", 18.0, "flat", 0)]))

    class _Ocr:
        def text_with_bboxes(self, _img):
            return []

    import numpy as np
    d = pe.parse_detail_disc(np.zeros((1440, 2560, 3), np.uint8), _Ocr())
    assert d.subs[0].rolls == 1

"""La mejora se escribe EN VIVO desde S10, nivel por nivel (Daniel, 2026-10-02).

"el sistema recién detecta y cambia los stats a la hora de finalizar la mejora … si mejoro al lv 3
no me dan cambio porque se usan todos; debe detectar el nivel y constantemente verificar las stats
en la pestaña de mejora y ahí mismo actualizar la db". El caso: #431 se vio subir 0→3 en S10
(10:38:43), la captura se reinició 40 s después y la fila quedó en Nv 0.

Cada paso exige una lectura coherente con lo que la fila tiene escrito: mismo disco
(`es_el_mismo_disco`) y lo que dan los umbrales cruzados (#substats + Σrolls − nivel//3 constante,
medido en 426 de 427 discos de la DB).
"""
from __future__ import annotations

import numpy as np

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.core.sync_upgrade import UpgradeSyncer, _crecimiento, _paso_coherente


def _sub(canon, valor, rolls):
    return SubstatParsed(canon, canon, valor, "%" if canon.endswith("%") else "flat", rolls, 1.0)


def _disc(nivel, subs, main_valor=79.0):
    return DiscParsed(set_name_raw="Hado emplumado", set_name_canon=None, slot=2,
                      main_stat_raw="ATK", main_stat_canon="ATK", main_valor=main_valor,
                      main_unidad="flat", nivel=nivel, rareza="S", subs=subs)


# El #431 de la sesión del 2026-10-02 (S10 10:38:42 → 10:38:43).
NV0 = _disc(0, [_sub("Maestría de Anomalía", 9, 0), _sub("HP%", 3, 0), _sub("ATK%", 3, 0)])
NV3 = _disc(3, [_sub("Maestría de Anomalía", 9, 0), _sub("HP%", 3, 0), _sub("ATK%", 3, 0),
                _sub("DEF", 15, 0)], 126.0)
NV6 = _disc(6, [_sub("Maestría de Anomalía", 18, 1), _sub("HP%", 3, 0), _sub("ATK%", 3, 0),
                _sub("DEF", 15, 0)], 173.0)
NV9 = _disc(9, [_sub("Maestría de Anomalía", 18, 1), _sub("HP%", 6, 1), _sub("ATK%", 3, 0),
                _sub("DEF", 15, 0)], 220.0)
NV15 = _disc(15, [_sub("Maestría de Anomalía", 27, 2), _sub("HP%", 6, 1), _sub("ATK%", 6, 1),
                  _sub("DEF", 15, 0)], 316.0)


class _SyncerEspia:
    def __init__(self, resultado=7):
        self.llamadas = []
        self.resultado = resultado

    def actualizar_por_mejora(self, pre, post):
        self.llamadas.append((pre.nivel, post.nivel))
        return self.resultado


def _modal(monkeypatch, lecturas, espia=None):
    """Entra a S10 con la primera lectura y pasa un ciclo por cada una de las siguientes (la barra
    de nivel cambia en cada una → se re-parsea)."""
    espia = espia or _SyncerEspia()
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append, disc_syncer=espia)
    it = iter(lecturas)
    monkeypatch.setattr(s, "_safe_parse", lambda _f: next(it))
    sigs = iter(range(1000))
    monkeypatch.setattr(s, "_level_sig", lambda _f: np.full((32, 32), next(sigs) * 10.0, np.float32))
    s.on_s10_enter(None)
    for _ in lecturas[1:]:
        s.on_s10_update(None)
    return s, espia, diags


def test_el_caso_del_431_se_escribe_al_verlo_subir(monkeypatch):
    """Sin salir del modal ni esperar el vuelto de materiales: la fila ya está en Nv 3."""
    s, espia, _d = _modal(monkeypatch, [NV0, NV3])
    assert espia.llamadas == [(0, 3)]
    assert s._pending is None, "todavía en S10: el pendiente nace recién al salir"


def test_cada_paso_matchea_contra_lo_que_ya_se_escribio(monkeypatch):
    _s, espia, _d = _modal(monkeypatch, [NV0, NV3, NV6, NV9])
    assert espia.llamadas == [(0, 3), (3, 6), (6, 9)]


def test_una_lectura_que_no_cuadra_no_se_escribe(monkeypatch):
    """Nv 6 sin el roll que dan los umbrales (un "+N" perdido o un frame de animación)."""
    mal = _disc(6, NV3.subs, 173.0)
    _s, espia, diags = _modal(monkeypatch, [NV0, NV3, mal])
    assert espia.llamadas == [(0, 3)]
    assert any("no cuadra" in d for d in diags), diags


def test_si_la_fila_no_se_encontro_el_siguiente_paso_reintenta_desde_el_pre(monkeypatch):
    """Equipado, gemelos o no capturado: lo escrito no avanza y no se finge que sí."""
    _s, espia, _d = _modal(monkeypatch, [NV0, NV3, NV6], espia=_SyncerEspia(resultado=None))
    assert espia.llamadas == [(0, 3), (0, 6)]


def test_la_pantalla_posterior_matchea_contra_el_ultimo_paso_escrito(monkeypatch):
    """Al maxear el modal se cierra solo y el 15 lo confirma S17/S5/S9: el PRE ya no está en la
    fila, está el Nv 9 que escribió S10."""
    s, espia, diags = _modal(monkeypatch, [NV0, NV3, NV6, NV9])
    s.on_s10_exit()
    s.on_post_upgrade_disc(NV15, now=s._pending[3] + 1)
    assert espia.llamadas[-1] == (9, 15)
    assert any("resumen: nivel 0→15" in d for d in diags), diags


def test_sin_disc_syncer_sigue_siendo_display_only(monkeypatch):
    s = UpgradeSyncer(ocr=None, on_diagnostic=lambda _m: None)
    it = iter([NV0, NV3])
    monkeypatch.setattr(s, "_safe_parse", lambda _f: next(it))
    sigs = iter(range(10))
    monkeypatch.setattr(s, "_level_sig", lambda _f: np.full((32, 32), next(sigs) * 10.0, np.float32))
    s.on_s10_enter(None)
    s.on_s10_update(None)          # no revienta


def test_crecimiento_constante_al_subir():
    assert [_crecimiento(d) for d in (NV0, NV3, NV6, NV9, NV15)] == [3, 3, 3, 3, 3]


def test_paso_coherente():
    assert _paso_coherente(NV0, NV3)
    assert _paso_coherente(NV3, NV15)                      # varios umbrales de una
    assert not _paso_coherente(NV3, _disc(6, NV3.subs))    # falta el roll del Nv 6
    assert not _paso_coherente(NV6, NV3)                   # baja de nivel

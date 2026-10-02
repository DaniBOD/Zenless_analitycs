"""El "Ver" (S6/S7) y el inventario (S9) confirman una mejora (SPEC 2026-10-02, puntos 3 y 5).

QA en vivo 2026-10-02: las mejoras empezadas desde el "Ver" terminan en el "Ver"
(S7 → S10 → S20 → S7) y el usuario después mira el disco en S9. Ninguna de las dos confirmaba: la
fila quedaba en Nv 0 y S9 insertaba otra (fantasmas #409, #411, #413).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState
from app.core.parser_disc import DiscParsed, SubstatParsed


class _SyncerEspia:
    def __init__(self):
        self.vistos = []

    def on_post_upgrade_disc(self, disc, now=None):
        self.vistos.append(disc)


def _disc(nivel=3, subs=4, conf=0.95):
    nombres = ["Maestría de Anomalía", "Prob. Crítica", "DEF", "DEF%"][:subs]
    return DiscParsed(set_name_raw="Hado emplumado", set_name_canon="Hado emplumado", slot=1,
                      main_stat_raw="PV", main_stat_canon="HP", main_valor=990.0,
                      main_unidad="flat", nivel=nivel, rareza="S", confianza_global=conf,
                      subs=[SubstatParsed(n, n, 1.0, "flat", 0, 0.95) for n in nombres])


@pytest.fixture
def monitor():
    import app.core.monitor as mon_mod
    m = mon_mod.Monitor(ocr=object(), detector=None)
    m._upgrade_syncer = _SyncerEspia()
    return m


def _ver(monitor, monkeypatch, disc, code="S7"):
    import app.core.parser_disc_s3 as s3
    monkeypatch.setattr(s3, "parse_disc_s7", lambda _f, _o: disc)
    monitor._process_disc(np.zeros((10, 10, 3), np.uint8), ScreenState(code, 1.0, code.lower()))


@pytest.mark.parametrize("code", ["S6", "S7"])
def test_el_ver_con_el_disco_maduro_confirma(monitor, monkeypatch, code):
    d = _disc()
    _ver(monitor, monkeypatch, d, code)
    assert monitor._upgrade_syncer.vistos == [d]


def test_el_ver_con_el_disco_a_medio_leer_no_confirma(monitor, monkeypatch):
    """Nv 3 exige 4 substats: con 3 leídos el disco no está maduro (RNF-02)."""
    _ver(monitor, monkeypatch, _disc(nivel=3, subs=3))
    assert monitor._upgrade_syncer.vistos == []


def test_el_ver_con_confianza_baja_no_confirma(monitor, monkeypatch):
    _ver(monitor, monkeypatch, _disc(conf=0.5))
    assert monitor._upgrade_syncer.vistos == []


def test_el_inventario_confirma_aunque_el_dedup_corte_la_emision(monitor):
    d = _disc()
    estado = ScreenState("S9", 1.0, "s9")
    monitor._emit_s9_disc(d, estado)
    monitor._emit_s9_disc(d, estado)               # repetido: el dedup corta la emisión
    assert monitor._upgrade_syncer.vistos == [d, d]


def test_sin_syncer_no_rompe(monitor, monkeypatch):
    monitor._upgrade_syncer = None
    _ver(monitor, monkeypatch, _disc())
    monitor._emit_s9_disc(_disc(), ScreenState("S9", 1.0, "s9"))

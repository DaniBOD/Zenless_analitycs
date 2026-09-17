"""Despacho rápido en S9 con confirmación de panel quieto.

**El problema** (Pasada A del censo, 2026-09-16): del click a la línea del log pasaban ~3,1 s (p50),
y ~1 s de eso era esperar a que la cadencia habilitara el despacho, aunque el loop ya había visto
el disco nuevo.

**Por qué no alcanza con despachar en el acto**: el despacho lee el MISMO frame en que el loop vio
el cambio, y ese frame puede estar a mitad de la animación del panel. La espera de cadencia le daba
tiempo al panel a asentarse sin querer — por eso aquella pasada dio 0 lecturas descartadas en 10
discos —, y leer el frame animado podía costar una lectura de ~1,9 s para tirarla.

**La regla**: la pasada que VE el disco nuevo no lo lee. La siguiente compara la firma ANTES de
clasificar: si coincide, el panel está quieto y se lee ya, salteando el `classify` de esa pasada.

Los tests del loop corren el `_run` VERDADERO (ver `arnes_loop_monitor.py`). La cadencia está en 0:
todo despacho que falta es una decisión del loop, no una espera. Con 3 pasadas el buffer temporal
confirma S9, así que la pasada 3 despacha el primer disco en todos los casos.
"""
from __future__ import annotations

import pytest

from app.core.detector import ScreenDetector, ScreenState
from app.core.monitor import Monitor, _S9_CONFIRMACION_MAX
from app.tests.unit.arnes_loop_monitor import correr_loop, firma

A, B, C, D, E = 0.0, 255.0, 120.0, 60.0, 190.0


class _DummyOcr:
    def text(self, *a, **kw):
        return "", 0.0

    def number(self, *a, **kw):
        return 0.0, 0.0


@pytest.fixture
def mon(monkeypatch):
    monkeypatch.delenv("DANIBOD_S9_DESPACHO_RAPIDO", raising=False)
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    return Monitor(ocr=_DummyOcr(), detector=ScreenDetector())


# --- el loop verdadero ---------------------------------------------------------------------------

def test_el_disco_nuevo_se_lee_en_la_pasada_siguiente_sin_classify(monkeypatch, mon):
    """Pasada 4 VE el disco B: no lo lee (su frame puede estar animando). Pasada 5 confirma la
    misma firma: lo lee YA y no clasifica."""
    reg = correr_loop(monkeypatch, mon, firmas=[A, A, A, B, B])
    assert reg.despachados == [3, 5]
    assert reg.clasificados == [1, 2, 3, 4], "la pasada de confirmación no debía clasificar"


def test_con_el_interruptor_apagado_el_loop_es_el_de_antes(monkeypatch):
    """`DANIBOD_S9_DESPACHO_RAPIDO=0` tiene que dejar el comportamiento EXACTO de antes: la pasada
    que ve el disco lo despacha y todas clasifican. Es la salida si la Pasada B sale mal."""
    monkeypatch.setenv("DANIBOD_S9_DESPACHO_RAPIDO", "0")
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    m = Monitor(ocr=_DummyOcr(), detector=ScreenDetector())
    reg = correr_loop(monkeypatch, m, firmas=[A, A, A, B, B])
    assert reg.despachados == [3, 4, 5]
    assert reg.clasificados == [1, 2, 3, 4, 5]


def test_si_el_panel_sigue_animando_espera_a_que_se_quede_quieto(monkeypatch, mon):
    """B en la pasada 4, C en la 5 (todavía anima): ninguna de las dos se lee. En la 6 la firma
    repite C: recién ahí se lee, sin classify."""
    reg = correr_loop(monkeypatch, mon, firmas=[A, A, A, B, C, C])
    assert reg.despachados == [3, 6]
    assert reg.clasificados == [1, 2, 3, 4, 5]


def test_un_panel_que_nunca_se_queda_quieto_vuelve_a_la_cadencia(monkeypatch, mon):
    """Sin el tope, un panel que no se asienta suprimiría el despacho para siempre y el disco no se
    leería nunca: peor que antes. Con el tope, tras `_S9_CONFIRMACION_MAX` cambios seguidos se
    abandona la confirmación y el loop vuelve a despachar como siempre."""
    assert _S9_CONFIRMACION_MAX == 3, "el guion de abajo asume 3"
    reg = correr_loop(monkeypatch, mon, firmas=[A, A, A, B, C, D, E, E])
    assert reg.despachados == [3, 7, 8], reg
    assert mon._s9_rapido_abandonados == 1


def test_el_mismo_disco_quieto_no_se_despacha_de_mas(monkeypatch, mon):
    """Sin disco nuevo no hay confirmación que valga: con la firma quieta el loop despacha por
    cadencia como siempre (cada pasada, porque en el arnés la cadencia es 0) y clasifica siempre."""
    reg = correr_loop(monkeypatch, mon, firmas=[A, A, A, A, A])
    assert reg.clasificados == [1, 2, 3, 4, 5]
    assert mon._s9_rapido_confirmados == 0


# --- las dos piezas, sueltas ----------------------------------------------------------------------

def test_ver_un_disco_nuevo_lo_deja_pendiente_y_marca_la_pasada(monkeypatch, mon):
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda f: firma(A))
    mon._s9_mirar_disco_en_loop(None)
    assert mon._s9_pendiente and mon._s9_recien_visto


def test_sin_s9_confirmado_no_se_confirma_nada(monkeypatch, mon):
    """Si la pantalla confirmada ya no es S9, una firma parecida no alcanza para saltear el
    classify: la pasada tiene que clasificar."""
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda f: firma(A))
    mon._s9_mirar_disco_en_loop(None)
    mon._confirmed_state = ScreenState("S17", 0.95, "t")
    assert mon._s9_confirmar_pendiente(None) is None
    assert mon._s9_pendiente is False


def test_sin_firma_no_se_confirma(monkeypatch, mon):
    firmas = iter([firma(A), None])
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda f: next(firmas))
    mon._s9_mirar_disco_en_loop(None)
    mon._confirmed_state = ScreenState("S9", 0.95, "t")
    assert mon._s9_confirmar_pendiente(None) is None
    assert mon._s9_pendiente is False


def test_salir_de_S9_suelta_la_confirmacion(monkeypatch, mon):
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda f: firma(A))
    mon._s9_mirar_disco_en_loop(None)
    mon._reset_s9_disc_tracking()
    assert not mon._s9_pendiente and not mon._s9_recien_visto

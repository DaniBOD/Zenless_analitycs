"""Cableado de S30 (inventario de amplificadores) en el monitor — RF-15 tramo 2.

Se stubbea el parser: la lectura real está cubierta contra los 6 fixtures en
`test_parser_weapon_s30`. Acá se prueba la ORQUESTACIÓN, que es donde el proyecto tuvo sus bugs
históricos: handlers mudos en un `return` temprano y estados que no se resetean al salir.

Lo que distingue a S30 de S26, y es el contrato que fijan estos tests:

  · **No emite toast.** Recorrer una grilla es lectura, no novedad — el criterio de Daniel es que
    un toast avisa de CAMBIOS. En S26 abrir un arma sí emite; acá no debe emitir nunca.
  · **No escribe la DB.** Observación pura, igual que S26.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState

_S30 = ScreenState("S30", 0.86, "s9_inventario_general.png")
_S9 = ScreenState("S9", 0.98, "s9_inventario_general.png")
_S12 = ScreenState("S12", 0.0, None)


def _frame(fill: int = 40):
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


class FakeWeapon:
    def __init__(self, nombre="Uitimacena", canon="Última cena", rareza="A", refin=5):
        self.nombre_raw, self.nombre_canon = nombre, canon
        self.nivel, self.nivel_max = 60, 60
        self.rareza, self.refinamiento = rareza, refin
        self.atk_base = 594
        self.stat_avanzado_canon, self.stat_avanzado_valor = "Recarga de Energía", 50.0
        self.stat_avanzado_unidad = "%"
        self.pill_bbox = (1944, 546, 2139, 579)
        self.confianza, self.notas = 0.98, []


@pytest.fixture
def mon(monkeypatch):
    import app.core.monitor as mon_mod
    import app.core.parser_weapon_s26 as pw_mod

    diags: list[str] = []
    toasts: list[dict] = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        set_badge_matcher=object(), on_weapon_seen=toasts.append)
    m._diags, m._toasts = diags, toasts
    m._stub = {"weapon": FakeWeapon(), "sig": b"A"}
    monkeypatch.setattr(pw_mod, "parse_weapon_s30",
                        lambda fr, ocr, catalogo=None: m._stub["weapon"])
    monkeypatch.setattr(pw_mod, "weapon_panel_signature_s30", lambda fr: m._stub["sig"])
    monkeypatch.setattr(m, "_weapon_catalog", lambda: ["Última cena"])
    m._identifier = None
    return m


def _paso(m, state, **stub):
    m._stub.update(stub)
    m._dispatch_state(_frame(), state)


def _lineas(m):
    return [d for d in m._diags if d.startswith("[S30]")]


# --- El camino normal -------------------------------------------------------------------------

def test_loguea_el_arma_seleccionada(mon):
    _paso(mon, _S30)
    assert len(_lineas(mon)) == 1, mon._diags
    linea = _lineas(mon)[0]
    assert "Última cena" in linea            # el CANÓNICO, no el crudo del OCR
    assert "Uitimacena" not in linea
    assert "A" in linea and "Nv 60/60" in linea and "P5" in linea and "594" in linea


def test_no_emite_toast_nunca(mon):
    """El contrato que separa esta pantalla de S26: recorrer la grilla es lectura, no novedad.
    Un toast por tile sería exactamente lo que Daniel vetó."""
    for sig in (b"A", b"B", b"C"):
        _paso(mon, _S30, sig=sig, weapon=FakeWeapon())
    assert len(_lineas(mon)) == 3
    assert mon._toasts == [], "S30 no debe interrumpir"


def test_panel_quieto_no_reocrea(mon):
    """El OCR del panel cuesta ~500 ms; sin el gate, quedarse en la grilla sería un OCR por ciclo
    (RNF-06)."""
    import app.core.parser_weapon_s26 as pw_mod
    llamadas = {"n": 0}

    def _contando(fr, ocr, catalogo=None):
        llamadas["n"] += 1
        return mon._stub["weapon"]
    pw_mod.parse_weapon_s30 = _contando

    for _ in range(5):
        _paso(mon, _S30)
    assert llamadas["n"] == 1
    assert len(_lineas(mon)) == 1


def test_al_cambiar_de_arma_vuelve_a_leer(mon):
    _paso(mon, _S30)
    _paso(mon, _S30, sig=b"B", weapon=FakeWeapon(canon="Llanto mielgo"))
    assert len(_lineas(mon)) == 2
    assert "Llanto mielgo" in _lineas(mon)[-1]


def test_salir_de_la_pantalla_olvida_la_firma(mon):
    """Si no, volver al inventario con la misma arma seleccionada quedaría mudo."""
    _paso(mon, _S30)
    _paso(mon, _S12)
    assert mon._s30_panel_sig is None
    _paso(mon, _S30)
    assert len(_lineas(mon)) == 2


# --- Los returns tempranos DECLARAN ------------------------------------------------------------

def test_panel_ilegible_no_queda_mudo(mon, caplog):
    """La lección de los 8m42s sin una línea de log: un handler que se va por un `return` temprano
    tiene que decir por qué. El trabe se anota por FLANCO (`_note_stall`), que va al log y queda
    registrado en `_stalls` — no al panel de diagnóstico."""
    malo = FakeWeapon()
    malo.nombre_raw, malo.nivel, malo.notas = "", None, ["panel_vacio"]
    with caplog.at_level("INFO", logger="app.core.monitor"):
        _paso(mon, _S30, weapon=malo)
    assert _lineas(mon) == []
    assert "S30/inventario" in mon._stalls
    assert "panel_vacio" in mon._stalls["S30/inventario"][0]
    assert any("S30/inventario" in r.getMessage() for r in caplog.records), caplog.text


def test_al_destrabarse_lo_dice(mon, caplog):
    """La contracara del flanco: si solo se anotara el trabe, un handler que se recupera dejaría
    al usuario creyendo que sigue roto."""
    malo = FakeWeapon()
    malo.nombre_raw, malo.nivel = "", None
    _paso(mon, _S30, weapon=malo)
    with caplog.at_level("INFO", logger="app.core.monitor"):
        _paso(mon, _S30, sig=b"B", weapon=FakeWeapon())
    assert "S30/inventario" not in mon._stalls
    assert any("destrabado" in r.getMessage() for r in caplog.records), caplog.text


def test_arma_fuera_del_catalogo_se_marca(mon):
    """`weapons` tiene 42 armas de menos: un nombre sin canonizar es información, no un fallo.
    Se muestra el crudo y se avisa — nunca se da de alta sola (RNF-01/02)."""
    suelta = FakeWeapon(nombre="Arma que no esta", canon=None)
    _paso(mon, _S30, weapon=suelta)
    linea = _lineas(mon)[0]
    assert "Arma que no esta" in linea and "fuera del catálogo" in linea


# --- Observación pura --------------------------------------------------------------------------

def test_no_escribe_la_db(mon):
    """Mismo contrato que S26. El flujo de armas es display-only hasta que se ate al censo."""
    escrituras = []
    mon._repo = type("R", (), {"__getattr__": lambda s, n: (lambda *a, **k: escrituras.append(n))})()
    for sig in (b"A", b"B"):
        _paso(mon, _S30, sig=sig, weapon=FakeWeapon())
    assert escrituras == []


def test_el_inventario_de_discos_no_pasa_por_este_handler(mon):
    """S9 y S30 comparten template; si el ruteo se aflojara, el handler de armas leería discos."""
    _paso(mon, _S9)
    assert _lineas(mon) == []

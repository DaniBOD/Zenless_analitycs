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
    # `badge=None` por defecto: sin lectura del avatar el handler dice "dueño ?" y los tests que
    # no hablan del dueño no dependen de él.
    m._stub = {"weapon": FakeWeapon(), "sig": b"A", "badge": None}
    monkeypatch.setattr(pw_mod, "parse_weapon_s30",
                        lambda fr, ocr, catalogo=None: m._stub["weapon"])
    monkeypatch.setattr(pw_mod, "weapon_panel_signature_s30", lambda fr: m._stub["sig"])
    monkeypatch.setattr(pw_mod, "read_weapon_owner_badge_s30", lambda fr, pb: m._stub["badge"])
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
    for sig, canon in ((b"A", "Última cena"), (b"B", "Llanto mielgo"), (b"C", "Petrazufre")):
        _paso(mon, _S30, sig=sig, weapon=FakeWeapon(canon=canon))
    assert len(_lineas(mon)) == 3, "tres armas DISTINTAS son tres lecturas"
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


# --- El log dice CAMBIOS, no lecturas ----------------------------------------------------------

def test_no_repite_la_linea_si_lo_leido_no_cambio(mon):
    """REGRESIÓN del QA 2026-08-07: **110 líneas de log para 9 armas distintas**.

    El gate de firma es de PÍXELES y no alcanza: cualquier temblor del panel lo cruza y el
    handler vuelve a parsear. Si además se loguea sin mirar el contenido, el log deja de ser
    edge-triggered y se vuelve un heartbeat que repite la misma arma cada ciclo.
    """
    for sig in (b"A", b"B", b"C", b"D"):      # firma distinta cada vez: el OCR sí corre
        _paso(mon, _S30, sig=sig)             # ...pero devuelve SIEMPRE la misma arma
    assert len(_lineas(mon)) == 1, _lineas(mon)


def test_vuelve_a_loguear_si_cambia_un_solo_campo(mon):
    """La contracara: el dedup no puede tragarse un cambio real. Mismo nombre y mismo nivel, pero
    otro refinamiento, es un arma distinta de la grilla."""
    _paso(mon, _S30)
    otra = FakeWeapon()
    otra.refinamiento = 3
    _paso(mon, _S30, sig=b"B", weapon=otra)
    assert len(_lineas(mon)) == 2


def test_salir_de_la_pantalla_olvida_tambien_el_dedup_del_log(mon):
    """Si no, volver al inventario con la misma arma seleccionada quedaría mudo."""
    _paso(mon, _S30)
    _paso(mon, _S12)
    assert mon._s30_last_log_sig is None
    _paso(mon, _S30)
    assert len(_lineas(mon)) == 2


# --- Dueño --------------------------------------------------------------------------------------

def _badge(present=True, crop=True):
    from app.core.parser_weapon_s26 import OwnerBadge
    return OwnerBadge(present=present, nitidez=0.0,
                      crop=(np.zeros((40, 40, 3), dtype=np.uint8) if crop else None))


def test_sin_avatar_el_arma_sale_libre(mon):
    _paso(mon, _S30, badge=_badge(present=False, crop=False))
    assert "LIBRE" in _lineas(mon)[0]


def test_con_avatar_reconocido_nombra_al_pj(mon):
    class _Res:
        name, conf = "Vivian", 0.92

    class _Ident:
        surfaces = {"detail": type("S", (), {"match": staticmethod(lambda c: _Res())})()}

        @staticmethod
        def _canonical_name(n):
            return n
    mon._identifier = _Ident()
    _paso(mon, _S30, badge=_badge())
    assert "la tiene Vivian" in _lineas(mon)[0]


def test_con_avatar_pero_sin_librería_dice_que_hay_alguien(mon):
    """"Hay alguien, no sé quién" es una salida legítima, no un fallo: `BadgeSurface` separa
    presencia de nombrado a propósito. Degradarlo a LIBRE sería mentir sobre el estado del arma."""
    mon._identifier = None
    _paso(mon, _S30, badge=_badge())
    linea = _lineas(mon)[0]
    assert "sin identificar" in linea and "LIBRE" not in linea


def test_un_nombre_que_no_resuelve_al_roster_se_descarta(mon):
    """La librería del detalle tiene labels con mojibake. Antes 'incierto' que basura (RNF-02)."""
    class _Res:
        name, conf = "n.\xc2\xba11", 0.9

    class _Ident:
        surfaces = {"detail": type("S", (), {"match": staticmethod(lambda c: _Res())})()}

        @staticmethod
        def _canonical_name(n):
            return None          # no resuelve
    mon._identifier = _Ident()
    _paso(mon, _S30, badge=_badge())
    linea = _lineas(mon)[0]
    assert "sin identificar" in linea and "n." not in linea.split("—")[1].split("·")[0]


def test_cambiar_de_dueno_re_loguea_aunque_el_arma_sea_la_misma(mon):
    """Dos copias del mismo modelo de arma, una libre y otra equipada, son filas distintas del
    inventario. Si el dedup mirara solo los stats, la segunda desaparecería del log."""
    _paso(mon, _S30, badge=_badge(present=False, crop=False))
    _paso(mon, _S30, sig=b"B", badge=_badge())
    assert len(_lineas(mon)) == 2


# --- Re-despacho: el bug del QA 2026-08-07 -----------------------------------------------------

def test_s30_se_re_despacha_mientras_seguis_en_la_pantalla():
    """REGRESIÓN. S30 no estaba en la lista de estados que se re-despachan, así que el monitor
    llamaba al handler UNA sola vez, al entrar. En vivo se vio como "reconoció el primer engine y
    después nada" — ocho minutos sin una línea, **ni siquiera de trabe**, porque nunca se llegaba
    al parser. El gate por firma ya estaba puesto, así que el arreglo no cuesta OCR de más.

    El criterio para estar en la lista es "el contenido cambia sin que cambie la pantalla", que es
    exactamente lo que pasa al moverse por la grilla del inventario.
    """
    from app.core.monitor import _CONTINUOUS_STATES, _REDISPATCH_STATES
    assert "S30" in _REDISPATCH_STATES or "S30" in _CONTINUOUS_STATES


@pytest.mark.parametrize("code", ["S9", "S26", "S30"])
def test_las_tres_pantallas_de_seleccion_se_re_despachan(code):
    """Las tres muestran un panel de detalle que SIGUE a una selección. Si alguna se cayera de la
    lista, se vería el mismo silencio desconcertante, así que van juntas."""
    from app.core.monitor import _CONTINUOUS_STATES, _REDISPATCH_STATES
    assert code in _REDISPATCH_STATES or code in _CONTINUOUS_STATES

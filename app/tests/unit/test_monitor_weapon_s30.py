"""Cableado de S30 (inventario de amplificadores) en el monitor — RF-15 tramo 2.

Se stubbea el parser: la lectura real está cubierta contra los 6 fixtures en
`test_parser_weapon_s30`. Acá se prueba la ORQUESTACIÓN, que es donde el proyecto tuvo sus bugs
históricos: handlers mudos en un `return` temprano y estados que no se resetean al salir.

Lo que distingue a S30 de S26, y es el contrato que fijan estos tests:

  · **No emite toast.** Recorrer una grilla es lectura, no novedad — el criterio de Daniel es que
    un toast avisa de CAMBIOS. En S26 abrir un arma sí emite; acá no debe emitir nunca.
  · **Ya no es observación pura.** Hasta el 2026-09-06 este handler no escribía nada; ahora
    persiste el arma (censo de W-Engines) por un callback PROPIO, separado de `on_weapon_seen`.
    Sin ese callback el comportamiento es exactamente el de antes.
"""
from __future__ import annotations

from typing import ClassVar

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
        # Lo declara el `WeaponParsed` real y el handler lo ESCRIBE (`d.dueno =`).
        self.dueno = None


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
    m._stub = {"weapon": FakeWeapon(), "sig": b"A", "badge": None, "pos": None}
    monkeypatch.setattr(pw_mod, "parse_weapon_s30",
                        lambda fr, ocr, catalogo=None: m._stub["weapon"])
    monkeypatch.setattr(pw_mod, "weapon_panel_signature_s30", lambda fr: m._stub["sig"])
    monkeypatch.setattr(pw_mod, "read_weapon_owner_badge_s30", lambda fr, pb: m._stub["badge"])
    # La posición de la selección también se stubbea. Por default `None`, que es lo que devuelve el
    # localizador real sobre un frame sintético: así los tests que no hablan de copias no cambian.
    monkeypatch.setattr(mon_mod, "s9_selected_tile_pos", lambda fr: m._stub["pos"])
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


def test_un_panel_sin_rareza_es_una_transicion_y_no_cuenta(mon):
    """El frame de transición: el panel todavía se está dibujando cuando la firma ya cambió.

    Medido en el log (127 lecturas de S30): la rareza vino vacía sólo 2 veces y ninguna era un arma
    asentada — `Última cena · ? · P? · dueño ?` a mitad de animación, y el panel de la propia app.
    Esa lectura entraba al censo como identidad provisoria propia (refinamiento `None` ⇒ otra
    clave) y sumaba 1. La lectura asentada que viene detrás cambia la firma otra vez y se lee bien.
    El refinamiento NO sirve de criterio: `P?` sale también en paneles asentados y válidos."""
    llamadas = []
    mon._on_weapon_detected = llamadas.append
    _paso(mon, _S30, sig=b"A", weapon=FakeWeapon(rareza=None, refin=None))
    assert _lineas(mon) == [] and llamadas == [], "a mitad de animación no se reporta ni persiste"
    _paso(mon, _S30, sig=b"B", weapon=FakeWeapon())
    assert len(_lineas(mon)) == 1 and len(llamadas) == 1, "el panel asentado sí"


def test_una_libre_llega_a_la_persistencia_marcada_y_con_su_numero_de_copia(mon):
    """El syncer no ve la grilla: el monitor le dice que es libre y QUÉ copia es. Las dos Última
    cena libres de Daniel (Ejemplo_11/12) sólo se separan por la posición de la selección."""
    from app.core.parser_weapon_s26 import OwnerBadge
    vistos = []
    mon._on_weapon_detected = lambda d: vistos.append((d.tenencia, d.copia))
    libre = OwnerBadge(present=False, nitidez=0.6)
    _paso(mon, _S30, sig=b"A", badge=libre, pos=(1304.0, 599.5, 172.0))
    _paso(mon, _S30, sig=b"A", badge=libre, pos=(1484.0, 599.5, 176.0))
    _paso(mon, _S30, sig=b"A", badge=libre, pos=(1304.0, 599.5, 172.0))
    assert vistos == [("libre", 0), ("libre", 1), ("libre", 0)]


def test_con_dueno_sin_nombre_no_se_marca_libre(mon):
    from app.core.parser_weapon_s26 import OwnerBadge
    vistos = []
    mon._on_weapon_detected = lambda d: vistos.append(d.tenencia)
    _paso(mon, _S30, badge=OwnerBadge(present=True, nitidez=60.5, crop=None))
    assert vistos == ["incierto"]


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


# --- S30 no cosecha (RF-15, spec 2026-08-10) --------------------------------------------------


def test_s30_nunca_cosecha_el_badge(mon):
    """El contrato que separa a S30 de S26, y la razón por la que existe.

    Acá el dueño sale del PROPIO badge: no hay botón que lo confirme. Cosechar con la etiqueta que
    produjo el mismo matcher lo realimenta con sus aciertos Y sus errores — es el efecto "imán" que
    en julio dejó una librería nombrando mal con confianza. S30 es consumidor puro.
    """
    import app.core.parser_weapon_s26 as pw_mod

    class Espia:
        def __init__(self):
            self.cosechado = []
            self.surfaces = {"detail": type("S", (), {
                "match": lambda self, crop: type("R", (), {"name": "Jane", "conf": 0.95})()})()}

        def _canonical_name(self, n):
            return n

        def detail_refs_count(self, name):
            return 0

        def learn_s17_detail(self, crop, name):
            self.cosechado.append(name)
            return True

    mon._identifier = Espia()
    mon._last_agent_name = "Jane"
    _paso(mon, _S30, badge=pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=_frame(200)))
    assert _lineas(mon), "el handler tenía que leer el arma igual"
    assert mon._identifier.cosechado == []


def test_el_diagnostico_no_repite_la_misma_evaluacion(mon, caplog):
    """QA en vivo 2026-08-11: 18 líneas idénticas para *Rotor de cañón*.

    El gate de firma del panel es de PÍXELES y el arte 3D del arma se mueve solo, así que la firma
    cambia sin que cambie nada de lo leído — la misma trampa que ya obligó al dedup por contenido
    de la línea `[S30]`. Un diagnóstico que se repite es tan ilegible como no tenerlo: si mañana
    hay que buscar una abstención entre 200 líneas iguales, no se encuentra.
    """
    import logging

    import app.core.parser_weapon_s26 as pw_mod

    class Abstiene:
        def __init__(self):
            self.surfaces = {"detail": type("S", (), {"match": lambda self, crop: type("R", (), {
                "name": None, "conf": 0.70, "margin": 0.02, "rejected": False,
                "top": [("Harumasa", 0.30)]})()})()}

        def _canonical_name(self, n):
            return n

    mon._identifier = Abstiene()
    mon._id_diag_on = True
    badge = pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=_frame(200))
    with caplog.at_level(logging.INFO):
        # Misma arma, mismo badge, firmas distintas: es el arte animado, no una selección nueva.
        _paso(mon, _S30, sig=b"A", badge=badge)
        _paso(mon, _S30, sig=b"B", badge=badge)
        _paso(mon, _S30, sig=b"C", badge=badge)
    diag = [r.getMessage() for r in caplog.records if "[id_diag/arma]" in r.getMessage()]
    assert len(diag) == 1, f"{len(diag)} líneas para la misma evaluación: {diag}"


def test_s30_registra_a_quien_estuvo_cerca_cuando_se_abstiene(mon, caplog):
    """S30 no cosecha, pero SÍ tiene que dejar registro: es la pantalla donde se midió el 3/7, y
    sin el top-1 de cada abstención no se puede saber a qué PJ le faltan referencias."""
    import logging

    import app.core.parser_weapon_s26 as pw_mod

    class Abstiene:
        def __init__(self):
            self.surfaces = {"detail": type("S", (), {"match": lambda self, crop: type("R", (), {
                "name": None, "conf": 0.70, "margin": 0.02, "rejected": False,
                "top": [("Harumasa", 0.30)]})()})()}

        def _canonical_name(self, n):
            return n

    mon._identifier = Abstiene()
    mon._last_agent_name = "Harumasa"
    mon._id_diag_on = True
    with caplog.at_level(logging.INFO):
        _paso(mon, _S30, badge=pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=_frame(200)))
    diag = [r.getMessage() for r in caplog.records if "[id_diag/arma]" in r.getMessage()]
    assert len(diag) == 1, diag
    assert "pantalla=S30" in diag[0] and "Harumasa" in diag[0] and "abstuvo" in diag[0]


# --- Persistencia y censo (2026-09-06) ----------------------------------------------------------

def _ident(nombre):
    class _Res:
        name, conf = nombre, 0.92

    class _Ident:
        surfaces: ClassVar[dict] = {
            "detail": type("S", (), {"match": staticmethod(lambda c: _Res())})()
        }

        @staticmethod
        def _canonical_name(n):
            return n
    return _Ident()


def test_el_dueno_resuelto_llega_a_la_persistencia(mon):
    """⚠️ El handler resolvía el dueño en una variable LOCAL y lo usaba sólo para armar el string
    del log. Todo lo que consumiera el `WeaponParsed` —la persistencia, el censo— lo veía en
    `None`, así que el syncer se habría abstenido SIEMPRE y el censo no habría registrado un solo
    dueño. Sin este test, ese fallo es completamente mudo."""
    vistas = []
    mon._on_weapon_detected = vistas.append
    mon._identifier = _ident("Vivian")
    _paso(mon, _S30, badge=_badge())
    assert vistas, "la persistencia no se llamó"
    assert vistas[0].dueno == "Vivian"


def test_el_arma_observada_entra_al_censo(mon):
    mon._identifier = _ident("Vivian")
    _paso(mon, _S30, badge=_badge())
    assert mon.censo_armas is not None and mon.censo_armas.registrados == 1
    assert mon.censo_armas.con_dueno == 1


def test_si_la_persistencia_revienta_el_log_y_el_censo_siguen(mon):
    """Mismo criterio que el toast del drop: el diagnóstico que el usuario está mirando durante una
    pasada de 57 tiles no puede depender de que la DB colabore."""
    def _explota(_d):
        raise RuntimeError("la DB se cayó")
    mon._on_weapon_detected = _explota
    _paso(mon, _S30)
    assert _lineas(mon), "el log se apagó"
    assert mon.censo_armas.registrados == 1


def test_sin_callback_el_handler_se_comporta_como_antes(mon):
    """El callback es opcional a propósito: sin él, display-only como hasta el 2026-09-06."""
    assert mon._on_weapon_detected is None
    _paso(mon, _S30)
    assert _lineas(mon)


# --- Copias idénticas (2026-09-10) --------------------------------------------------------------
#
# Daniel tiene cinco Última cena: tres equipadas y DOS LIBRES, una al lado de la otra. Las libres
# son idénticas en todo el panel derecho, tenencia incluida, así que la segunda moría en dos
# lugares: el gate de firma (re-disparar dependía del ruido del frame) y el dedup por contenido,
# que salía por un `return` antes de persistir y de censar. Lo único que las separa es DÓNDE está
# la selección en la grilla. Las posiciones de abajo son las medidas en sus capturas 11 y 12.

_COPIA_1 = (1304.0, 599.5, 172.0)
_COPIA_2 = (1484.0, 599.5, 176.0)


def test_dos_copias_libres_identicas_se_leen_las_dos(mon):
    """El caso de Daniel: misma firma del panel, mismo contenido, otro tile."""
    _paso(mon, _S30, sig=b"A", pos=_COPIA_1, badge=_badge(present=False))
    _paso(mon, _S30, sig=b"A", pos=_COPIA_2)
    assert len(_lineas(mon)) == 2, _lineas(mon)


def test_la_segunda_copia_llega_a_la_persistencia_y_al_censo(mon):
    """El log no alcanza: lo que el `return` del dedup se tragaba era la persistencia y el censo,
    que van DESPUÉS. Verificar la línea sola habría dado verde con el censo todavía roto."""
    vistas = []
    mon._on_weapon_detected = vistas.append
    _paso(mon, _S30, sig=b"A", pos=_COPIA_1, badge=_badge(present=False))
    _paso(mon, _S30, sig=b"A", pos=_COPIA_2)
    assert len(vistas) == 2, "la segunda copia no llegó a la persistencia"
    assert mon.censo_armas.registrados == 2, "el censo colapsó las dos copias en una"


def test_el_temblor_del_localizador_no_inventa_una_copia(mon):
    """El lado medido del tile varía 167-177 px entre capturas y el centro tiembla unos píxeles.
    La tolerancia es medio tile: quedarse quieto no puede leerse como moverse."""
    _paso(mon, _S30, sig=b"A", pos=_COPIA_1)
    _paso(mon, _S30, sig=b"A", pos=(1310.0, 602.0, 170.0))
    assert len(_lineas(mon)) == 1, _lineas(mon)


def test_sin_posicion_no_decide(mon):
    """En 3 de 18 capturas de S9 no hay tile localizable. Ausencia de posición es ausencia de
    dato: si forzara una relectura, un frame sin selección inventaría una copia por no saber.

    Cuenta RELECTURAS del panel, no sólo líneas: la primera versión de este test contaba líneas y
    pasaba igual con el gate roto, porque el dedup por contenido tapaba la línea repetida mientras
    el OCR de ~500 ms corría en cada ciclo. Lo destapó un sabotaje."""
    import app.core.parser_weapon_s26 as pw_mod
    llamadas = {"n": 0}

    def _contando(fr, ocr, catalogo=None):
        llamadas["n"] += 1
        return mon._stub["weapon"]
    pw_mod.parse_weapon_s30 = _contando

    for _ in range(4):
        _paso(mon, _S30, sig=b"A", pos=None)
    assert llamadas["n"] == 1, "sin posición, el gate re-OCReó un panel quieto"
    assert len(_lineas(mon)) == 1


def test_salir_de_la_pantalla_olvida_la_posicion(mon):
    _paso(mon, _S30, pos=_COPIA_1)
    _paso(mon, _S12)
    assert mon._s30_pos is None and mon._s30_last_log_pos is None


def test_las_capturas_de_daniel_se_distinguen_por_la_seleccion():
    """Con los píxeles reales, no con stubs: el localizador de S9 encuentra la selección en la
    pantalla de ARMAS, y entre las dos Última cena libres salta más de medio tile."""
    from pathlib import Path

    import cv2

    from app.core.detector import s9_selected_tile_pos
    from app.core.monitor import Monitor

    d = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
         / "Engines_Triggers" / "Inventario_general_engines")
    a, b = d / "Ejemplo_11.png", d / "Ejemplo_12.png"
    if not (a.exists() and b.exists()):
        pytest.skip("capturas full-res locales (gitignoreadas)")
    pa, pb = s9_selected_tile_pos(cv2.imread(str(a))), s9_selected_tile_pos(cv2.imread(str(b)))
    assert pa is not None and pb is not None, "no localizó la selección en la pantalla de armas"
    assert Monitor._s9_pos_movio(pa, pb) is True

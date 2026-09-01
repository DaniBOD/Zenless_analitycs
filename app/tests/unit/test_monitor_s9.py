"""Handler del INVENTARIO GLOBAL S9 en el monitor (`_process_disc_s9_continuous`).

Verifica el end-to-end: frame S9 → parse del disco (panel derecho) + dueño por badge
del tile → emisión vía on_disc. Reusa el parser y el matcher de S17. Tests de frame
real (PaddleOCR); se saltean si Paddle o las capturas no están.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "09_Inventario_discos_general"


class _StubIdent:
    """Identifier de prueba: el badge (crop real) que se le pase matchea a un PJ fijo.
    Hace el test hermético (no depende de la librería de badges en %LOCALAPPDATA% ni
    del roster de la DB), pero SÍ ejercita el crop real del tile (`crop_s9_selected_badge`)."""
    def __init__(self, name="Zhao", rejected=False):
        self._name, self._rejected = name, rejected
    def s17_match(self, badge):
        return (None, 0.5, True) if self._rejected else (self._name, 0.94, False)


def _monitor(on_disc, ident=None, tiebreaker=None):
    import app.core.monitor as mon
    return mon.Monitor(ocr=_paddle(), detector=None, on_disc=on_disc,
                       agent_identifier=ident or _StubIdent(),
                       owner_tiebreaker=tiebreaker)


class _MarginAbstainIdent:
    """Badge match que ABSTIENE por margen: s17_match da (None, conf, no-reject) y
    s17_match_full devuelve el MatchResult crudo con `top` (los look-alikes). Modela
    Velina@0.97 vs César. Ejercita el camino de desempate por contexto del monitor."""
    def __init__(self, conf=0.95, rejected=False, top=None):
        self._conf, self._rejected = conf, rejected
        self._top = top or [("Velina", 0.05), ("César", 0.09)]
    def s17_match(self, badge):
        return (None, self._conf, self._rejected)
    def s17_match_full(self, badge):
        from app.core.avatar_descriptor import MatchResult
        return MatchResult(None, self._conf, 0.02, self._rejected, self._top)


class _StubTiebreaker:
    """Tiebreaker de prueba: devuelve un resultado fijo (o None) sin tocar la DB.

    Registra `permitir_top2` porque el monitor lo calcula (censo abierto ⇒ False) y esa
    decisión no se ve en el resultado: el stub confirma el top-1 pase lo que pase."""
    def __init__(self, ret):
        self._ret = ret
        self.calls = []
    def resolve(self, disc, top, permitir_top2=True):
        self.calls.append((disc, top, permitir_top2))
        return self._ret


class _DeferredIdent:
    """Abstiene (sin dueño, no-reject) las primeras `resolve_after` llamadas a s17_match,
    luego matchea. Modela el badge que NO localiza en la 1ª cadencia y resuelve en una
    posterior → ejercita el WARMUP del dueño en S9."""
    def __init__(self, name="Zhao", resolve_after=1):
        self._name, self._resolve_after, self.calls = name, resolve_after, 0
    def s17_match(self, badge):
        self.calls += 1
        if self.calls <= self._resolve_after:
            return (None, 0.5, False)        # abstiene: ni nombre ni reject → sin dueño
        return (self._name, 0.94, False)


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_emite_disco_con_dueno():
    """Ejemplo_1 (Conejo, slot 2, equipado): el handler emite el disco parseado con su
    dueño resuelto por el badge del tile (Zhao @0.94 offline)."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    d, st = emitted[0]
    assert st.code == "S9"
    assert d.slot == 2
    assert (d.main_stat_canon or d.main_stat_raw) == "ATK"
    assert len([s for s in d.subs if s.valor is not None]) == 4
    assert d.agente_asignado_nombre  # dueño resuelto por badge (no None)


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_mismo_disco_no_re_emite():
    """Gate RNF-06: re-despachar el MISMO frame S9 no re-emite (firma estable +
    dedup por identidad)."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S9", 1.0, "s9_inventario")
    m._dispatch_state(fr, st)
    m._dispatch_state(fr, st)
    assert len(emitted) == 1


@pytest.mark.skipif(not (_S9 / "Ejemplo_4.png").exists(), reason="capturas S9 no presentes")
def test_s9_disco_sin_badge_se_emite_sin_dueno():
    """Un disco cuyo tile no da badge confiable (libre/NOLOC) se emite IGUAL con los stats,
    sin inventar dueño (RNF-02): agente_asignado_nombre = None. Con el WARMUP del dueño, la
    emisión sin dueño se DIFIERE hasta el techo de ciclos → despachamos hasta que emita."""
    from app.core.detector import ScreenState
    from app.core.monitor import _S17_AGG_MAX_CYCLES
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_4.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S9", 1.0, "s9_inventario")
    for _ in range(_S17_AGG_MAX_CYCLES + 1):     # 1 OCR + warmup hasta el techo
        m._dispatch_state(fr, st)
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre is None


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_desempate_por_contexto_asigna_dueno():
    """Badge ambiguo por margen (no-reject, conf alta): el monitor consulta el tiebreaker
    y, si confirma el top-1, asigna ese dueño + nota. Ejercita el camino completo
    `_assign_s9_owner` → `s17_match_full` → `OwnerTiebreaker.resolve`."""
    from app.core.detector import ScreenState
    emitted = []
    tb = _StubTiebreaker(("Velina", "build"))
    m = _monitor(on_disc=lambda d, st: emitted.append(d),
                 ident=_MarginAbstainIdent(), tiebreaker=tb)
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre == "Velina"
    assert "dueno_desempate_build" in emitted[0].notas
    assert tb.calls, "el tiebreaker debió ser consultado"


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_desempate_abstiene_deja_sin_dueno():
    """Si el tiebreaker no confirma (None), el disco queda SIN dueño (RNF-02), no se
    inventa el top-1 visual solo."""
    from app.core.detector import ScreenState
    from app.core.monitor import _S17_AGG_MAX_CYCLES
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d),
                 ident=_MarginAbstainIdent(), tiebreaker=_StubTiebreaker(None))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S9", 1.0, "s9_inventario")
    for _ in range(_S17_AGG_MAX_CYCLES + 1):     # warmup difiere el sin-dueño hasta el techo
        m._dispatch_state(fr, st)
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre is None


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_desempate_no_corre_en_reject():
    """Un badge RECHAZADO (disco libre/lock) NO debe consultar el tiebreaker — queda sin
    dueño. El desempate es solo para abstenciones por margen, no para rejects."""
    from app.core.detector import ScreenState
    from app.core.monitor import _S17_AGG_MAX_CYCLES
    emitted = []
    tb = _StubTiebreaker(("Velina", "build"))
    m = _monitor(on_disc=lambda d, st: emitted.append(d),
                 ident=_MarginAbstainIdent(rejected=True), tiebreaker=tb)
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S9", 1.0, "s9_inventario")
    for _ in range(_S17_AGG_MAX_CYCLES + 1):     # reject → sin dueño → warmup hasta el techo
        m._dispatch_state(fr, st)
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre is None
    assert not tb.calls, "el tiebreaker NO debe consultarse en reject"


# --- WARMUP del dueño S9 (fix badge=None: reintenta la localización antes de emitir) -------

@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_warmup_difiere_y_resuelve_dueno():
    """El badge no localiza en la 1ª cadencia (dueño None) → el disco NO se emite (warmup);
    cuando una cadencia posterior resuelve el dueño, recién ahí emite CON dueño."""
    from app.core.detector import ScreenState
    emitted = []
    ident = _DeferredIdent(name="Zhao", resolve_after=1)   # abstiene 1×, luego matchea
    m = _monitor(on_disc=lambda d, st: emitted.append(d), ident=ident)
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    st = ScreenState("S9", 1.0, "s9_inventario")
    m._dispatch_state(fr, st)                  # 1ª: madura sin dueño → warmup, NO emite
    assert emitted == [], "no debe emitir mientras calienta el dueño"
    m._dispatch_state(fr, st)                  # 2ª: el badge resuelve → emite con dueño
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre == "Zhao"


def test_tiebreak_owner_helper_asigna_y_es_compartido():
    """El helper `_tiebreak_owner` (compartido por S9 y S17): ante un badge que abstiene por
    margen, consulta el tiebreaker y, si confirma, asigna dueño + nota y devuelve True. Es el
    mismo camino que cablea el fallback 'incierto' de S17."""
    from types import SimpleNamespace
    import app.core.monitor as mon
    m = mon.Monitor(ocr=None, detector=None, on_disc=None,
                    agent_identifier=_MarginAbstainIdent(),
                    owner_tiebreaker=_StubTiebreaker(("Velina", "build")))
    disc = SimpleNamespace(agente_asignado_nombre=None, agente_asignado_conf=None, notas=[])
    assert m._tiebreak_owner(disc, badge=object(), tag="s17_owner") is True
    assert disc.agente_asignado_nombre == "Velina"
    assert "dueno_desempate_build" in disc.notas


def test_tiebreak_owner_helper_no_asigna_en_reject():
    """Reject (disco libre) → el helper NO consulta el tiebreaker ni asigna (RNF-02)."""
    from types import SimpleNamespace
    import app.core.monitor as mon
    tb = _StubTiebreaker(("Velina", "build"))
    m = mon.Monitor(ocr=None, detector=None, on_disc=None,
                    agent_identifier=_MarginAbstainIdent(rejected=True), owner_tiebreaker=tb)
    disc = SimpleNamespace(agente_asignado_nombre=None, agente_asignado_conf=None, notas=[])
    assert m._tiebreak_owner(disc, badge=object(), tag="s17_owner") is False
    assert disc.agente_asignado_nombre is None
    assert not tb.calls


def test_tiebreak_owner_helper_sin_tiebreaker():
    """Sin tiebreaker inyectado → no-op seguro (False)."""
    from types import SimpleNamespace
    import app.core.monitor as mon
    m = mon.Monitor(ocr=None, detector=None, on_disc=None,
                    agent_identifier=_MarginAbstainIdent(), owner_tiebreaker=None)
    disc = SimpleNamespace(agente_asignado_nombre=None, agente_asignado_conf=None, notas=[])
    assert m._tiebreak_owner(disc, badge=object(), tag="s17_owner") is False


# --- LIBRE vs NO SÉ (2026-08-18) ----------------------------------------------------------

def test_un_disco_LIBRE_queda_afirmado_como_libre():
    """El disco sin dueño deja de ser mudo. `equip_libre=True` es una AFIRMACIÓN sobre la pantalla
    —se leyó la esquina del tile y no hay cara—, no la ausencia de un dato.

    Es lo que le falta al censo para poder persistir los 72 discos sueltos del inventario sin
    inventar un equipamiento."""
    fr = _frame_o_skip("Ejemplo_2")            # libre, etiquetado en test_s9_badge_libre
    mon = _monitor(on_disc=lambda *_: None)
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.equip_libre is True
    assert d.agente_asignado_nombre is None


def test_un_tile_que_no_se_localiza_NO_se_declara_libre():
    """La mitad que importa: 'no pude leer' no puede convertirse en 'no tiene dueño'. Ese error
    registraría como suelto un disco que alguien tiene equipado."""
    fr = _frame_o_skip("Ejemplo_4")            # sin tile resaltado localizable
    mon = _monitor(on_disc=lambda *_: None)
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.equip_libre is False, "sin lectura no se afirma nada"
    assert d.agente_asignado_nombre is None


def test_un_disco_con_dueno_no_se_marca_libre():
    fr = _frame_o_skip("Ejemplo_1")            # equipado
    mon = _monitor(on_disc=lambda *_: None, ident=_StubIdent("Zhao"))
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.equip_libre is False
    assert d.agente_asignado_nombre == "Zhao"


def _disc_vacio():
    """DiscParsed mínimo: al `_assign_s9_owner` solo le importan los campos de dueño."""
    from app.core.parser_disc import DiscParsed
    return DiscParsed(set_name_raw="", set_name_canon=None, slot=1,
                      main_stat_raw="", main_stat_canon=None, main_valor=0.0,
                      main_unidad="flat", nivel=0, rareza="S")


def _frame_o_skip(stem: str):
    p = _S9 / f"{stem}.png"
    if not p.exists():
        pytest.skip(f"falta {p.name}")
    fr = cv2.imread(str(p))
    if fr is None:
        pytest.skip(f"no se pudo leer {p.name}")
    return fr


# --- la segunda superficie: el avatar del panel de detalle (2026-08-18) -----------------------

class _IdentSoloDetalle:
    """La grilla ABSTIENE (empate de look-alikes, sin reject) y el detalle sí nombra.

    Modela el caso medido en vivo: un disco de Soukaku da `Ben 0.897 / Soukaku 0.897` con margen
    0.000 en la grilla, porque en esa superficie las dos clases están separadas apenas 1,1×. En el
    detalle la separación es 8,9× y el match sale limpio."""
    def __init__(self, nombre="Soukaku"):
        self._n = nombre
    def s17_match(self, badge):
        return (None, 0.897, False)          # abstención por margen, NO reject
    def s17_match_detail(self, face):
        return (self._n, 0.843, 0.39, False)


def test_el_detalle_nombra_al_dueno_que_la_grilla_no_pudo(monkeypatch):
    """Sin esto el disco se descarta entero: `persist_s17_disc` exige dueño confiable, así que se
    pierden set, slot, nivel y los cuatro substats — que se leyeron bien."""
    import app.core.monitor as m
    monkeypatch.setattr(m, "crop_s9_detail_badge", lambda f: object())
    fr = _frame_o_skip("Ejemplo_1")
    mon = _monitor(on_disc=lambda *_: None, ident=_IdentSoloDetalle("Soukaku"))
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.agente_asignado_nombre == "Soukaku"
    assert d.equip_libre is False


def test_si_la_grilla_YA_nombro_no_se_consulta_el_detalle(monkeypatch):
    """La grilla es la superficie primaria y basta cuando resuelve. Consultar el detalle igual
    sería un Hough + un match por disco, gratis y en un handler continuo (RNF-06)."""
    import app.core.monitor as m
    llamadas = []
    monkeypatch.setattr(m, "crop_s9_detail_badge",
                        lambda f: (llamadas.append(1), object())[1])
    fr = _frame_o_skip("Ejemplo_1")
    mon = _monitor(on_disc=lambda *_: None, ident=_StubIdent("Zhao"))
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.agente_asignado_nombre == "Zhao"
    assert llamadas == [], "se consultó el detalle habiendo resuelto la grilla"


def test_un_disco_afirmado_LIBRE_no_consulta_el_detalle(monkeypatch):
    """`libre` es una afirmación sobre la pantalla, no una falta de datos. Buscarle dueño a un
    disco que ya se afirmó sin dueño sólo puede producir un falso positivo."""
    import app.core.monitor as m
    llamadas = []
    monkeypatch.setattr(m, "crop_s9_detail_badge",
                        lambda f: (llamadas.append(1), object())[1])
    fr = _frame_o_skip("Ejemplo_2")          # libre
    mon = _monitor(on_disc=lambda *_: None, ident=_IdentSoloDetalle("Soukaku"))
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.equip_libre is True
    assert d.agente_asignado_nombre is None
    assert llamadas == []


def test_sin_avatar_en_el_detalle_no_se_inventa_dueno(monkeypatch):
    import app.core.monitor as m
    monkeypatch.setattr(m, "crop_s9_detail_badge", lambda f: None)
    fr = _frame_o_skip("Ejemplo_1")
    mon = _monitor(on_disc=lambda *_: None, ident=_IdentSoloDetalle("Soukaku"))
    d = _disc_vacio()
    mon._assign_s9_owner(d, fr)
    assert d.agente_asignado_nombre is None


# --- La promoción del top-2 con un censo abierto (2026-09-01) ---------------------------------

def _disc_vacio():
    """`DiscParsed` mínimo: sólo se usa como destinatario del dueño que resuelve el desempate."""
    from app.core.parser_disc_s17 import DiscParsed
    return DiscParsed(set_name_raw="Punk Primitivo", set_name_canon=None, slot=4,
                      main_stat_raw="ATK", main_stat_canon="ATK", main_valor=None,
                      main_unidad=None, nivel=15, rareza="S")


def test_censo_en_curso_no_abre_la_pasada():
    """`_censo_discos_en_curso` es una CONSULTA: preguntar no puede abrir un censo.

    Es el efecto de costado que el censo del roster enseñó a evitar (QA 2026-08-17): una
    corrida que arranca sola por una razón que no es "el usuario entró al inventario" declara
    huérfano lo que nunca miró."""
    m = _monitor(on_disc=lambda d, st: None)
    assert m._censo_discos_en_curso() is False
    assert m.censo_discos is None, "la consulta no debe haber abierto la pasada"


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_con_censo_abierto_prohibe_promover_el_top2():
    """Recorrer el inventario ABRE la pasada, y desde ahí el desempate no puede dar vuelta
    al top-1 visual: la DB que usaría como corroboración es la que se está llenando."""
    from app.core.detector import ScreenState
    tb = _StubTiebreaker(("Velina", "build"))
    m = _monitor(on_disc=lambda d, st: None, ident=_MarginAbstainIdent(), tiebreaker=tb)
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
    assert tb.calls, "el tiebreaker debió ser consultado"
    assert m._censo_discos_en_curso() is True, "el handler S9 abre la pasada"
    assert all(c[2] is False for c in tb.calls), "con censo abierto, permitir_top2=False"


def test_sin_censo_el_desempate_puede_promover_el_top2():
    """Fuera de una pasada abierta la promoción sigue disponible: el rescate César/Punk que
    la justifica (2026-06-26) no se pierde, sólo se apaga mientras la DB está a medio hacer."""
    tb = _StubTiebreaker(("César", "build_top2"))
    m = _monitor(on_disc=lambda d, st: None, ident=_MarginAbstainIdent(), tiebreaker=tb)
    assert m._censo_discos_en_curso() is False
    disc = _disc_vacio()
    assert m._tiebreak_owner(disc, badge=object(), tag="s17_owner") is True
    assert disc.agente_asignado_nombre == "César"
    assert tb.calls[-1][2] is True, "sin censo, permitir_top2=True"

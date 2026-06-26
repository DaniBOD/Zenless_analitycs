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
    """Tiebreaker de prueba: devuelve un resultado fijo (o None) sin tocar la DB."""
    def __init__(self, ret):
        self._ret = ret
        self.calls = []
    def resolve(self, disc, top):
        self.calls.append((disc, top))
        return self._ret


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
    """Un disco cuyo tile no da badge confiable (libre/NOLOC) se emite IGUAL con los
    stats, sin inventar dueño (RNF-02): agente_asignado_nombre = None."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_4.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
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
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d),
                 ident=_MarginAbstainIdent(), tiebreaker=_StubTiebreaker(None))
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre is None


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_s9_desempate_no_corre_en_reject():
    """Un badge RECHAZADO (disco libre/lock) NO debe consultar el tiebreaker — queda sin
    dueño. El desempate es solo para abstenciones por margen, no para rejects."""
    from app.core.detector import ScreenState
    emitted = []
    tb = _StubTiebreaker(("Velina", "build"))
    m = _monitor(on_disc=lambda d, st: emitted.append(d),
                 ident=_MarginAbstainIdent(rejected=True), tiebreaker=tb)
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    m._dispatch_state(fr, ScreenState("S9", 1.0, "s9_inventario"))
    assert len(emitted) == 1
    assert emitted[0].agente_asignado_nombre is None
    assert not tb.calls, "el tiebreaker NO debe consultarse en reject"

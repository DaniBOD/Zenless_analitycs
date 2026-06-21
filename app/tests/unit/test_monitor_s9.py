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


def _monitor(on_disc, ident=None):
    import app.core.monitor as mon
    return mon.Monitor(ocr=_paddle(), detector=None, on_disc=on_disc,
                       agent_identifier=ident or _StubIdent())


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

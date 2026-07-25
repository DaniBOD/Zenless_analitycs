"""Cableado del desmontaje en el monitor: S11 (seguimiento) + S24 (commit).

Se stubbean los parsers — la lectura de píxeles ya está cubierta contra los fixtures reales en
`test_parser_desmontaje` y `test_parser_disc_s11`. Acá se prueba la ORQUESTACIÓN, que es donde
estuvieron los dos bugs históricos del proyecto: handlers que se quedaban mudos en un `return`
temprano (8m42s sin una línea de log en el QA del 2026-07-20) y pendientes que no cerraban nunca.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState

_S11 = ScreenState("S11", 1.0, "s11_desmontaje.png")
_S24 = ScreenState("S24", 1.0, "s24_obtenido_desmontaje.png")
_S12 = ScreenState("S12", 0.0, None)
_S9 = ScreenState("S9", 0.95, "s9_inventario_general.png")


def _frame(fill: int = 40):
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


class FakeSub:
    def __init__(self):
        self.nombre_canon, self.nombre_raw = "DEF%", "Defensa"
        self.valor, self.unidad, self.rolls, self.confianza = 4.8, "%", 0, 1.0


class FakeDisc:
    def __init__(self, slot=2):
        self.set_name_raw, self.set_name_canon = "Firmamento llameante", None
        self.slot, self.nivel, self.rareza = slot, 0, "S"
        self.main_stat_canon, self.main_stat_raw = "ATK", "Ataque"
        self.main_valor, self.main_unidad = 79.0, "flat"
        self.subs = [FakeSub()]
        self.confianza_global, self.notas = 0.95, []


@pytest.fixture
def mon(monkeypatch, tmp_path):
    import app.core.monitor as mon_mod
    import app.core.parser_desmontaje as pd_mod
    import app.core.parser_disc_s3 as s3_mod
    from app.core.farm_session import FarmSession

    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))

    diags: list[str] = []
    toasts: list[dict] = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        farm_session=FarmSession(), set_badge_matcher=object(),
                        on_teardown=toasts.append)
    m._diags, m._toasts, m._audit = diags, toasts, tmp_path

    # Estado de los stubs, controlable por test.
    m._stub = {"tildes": frozenset(), "counter": 0, "scroll": 0.1,
               "disc": FakeDisc(), "materiales": [("Disco original", 1)]}
    monkeypatch.setattr(pd_mod, "tilde_cells", lambda fr: m._stub["tildes"])
    monkeypatch.setattr(pd_mod, "parse_header_counter", lambda fr, ocr: m._stub["counter"])
    monkeypatch.setattr(pd_mod, "scroll_pos", lambda fr: m._stub["scroll"])
    monkeypatch.setattr(pd_mod, "parse_obtenido_materiales",
                        lambda fr, ocr: m._stub["materiales"])
    monkeypatch.setattr(s3_mod, "parse_disc_s11", lambda fr, ocr: m._stub["disc"])
    return m


def _paso(m, state, **stub):
    m._stub.update(stub)
    m._dispatch_state(_frame(), state)


# --- Flujo completo -------------------------------------------------------------------------

def test_flujo_completo_emite_un_solo_commit(mon):
    """S11 vacío → dos tildes → S24. Un solo toast, un solo archivo, dos discos con datos."""
    _paso(mon, _S11, tildes=frozenset(), counter=0)
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=1, disc=FakeDisc(slot=2))
    _paso(mon, _S11, tildes=frozenset({(0, 0), (0, 1)}), counter=2, disc=FakeDisc(slot=3))
    _paso(mon, _S24, materiales=[("Disco original", 2)])

    assert len(mon._toasts) == 1, mon._toasts
    ev = mon._toasts[0]
    assert ev["total"] == 2 and ev["con_datos"] == 2
    archivos = list((mon._audit / "desmontajes").glob("*.json"))
    assert len(archivos) == 1, archivos


def test_s24_repetido_no_commitea_dos_veces(mon):
    """S24 es CONTINUO (el modal vive hasta que el usuario aprieta Confirmar), así que el handler
    corre en cada ciclo y el gate de idempotencia es load-bearing."""
    _paso(mon, _S11, tildes=frozenset(), counter=0)
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=1)
    for _ in range(4):
        _paso(mon, _S24)
    assert len(mon._toasts) == 1, mon._toasts
    assert len(list((mon._audit / "desmontajes").glob("*.json"))) == 1


def test_la_tanda_sobrevive_un_s12_intermedio(mon):
    """El diálogo de confirmación de grado S cae a S12 (decisión de diseño: no se detecta). Si un
    S12 matara la tanda, el desmontaje NUNCA se registraría en ese camino."""
    _paso(mon, _S11, tildes=frozenset(), counter=0)
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=1)
    _paso(mon, _S12)
    _paso(mon, _S24)
    assert len(mon._toasts) == 1, "la tanda no sobrevivió al S12"


def test_salir_a_otra_pantalla_abandona_sin_registrar(mon):
    """Si el usuario se va sin desmontar, no pasó nada: ni toast ni archivo."""
    _paso(mon, _S11, tildes=frozenset(), counter=0)
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=1)
    _paso(mon, _S9)
    _paso(mon, _S24)
    assert mon._toasts == []
    assert not (mon._audit / "desmontajes").exists()


# --- Honestidad -----------------------------------------------------------------------------

def test_los_huecos_se_reportan_en_el_toast(mon):
    """Clicks más rápidos que la cadencia: el conteo sale igual (contador) pero los stats no."""
    _paso(mon, _S11, tildes=frozenset(), counter=0)
    _paso(mon, _S11, tildes=frozenset({(0, 0), (0, 1), (0, 2)}), counter=3)
    _paso(mon, _S24, materiales=[("Disco original", 3)])
    ev = mon._toasts[0]
    assert ev["total"] == 3 and ev["con_datos"] == 0


def test_contador_ilegible_no_inventa_conteo(mon):
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=None)
    _paso(mon, _S24)
    assert mon._toasts == [], "commiteó una tanda sin conteo declarado"


# --- Anti-trabe mudo ------------------------------------------------------------------------

def test_los_returns_tempranos_no_son_mudos(mon, caplog):
    """Requisito del proyecto: TODO return temprano de un handler continuo pasa por `_note_stall`.
    Los dos trabes históricos (6 y 8m42s sin una línea) fueron exactamente esto."""
    import logging
    caplog.set_level(logging.INFO)
    _paso(mon, _S11, tildes=frozenset({(0, 0)}), counter=None)
    assert any("S11" in r.message or "S11" in str(r.args) for r in caplog.records), \
        [r.message for r in caplog.records]


def test_s24_sin_tanda_abierta_avisa_y_no_crashea(mon, caplog):
    import logging
    caplog.set_level(logging.INFO)
    _paso(mon, _S24)
    assert mon._toasts == []

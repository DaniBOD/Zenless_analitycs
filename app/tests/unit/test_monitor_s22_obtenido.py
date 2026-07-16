"""Handler del modal "Obtenido" (S22) en el monitor (`_process_s22_obtenido`).

Reporte elegido por el usuario: UNA LÍNEA POR CORRIDA, emitida al verla mientras se scrollea
(no un total al cerrar: si no scrolleás hasta el fondo, el total mentiría). El dedup es
CONVERGENTE — una sección sin cerrar sale con "≥" y se re-emite sin él cuando el scroll trae
la evidencia de cierre.

Se stubbea el parser: la lectura de píxeles está cubierta por `test_parser_extraccion` contra
los fixtures reales; acá se testea la lógica de emisión/dedup/formato.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from app.core.detector import ScreenState
from app.core.parser_extraccion import DiscoS, Seccion

_ST22 = ScreenState("S22", 1.0, "s22_obtenido.png")
_ST13 = ScreenState("S13", 1.0, "s13_set")


def _frame(fill: int = 0):
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


def _sec(n_uso, slots, sets=None, completa=True):
    sets = sets or [None] * len(slots)
    return Seccion(n_uso=n_uso, completa=completa,
                   discos=tuple(DiscoS(slot=s, set_name=st, conf=0.66)
                                for s, st in zip(slots, sets)))


@pytest.fixture
def mon(monkeypatch):
    """Monitor con el parser stubbeado. `m._stub` = lo que devuelve `parse_obtenido`; los
    frames que pide se cuentan en `m._calls`.

    El handler importa `parse_obtenido` de forma lazy (convención del repo), así que el parche
    va sobre el módulo del PARSER: el import resuelve el atributo en tiempo de llamada."""
    import app.core.monitor as mon_mod
    import app.core.parser_extraccion as pe_mod
    from app.core.farm_session import FarmSession

    diags: list[str] = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        farm_session=FarmSession(), set_badge_matcher=object())
    m._diags = diags
    m._stub = []
    m._calls = []

    def _fake(frame, ocr, matcher=None, cand_en=None):
        m._calls.append(cand_en)
        if isinstance(m._stub, Exception):
            raise m._stub
        return m._stub

    monkeypatch.setattr(pe_mod, "parse_obtenido", _fake)
    return m


def _lineas(m):
    return [d for d in m._diags if d.startswith("[extracción]")]


def _arma_flujo(m, usos=4):
    ts = time.monotonic()
    m._farm_session.set_prediction("El piloto y el meca rebelde",
                                   [(1, "Wuthering Salon"), (2, "The Sky Ablaze")], ts)
    m._farm_session.set_usos(usos, ts)


def test_emite_una_linea_por_corrida(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(2, [2, 3, 6], ["Wuthering Salon", "Wuthering Salon", "The Sky Ablaze"])]
    mon._dispatch_state(_frame(), _ST22)

    lineas = _lineas(mon)
    assert len(lineas) == 1, lineas
    assert "uso 2/4" in lineas[0]
    assert "3 discos S" in lineas[0]
    assert "slot 2 Wuthering Salon" in lineas[0]
    assert "slot 6 The Sky Ablaze" in lineas[0]
    assert "≥" not in lineas[0]


def test_seccion_incompleta_sale_con_mayor_o_igual(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2, 6], completa=False)]
    mon._dispatch_state(_frame(), _ST22)
    assert "≥2 discos S" in _lineas(mon)[0]


def test_no_reemite_la_misma_seccion(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(3, [4, 4, 4])]
    for i in range(3):
        mon._dispatch_state(_frame(fill=10 + i * 40), _ST22)   # scroll "en movimiento"
    assert len(_lineas(mon)) == 1


def test_dedup_convergente_reemite_al_cerrar(mon):
    """El caso que justifica el '≥': la sección se ve parcial, después el scroll la cierra."""
    _arma_flujo(mon)
    mon._stub = [_sec(2, [2, 3], completa=False)]
    mon._dispatch_state(_frame(fill=10), _ST22)
    mon._stub = [_sec(2, [2, 3, 6], completa=True)]
    mon._dispatch_state(_frame(fill=90), _ST22)

    lineas = _lineas(mon)
    assert len(lineas) == 2, lineas
    assert "≥2 discos S" in lineas[0]
    assert "3 discos S" in lineas[1] and "≥" not in lineas[1]


def test_una_seccion_cerrada_no_vuelve_a_emitir(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(2, [2, 3, 6], completa=True)]
    mon._dispatch_state(_frame(fill=10), _ST22)
    mon._dispatch_state(_frame(fill=90), _ST22)   # sigue scrolleando sobre lo mismo
    assert len(_lineas(mon)) == 1


def test_no_reemite_si_la_seccion_no_crecio(mon):
    """Scrollear dentro de una sección parcial no debe spamear una línea por frame."""
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2, 6], completa=False)]
    mon._dispatch_state(_frame(fill=10), _ST22)
    mon._dispatch_state(_frame(fill=90), _ST22)
    assert len(_lineas(mon)) == 1


def test_gate_de_firma_evita_reparsear_con_el_scroll_quieto(mon):
    """RNF-06: con el scroll quieto no se re-parsea (es lo que hace viable la cadencia 700ms)."""
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2], completa=False)]
    f = _frame(fill=33)
    for _ in range(4):
        mon._dispatch_state(f, _ST22)   # MISMO frame → firma idéntica
    assert len(mon._calls) == 1, f"re-parseó {len(mon._calls)} veces con el scroll quieto"


def test_varias_corridas_en_un_frame(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2, 6]), _sec(2, [2, 3, 6], completa=False)]
    mon._dispatch_state(_frame(), _ST22)
    lineas = _lineas(mon)
    assert len(lineas) == 2
    assert "uso 1/4" in lineas[0] and "uso 2/4" in lineas[1]


def test_sin_usos_no_inventa_denominador(mon):
    """Si no se pasó por S21 (o expiró), se reporta la corrida sin el '/N'."""
    mon._farm_session.set_prediction("X", [(1, "Wuthering Salon")], time.monotonic())
    mon._stub = [_sec(2, [2])]
    mon._dispatch_state(_frame(), _ST22)
    linea = _lineas(mon)[0]
    assert "uso 2" in linea and "/4" not in linea and "/" not in linea.split("·")[0]


def test_sin_farm_session_no_emite(mon):
    """Sin contexto de farmeo no hay par de sets útil, y además un FP de S22 no debe hablar."""
    mon._farm_session = None
    mon._stub = [_sec(1, [2, 6])]
    mon._dispatch_state(_frame(), _ST22)
    assert _lineas(mon) == []


def test_sin_secciones_no_emite(mon):
    _arma_flujo(mon)
    mon._stub = []
    mon._dispatch_state(_frame(), _ST22)
    assert _lineas(mon) == []


def test_slot_no_confirmado_cuenta_pero_no_se_afirma(mon):
    """RNF-02: el disco existe (franja dorada = evidencia directa) aunque el slot no se lea.
    Suma al conteo, pero NO aparece un 'slot ?' inventado."""
    _arma_flujo(mon)
    mon._stub = [_sec(3, [None, None, None])]
    mon._dispatch_state(_frame(), _ST22)
    linea = _lineas(mon)[0]
    assert "3 discos S" in linea
    assert "slot" not in linea
    assert "?" not in linea


def test_el_set_sobrevive_aunque_no_se_lea_el_slot(mon):
    """Regresión (QA end-to-end 2026-07-16): el uso 3 son tres discos slot 4, y el '4' es el
    único dígito que el OCR no lee. El set SÍ se identificó, pero el formato lo mostraba solo
    pegado al slot → la línea salía como '3 discos S' pelada, tirando a la basura un dato que
    el sistema tenía. Cada disco debe reportar lo que se sabe de él, con o sin slot."""
    _arma_flujo(mon)
    mon._stub = [_sec(3, [None, None, None],
                      ["Wuthering Salon", "The Sky Ablaze", "The Sky Ablaze"])]
    mon._dispatch_state(_frame(), _ST22)
    linea = _lineas(mon)[0]
    assert "3 discos S: Wuthering Salon, The Sky Ablaze, The Sky Ablaze" in linea
    assert "slot" not in linea


def test_datos_parciales_por_disco(mon):
    """Un disco con slot y otro sin nada: se lista lo que hay y se declara lo que falta."""
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2, None])]
    mon._dispatch_state(_frame(), _ST22)
    linea = _lineas(mon)[0]
    assert "2 discos S: slot 2" in linea
    assert "(+1 sin identificar)" in linea


def test_sin_set_confirmado_enumera_los_candidatos(mon):
    """Formato ya vigente en `_process_s2_tiles`: enumerar el universo predicho es honesto;
    elegir uno sin evidencia, no."""
    _arma_flujo(mon)
    mon._stub = [_sec(2, [2, 3], [None, None])]
    mon._dispatch_state(_frame(), _ST22)
    linea = _lineas(mon)[0]
    assert "Wuthering Salon o The Sky Ablaze" in linea


def test_reset_al_salir_permite_reemitir(mon):
    _arma_flujo(mon)
    mon._stub = [_sec(2, [2, 3, 6])]
    mon._dispatch_state(_frame(fill=10), _ST22)
    mon._dispatch_state(_frame(fill=10), _ST13)    # cerrar el modal
    mon._dispatch_state(_frame(fill=10), _ST22)    # re-abrirlo
    assert len(_lineas(mon)) == 2


def test_un_parser_que_explota_no_tumba_el_monitor(mon):
    _arma_flujo(mon)
    mon._stub = RuntimeError("boom")
    mon._dispatch_state(_frame(), _ST22)   # no debe propagar
    assert _lineas(mon) == []


def test_el_matcher_se_restringe_a_los_sets_del_nodo(mon):
    """El matcher de set solo es confiable comparando contra los 2 candidatos del nodo (S13);
    abierto a los 27 sets del catálogo no tendría margen."""
    _arma_flujo(mon)
    mon._stub = [_sec(1, [2])]
    mon._dispatch_state(_frame(), _ST22)
    assert mon._calls[0] == ["Wuthering Salon", "The Sky Ablaze"]

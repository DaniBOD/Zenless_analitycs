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


# --- panel DETAIL (disco seleccionado) -------------------------------------


def _disc(set_raw="Salönhuracanado", slot=2, nivel=0, main=("ATK", 79.0, "flat"),
          subs=(("Perforación", 9.0, "flat"), ("DEF%", 4.8, "%"))):
    from app.core.parser_disc import DiscParsed, SubstatParsed
    return DiscParsed(
        set_name_raw=set_raw, set_name_canon=None, slot=slot,
        main_stat_raw=main[0], main_stat_canon=main[0], main_valor=main[1],
        main_unidad=main[2], nivel=nivel, rareza="S",
        subs=[SubstatParsed(n, n, v, u, 0, 0.9) for (n, v, u) in subs],
    )


class _SetRepo:
    """DiscSetRepo falso con resolución DIFUSA (el OCR rompe las tildes)."""
    class _E:
        def __init__(self, i, n): self.id, self.nombre, self.nombre_en = i, n, None

    def get_all(self):
        return [self._E(52, "Salón huracanado"), self._E(53, "Firmamento llameante")]

    def resolve_id(self, raw):
        return 52 if "huracanado" in (raw or "").lower() else None


@pytest.fixture
def mon_det(monkeypatch):
    """Monitor con el parser del DETAIL stubbeado. `m._det` = lo que devuelve."""
    import app.core.monitor as mon_mod
    import app.core.parser_extraccion as pe_mod
    from app.core.farm_session import FarmSession

    diags: list[str] = []
    emitted: list = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        on_disc=lambda d, st: emitted.append((d, st)),
                        farm_session=FarmSession(), set_repo=_SetRepo())
    m._diags = diags
    m._emitted = emitted          # discos enviados al recommender/toast (on_disc)
    m._det = None
    m._det_calls = []
    monkeypatch.setattr(pe_mod, "parse_obtenido",
                        lambda frame, ocr, matcher=None, cand_en=None: [])
    monkeypatch.setattr(pe_mod, "parse_detail_disc",
                        lambda frame, ocr: (m._det_calls.append(1), m._det)[1])
    return m


def _discos(m):
    return [d for d in m._diags if d.startswith("[disco]")]


def test_detail_emite_el_disco_con_sus_stats(mon_det):
    mon_det._det = _disc()
    mon_det._dispatch_state(_frame(), _ST22)
    linea = _discos(mon_det)
    assert len(linea) == 1, mon_det._diags
    assert "Salón huracanado" in linea[0]        # canon resuelto pese a la tilde rota
    assert "slot 2" in linea[0]
    assert "nivel 0/15" in linea[0]
    assert "ATK 79" in linea[0]
    assert "Perforación 9" in linea[0] and "DEF% 4.8%" in linea[0]


def test_detail_dispara_el_toast_como_el_ver(mon_det):
    """El panel DETAIL enruta el disco al recommender/toast (on_disc), no solo a la línea de
    log — igual que el "Ver" (S6/S7) y que el detalle de un drop S3. Pedido de QA 2026-07-18:
    el toast salía solo en "Ver", no al mirar el detalle en el propio "Obtenido"."""
    mon_det._det = _disc()
    mon_det._dispatch_state(_frame(), _ST22)
    assert len(mon_det._emitted) == 1, mon_det._emitted
    disc, st = mon_det._emitted[0]
    assert st.code == "S22"                       # el controller enruta S22 al recommender
    assert disc.slot == 2 and (disc.set_name_canon or disc.set_name_raw)
    assert disc.rareza == "S"                     # invariante del "Obtenido": drop conservado = tier S


def test_detail_no_reemite_el_toast_al_reclickear(mon_det):
    """El mismo disco visto de nuevo avisa 'ya capturado' y NO vuelve a toastar (un toast por
    disco distinto, como el dedup de la línea de log)."""
    mon_det._det = _disc()
    for i in range(3):
        mon_det._dispatch_state(_frame(fill=10 + i * 40), _ST22)
    assert len(mon_det._emitted) == 1, mon_det._emitted


def test_detail_lee_el_slot_que_la_grilla_no_puede(mon_det):
    """El '4' es el único dígito que el OCR de la grilla no lee; acá viene en texto."""
    mon_det._det = _disc(set_raw="Firmamentollameante", slot=4)
    mon_det._dispatch_state(_frame(), _ST22)
    assert "slot 4" in _discos(mon_det)[0]


def test_detail_sin_disco_seleccionado_no_emite(mon_det):
    """El modal abre en 'Crédito proxy'; el panel también muestra materiales/EXP/denny."""
    mon_det._det = None
    mon_det._dispatch_state(_frame(), _ST22)
    assert _discos(mon_det) == []


def test_detail_no_reemite_el_mismo_disco(mon_det):
    """El disco COMPLETO se reporta una sola vez; verlo de nuevo solo avisa 'ya capturado'
    (ver `test_reclickear_un_disco_ya_visto_avisa_en_vez_de_callar`)."""
    mon_det._det = _disc()
    for i in range(3):
        mon_det._dispatch_state(_frame(fill=10 + i * 40), _ST22)
    completas = [d for d in _discos(mon_det) if "ya capturado" not in d]
    assert len(completas) == 1, completas


def test_detail_emite_cada_disco_distinto(mon_det):
    mon_det._det = _disc(slot=2)
    mon_det._dispatch_state(_frame(fill=10), _ST22)
    mon_det._det = _disc(set_raw="Firmamentollameante", slot=4,
                         subs=(("Daño Crítico", 4.8, "%"),))
    mon_det._dispatch_state(_frame(fill=90), _ST22)
    assert len(_discos(mon_det)) == 2


def test_detail_gate_de_firma_no_reparsea_con_el_panel_quieto(mon_det):
    """RNF-06: el panel quieto = el mismo disco = nada nuevo que OCRear."""
    mon_det._det = _disc()
    f = _frame(fill=33)
    for _ in range(4):
        mon_det._dispatch_state(f, _ST22)
    assert len(mon_det._det_calls) == 1


def test_el_detalle_se_lee_aunque_la_grilla_este_quieta(mon_det):
    """Regresión de diseño: clickear otro disco cambia el panel ENTERO pero apenas mueve el
    viewport de la grilla (solo el borde de selección). Con una firma compartida, el gate de
    la grilla haría return y el disco no se leería nunca."""
    f = _frame(fill=50)
    mon_det._det = _disc(slot=2)
    mon_det._dispatch_state(f, _ST22)          # 1er disco
    mon_det._det = _disc(set_raw="Firmamentollameante", slot=6,
                         subs=(("ATK", 19.0, "flat"),))
    mon_det._s22_detail_sig = None             # el panel cambió...
    mon_det._dispatch_state(f, _ST22)          # ...con el MISMO frame de grilla
    assert len(_discos(mon_det)) == 2


def test_detail_sin_set_repo_no_rompe(mon_det):
    mon_det._set_repo = None
    mon_det._det = _disc()
    mon_det._dispatch_state(_frame(), _ST22)
    assert len(_discos(mon_det)) == 1


def test_un_parser_de_detalle_que_explota_no_tumba_el_monitor(mon_det, monkeypatch):
    import app.core.parser_extraccion as pe_mod

    def boom(frame, ocr):
        raise RuntimeError("boom")
    monkeypatch.setattr(pe_mod, "parse_detail_disc", boom)
    mon_det._dispatch_state(_frame(), _ST22)
    assert _discos(mon_det) == []


def test_reset_al_salir_olvida_los_discos_vistos(mon_det):
    mon_det._det = _disc()
    mon_det._dispatch_state(_frame(fill=10), _ST22)
    mon_det._dispatch_state(_frame(fill=10), _ST13)
    mon_det._dispatch_state(_frame(fill=10), _ST22)
    assert len(_discos(mon_det)) == 2


def test_reclickear_un_disco_ya_visto_avisa_en_vez_de_callar(mon_det):
    """QA en vivo 2026-07-16: el disco ya se había leído al ARRANCAR la app (el juego lo tenía
    seleccionado); al clickearlo después, el dedup lo tragaba EN SILENCIO y desde el lado del
    usuario parecía que no lo detectaba. Mismo feedback que S5: avisar, no callar."""
    mon_det._det = _disc()
    mon_det._dispatch_state(_frame(fill=10), _ST22)
    mon_det._s22_detail_sig = None            # se lo vuelve a clickear
    mon_det._dispatch_state(_frame(fill=10), _ST22)

    lineas = _discos(mon_det)
    assert len(lineas) == 2
    assert "ya capturado" in lineas[1]
    assert "Salón huracanado" in lineas[1] and "slot 2" in lineas[1]

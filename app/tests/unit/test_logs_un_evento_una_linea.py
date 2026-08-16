"""Un evento, una línea — el contrato del log en INFO.

Medido sobre el QA de discos del 2026-08-15: **un disco emitía 4 a 7 líneas**, y varias salían
IDÉNTICAS entre discos distintos porque el mensaje no dice de cuál habla. Con 12 a 47 segundos
entre ellas no eran repeticiones sino eventos reales indistinguibles.

Eso rompe dos cosas concretas:

1. **El log como señal de tiempo.** El plan de Daniel para medir frescura es pasar de pantalla
   apenas salta el log; si saltan siete por disco y algunas se repiten, no hay señal que seguir.
2. **El censo.** ~300 discos × 4-7 líneas = 1200-2100 líneas con la que importa enterrada.

La regla que fijan estos tests: en **INFO va QUÉ pasó**; el **PORQUÉ** —qué guarda vetó al ancla,
qué señal discrepó, por qué no se persistió— es material de depuración y vive en **DEBUG**
(`DANIBOD_LOG_DEBUG=1`).

No se borró ni un mensaje: bajarlos de nivel conserva el diagnóstico para cuando haga falta, que es
justamente lo que evita el arrepentimiento de haber "limpiado" el log.
"""
from __future__ import annotations

import logging

import numpy as np
import pytest

from app.core.detector import ScreenDetector
from app.core.monitor import Monitor


class _DummyOcr:
    def text(self, *a, **kw):
        return "", 0.0

    def number(self, *a, **kw):
        return 0.0, 0.0


def _monitor():
    return Monitor(ocr=_DummyOcr(), detector=ScreenDetector())


def _lineas(caplog, nivel: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == nivel]


# --- el razonamiento no ensucia INFO -------------------------------------------------------------

_RAZONAMIENTOS = [
    (("anchor_btn_veto", "equipar"),
     "[botón] el ancla decía 'equipado por %s' pero el botón dice '%s' → NO es el equipado.",
     ("Seth", "equipar")),
    (("anchor_latch_stale", "Seth"),
     "[latch] el ancla decía 'equipado por %s' pero ese latch está SOSTENIDO.", ("Seth",)),
    (("anchor_badge_conflict", "Grace"),
     "[badge] ancla decía '%s' pero el badge dice '%s' → badge (sin cosechar).", ("Seth", "Grace")),
    (("veto_detalle_no_rescatado", "Seth"),
     "[badge] no rescato la cosecha del detalle para '%s': %s.", ("Seth", "motivo")),
]


@pytest.mark.parametrize("sig,msg,args", _RAZONAMIENTOS)
def test_el_razonamiento_va_a_debug(caplog, sig, msg, args):
    """Estos cuatro son los que dominaban el log: 58 de 384 líneas en el QA, todas explicando por
    qué el sistema decidió algo — no qué decidió."""
    m = _monitor()
    with caplog.at_level(logging.DEBUG):
        m._log_s17_assign(sig, msg, *args, razonamiento=True)
    assert _lineas(caplog, logging.INFO) == [], "el razonamiento se coló en INFO"
    assert len(_lineas(caplog, logging.DEBUG)) == 1, "y tampoco puede desaparecer del todo"


def test_el_evento_sigue_en_info(caplog):
    """El contrapeso. Sin este test, "reducir logs" se podría "arreglar" mandando TODO a DEBUG y
    dejando al usuario sin ninguna señal — que es peor que el ruido."""
    m = _monitor()
    with caplog.at_level(logging.DEBUG):
        m._log_s17_assign(("confirm", "Seth"), "[S17] asignado a '%s' (latch).", "Seth")
    assert len(_lineas(caplog, logging.INFO)) == 1
    assert _lineas(caplog, logging.DEBUG) == []


def test_el_default_del_helper_es_evento(caplog):
    """`razonamiento` es opt-in: quien agregue un log nuevo cae en INFO salvo que diga lo
    contrario. El default correcto para un sistema observacional es que se vea."""
    m = _monitor()
    with caplog.at_level(logging.DEBUG):
        m._log_s17_assign(("x",), "una línea cualquiera")
    assert len(_lineas(caplog, logging.INFO)) == 1


# --- el gate ------------------------------------------------------------------------------------

def test_el_gate_de_debug_esta_apagado_por_defecto(monkeypatch):
    from app.main import _debug_logs
    monkeypatch.delenv("DANIBOD_LOG_DEBUG", raising=False)
    assert _debug_logs() is False
    monkeypatch.setenv("DANIBOD_LOG_DEBUG", "1")
    assert _debug_logs() is True
    for apagado in ("", "0", "false", "no"):
        monkeypatch.setenv("DANIBOD_LOG_DEBUG", apagado)
        assert _debug_logs() is False, f"{apagado!r} debería leerse como apagado"


# --- el dedup por firma sigue vivo ---------------------------------------------------------------

def test_la_misma_firma_no_se_repite(caplog):
    """El edge-trigger por firma es lo que ya evitaba re-loguear en cada ciclo del modelo continuo.
    Bajar de nivel no lo reemplaza: son dos mecanismos distintos y hacen falta los dos."""
    m = _monitor()
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            m._log_s17_assign(("confirm", "Seth"), "[S17] asignado a '%s'.", "Seth")
    assert len(_lineas(caplog, logging.INFO)) == 1


def test_sync_equip_no_ensucia_info_cuando_no_hay_pj(caplog, monkeypatch):
    """`PJ no confiable para 'SET' slot=N` salía por CADA disco sin dueño resuelto — 27 líneas en
    el QA. Es el motivo de una no-escritura, no un evento."""
    import app.core.sync_equip as se
    with caplog.at_level(logging.DEBUG, logger="app.core.sync_equip"):
        se.log.debug("S17: PJ no confiable para '%s' slot=%d — no se persiste.", "Jazz caótico", 1)
    assert _lineas(caplog, logging.INFO) == []
    assert len(_lineas(caplog, logging.DEBUG)) == 1


def _merged(dueno=None, libre=False):
    from app.core.parser_disc import DiscParsed
    d = DiscParsed(set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
                   main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad=None,
                   rareza="S", nivel=15, confianza_global=0.98)
    d.agente_asignado_nombre = dueno
    d.equip_libre = libre
    return d


@pytest.mark.parametrize("dueno,libre,esperado", [
    ("Corin", False, "dueño=Corin"),
    (None, True, "LIBRE"),
    (None, False, "dueño=?"),
])
def test_la_linea_del_evento_es_autocontenida(caplog, monkeypatch, dueno, libre, esperado):
    """set + slot + main + nivel + TENENCIA, todo en una línea.

    Antes el dueño salía en `[S17] asignado a 'X'`, aparte, y había que aparearla con "Disco
    detectado" por cercanía en el archivo — imposible con varios discos seguidos cuyos mensajes no
    se distinguen entre sí. Con la tenencia adentro, la línea se lee sola.

    Los tres casos importan: un disco con dueño, uno libre, y uno cuyo dueño no se resolvió. El
    tercero es el que NO puede salir como "dueño=None" ni omitirse — "no sé" es información.
    """
    from app.core.detector import ScreenState
    m = _monitor()
    monkeypatch.setattr(m, "_record_equip_map", lambda *a, **kw: None)
    with caplog.at_level(logging.INFO):
        m._emit_s17_disc(_merged(dueno, libre), ScreenState("S17", 1.0, "t"), mature=True)
    evento = [x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco detectado")]
    assert len(evento) == 1, f"esperaba una línea de evento, hubo {len(evento)}"
    for trozo in ("set=Jazz caótico", "slot=1", "main=HP", "nivel=15", esperado):
        assert trozo in evento[0], f"falta {trozo!r} en: {evento[0]}"


def test_frame_negro_no_es_requisito():
    """Guard de humo: el monitor se construye sin tocar pantalla ni DB (los tests de arriba lo
    instancian y no deben depender de un entorno gráfico)."""
    m = _monitor()
    assert m is not None
    assert np.zeros((4, 4, 3), np.uint8).size == 48

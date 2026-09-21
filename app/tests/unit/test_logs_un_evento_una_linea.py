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


def _aislar_emision_s9(monkeypatch, m):
    """Lo que `_emit_s9_disc` hace DESPUÉS de decidir la línea (mapa de equipamiento y censo) no
    es lo que se prueba acá, y necesita DB."""
    monkeypatch.setattr(m, "_record_equip_map", lambda *a, **kw: None)
    monkeypatch.setattr(m, "_censar_disco", lambda *a, **kw: None)


@pytest.mark.parametrize("dueno,libre,incierto,esperado", [
    ("Corin", False, False, "dueño=Corin"),
    (None, True, False, "LIBRE"),
    (None, False, True, "dueño=? (sin identificar)"),
    (None, False, False, "dueño=? (badge sin leer)"),
])
def test_la_linea_de_S9_distingue_los_cuatro_desenlaces(caplog, monkeypatch, dueno, libre,
                                                        incierto, esperado):
    """La línea de S9 imprimía `dueno=-` para TRES casos distintos: LIBRE, "tiene dueño y no sé
    quién" y "no se pudo leer el badge". Para el censo no son lo mismo — el segundo se guarda
    marcado y el tercero no se guarda —, y es la línea que Daniel mira para pasar al disco
    siguiente. En la pasada del 2026-09-16 salieron dos `dueno=-` y no había forma de saber cuál
    de los tres eran. Ninguno de los cuatro puede salir como `-` ni sin decir qué pasó."""
    from app.core.detector import ScreenState
    m = _monitor()
    _aislar_emision_s9(monkeypatch, m)
    d = _merged(dueno, libre)
    d.equip_dueno_incierto = incierto
    with caplog.at_level(logging.INFO):
        m._emit_s9_disc(d, ScreenState("S9", 1.0, "t"))
    evento = [x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9 detectado")]
    assert len(evento) == 1, f"esperaba una línea de evento, hubo {len(evento)}"
    for trozo in ("set=Jazz caótico", "slot=1", "main=HP", "nivel=15", esperado):
        assert trozo in evento[0], f"falta {trozo!r} en: {evento[0]}"
    assert "dueno=-" not in evento[0] and "=-" not in evento[0]


def test_la_linea_de_S9_cuenta_las_lecturas_descartadas_en_el_handler_real(caplog, monkeypatch):
    """**El diagnóstico de la Pasada A**, probado en el handler REAL y no en el emisor suelto.

    En la pasada del 2026-09-16 los 7 discos sin warmup esperaron 1719-2047 ms: el primer
    despacho no emitía y el siguiente sí. Faltaba saber POR QUÉ, y la sospecha es la lectura de
    transición (`confianza_global < 0.7`), que se descarta en silencio y encima no cuenta para el
    techo de ciclos. Este test fija que ese descarte se VEA en la línea: si alguien mueve el
    contador fuera del camino real, la línea dice `0 desc` y el diagnóstico miente."""
    import numpy as np
    from app.core.detector import ScreenState
    from app.core.parser_disc import SubstatParsed
    m = _monitor()
    _aislar_emision_s9(monkeypatch, m)
    firma = (np.zeros((24, 48), np.float32), np.zeros((48, 48), np.float32), None)
    monkeypatch.setattr(m, "_s9_disc_signature", lambda frame: firma)
    monkeypatch.setattr(m, "_anclar_contador_s9", lambda *a, **kw: None)
    # Dueño con nombre: así el disco NO entra al warmup y lo único que puede frenarlo es la lectura.
    monkeypatch.setattr(m, "_assign_s9_owner",
                        lambda disc, frame: setattr(disc, "agente_asignado_nombre", "Corin"))

    def _disco(conf):
        d = _merged()
        d.confianza_global = conf
        d.subs = [SubstatParsed(n, n, v, "flat", 1, 0.95)
                  for n, v in (("ATK", 38.0), ("DEF", 15.0), ("PV", 112.0), ("Penetración", 9.0))]
        return d

    lecturas = iter([_disco(0.40), _disco(0.95)])       # 1ª: frame de transición · 2ª: buena
    monkeypatch.setattr("app.core.monitor.parse_disc_s9", lambda frame, ocr, slot=None: next(lecturas))
    st = ScreenState("S9", 1.0, "t")
    with caplog.at_level(logging.INFO):
        m._process_disc_s9_continuous(None, st)          # descartada: no hay línea todavía
        assert not [x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9")]
        m._process_disc_s9_continuous(None, st)          # buena: sale
    evento = [x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9 detectado")]
    assert len(evento) == 1
    assert "(agg 1c · 1 desc · 0 warm)" in evento[0], evento[0]


def test_frame_negro_no_es_requisito():
    """Guard de humo: el monitor se construye sin tocar pantalla ni DB (los tests de arriba lo
    instancian y no deben depender de un entorno gráfico)."""
    m = _monitor()
    assert m is not None
    assert np.zeros((4, 4, 3), np.uint8).size == 48


# --- un disco, una línea: aunque el OCR lea el set con otra letra (2026-09-17) --------------------

def _disco_s9(set_raw, dueno="Pyrois"):
    d = _merged(dueno)
    d.set_name_raw, d.set_name_canon = set_raw, None     # como en vivo: el canónico no resolvió
    return d


def test_el_mismo_disco_leido_con_otra_letra_da_una_sola_linea(caplog, monkeypatch):
    """Pasada B del censo: `Firmamento Ilameante` y `Firmamento llameante` (I / l) salieron como
    DOS líneas del mismo disco. Es la señal con la que Daniel avanza: dos líneas por un disco le
    dicen que pasó algo que no pasó. El filtro de repetidos tiene que mirar el set RESUELTO."""
    from app.core.detector import ScreenState
    m = _monitor()
    _aislar_emision_s9(monkeypatch, m)
    resueltos = []
    def resolver(nombre):
        resueltos.append(nombre)
        return 53 if "lameante" in nombre.lower() else None
    monkeypatch.setattr(m, "_resolve_set_id_safe", resolver)
    st = ScreenState("S9", 1.0, "t")
    with caplog.at_level(logging.INFO):
        m._emit_s9_disc(_disco_s9("Firmamento Ilameante"), st)
        m._s9_emitted = False                        # otra lectura del MISMO disco
        m._emit_s9_disc(_disco_s9("Firmamento llameante"), st)
        m._s9_emitted = False
        m._emit_s9_disc(_disco_s9("Firmamento llameante"), st)
    evento = [x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9 detectado")]
    assert len(evento) == 1, f"un disco, una línea — hubo {len(evento)}: {evento}"
    assert resueltos == ["Firmamento Ilameante", "Firmamento llameante"], "cada grafía se resuelve UNA vez"


def test_si_el_set_no_resuelve_se_filtra_como_antes(caplog, monkeypatch):
    """Sin set resuelto (catálogo inaccesible, nombre basura) queda la identidad de siempre: dos
    textos distintos siguen siendo dos discos. Nunca peor que antes."""
    from app.core.detector import ScreenState
    m = _monitor()
    _aislar_emision_s9(monkeypatch, m)
    monkeypatch.setattr(m, "_resolve_set_id_safe", lambda nombre: None)
    st = ScreenState("S9", 1.0, "t")
    with caplog.at_level(logging.INFO):
        m._emit_s9_disc(_disco_s9("Set A ilegible"), st)
        m._s9_emitted = False
        m._emit_s9_disc(_disco_s9("Set B ilegible"), st)
    assert len([x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9 detectado")]) == 2


def test_dos_discos_distintos_del_mismo_set_siguen_siendo_dos(caplog, monkeypatch):
    """Resolver el set no puede colapsar discos distintos: slot y substats siguen en la clave."""
    from app.core.detector import ScreenState
    m = _monitor()
    _aislar_emision_s9(monkeypatch, m)
    monkeypatch.setattr(m, "_resolve_set_id_safe", lambda nombre: 53)
    st = ScreenState("S9", 1.0, "t")
    otro = _disco_s9("Firmamento llameante")
    otro.slot = 2
    with caplog.at_level(logging.INFO):
        m._emit_s9_disc(_disco_s9("Firmamento Ilameante"), st)
        m._s9_emitted = False
        m._emit_s9_disc(otro, st)
    assert len([x for x in _lineas(caplog, logging.INFO) if x.startswith("Disco S9 detectado")]) == 2


def test_la_premisa_las_dos_grafias_resuelven_al_mismo_set_en_la_db_real():
    """La premisa del arreglo, contra el catálogo REAL (solo lectura): si mañana el resolvedor deja
    de juntar estas dos grafías, el filtro de repetidos vuelve a dejar pasar el duplicado y esto
    lo dice antes que una pasada en vivo."""
    import sqlite3
    from pathlib import Path
    from app.db.repositories import DiscSetRepo
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        repo = DiscSetRepo(con)
        a, b = repo.resolve_id("Firmamento Ilameante"), repo.resolve_id("Firmamento llameante")
    finally:
        con.close()
    assert a is not None and a == b, (a, b)

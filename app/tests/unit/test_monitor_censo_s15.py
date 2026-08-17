"""Wiring del censo de roster en el handler de S15.

Dos cosas se prueban acá, y la segunda es la que suele romperse sin que nadie mire:

1. Que cada cambio de selección deje **una** observación.
2. Que sin censo inyectado el handler siga comportándose **exactamente** como antes. El censo es
   opcional: la app se usa la enorme mayoría del tiempo sin estar censando, y ese camino no puede
   pagar nada ni cambiar de conducta.

El gate de firma (`_MENU_SIG_MAX`) se deja intacto a propósito: es el presupuesto RNF-06 de toda
la fase — ~51 OCR por pasada en vez de uno por frame de animación. La contrapartida está declarada
como riesgo: si el gate se traga un cambio de selección, ese PJ queda pendiente en silencio.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.census import RosterCensus
from app.core.detector import ScreenState

_ROSTER = [(1, "Nangong Yu"), (2, "Jane"), (3, "Ellen")]


class _SeqOcr:
    """Devuelve nombres en secuencia — simula mover la selección."""
    def __init__(self, texts, conf=0.99):
        self._texts = list(texts); self._i = 0; self._conf = conf

    def text(self, img, psm=6, lang="spa"):
        t = self._texts[min(self._i, len(self._texts) - 1)]; self._i += 1
        return t, self._conf


def _monitor(ocr, censo=None, on_census_progress=None, on_diagnostic=None):
    import app.core.monitor as mon
    return mon.Monitor(ocr=ocr, detector=None, censo=censo,
                       on_census_progress=on_census_progress,
                       on_diagnostic=on_diagnostic)


def _censo():
    c = RosterCensus(_ROSTER)
    c.ensure_open(ts=0.0)
    return c


def _st():
    return ScreenState("S15", 1.0, "s15_menu_personajes.png")


def _frames():
    """Tres frames de firma distinta (el gate compara un recorte gris del nombre)."""
    return [np.full((1439, 2559, 3), v, np.uint8) for v in (0, 120, 240)]


@pytest.fixture(autouse=True)
def _matcher_eco(monkeypatch):
    """El matcher devuelve el texto tal cual: acá se prueba la ORQUESTACIÓN, no el matching
    (que tiene sus propios tests contra capturas reales)."""
    import app.core.parser_agent_stats as p
    monkeypatch.setattr(p, "_match_agent_scored",
                        lambda t, *a, **k: (t.strip(), "rol", "elem", t.strip(), 0.99))


# --- el camino sin censo no cambia ----------------------------------------------------------

def test_sin_censo_inyectado_el_handler_se_comporta_igual_que_antes():
    m = _monitor(_SeqOcr(["Nangong Yu"]))
    m._dispatch_state(_frames()[0], _st())
    assert m._last_agent_name == "Nangong Yu"      # sigue sembrando el latch
    assert m._census is None


# --- una observación por cambio de selección ------------------------------------------------

def test_cada_cambio_de_seleccion_deja_una_observacion():
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane", "Ellen"]), censo=c)
    for f in _frames():
        m._dispatch_state(f, _st())
    assert {r.clave for r in c.vistos} == {"Nangong Yu", "Jane", "Ellen"}
    assert c.pendientes == []


def test_el_mismo_frame_no_se_cuenta_dos_veces():
    """El gate de firma es lo que hace barato el recorrido: sin él habría un OCR por frame de
    animación idle."""
    c = _censo()
    f = _frames()[0]
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(f, _st())
    m._dispatch_state(f, _st())
    m._dispatch_state(f, _st())
    assert c.vistos[0].n_obs == 1


def test_volver_a_pasar_por_un_pj_ya_visto_no_lo_duplica_ni_reloguea():
    c = _censo()
    fa, fb, _ = _frames()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane", "Nangong Yu"]), censo=c)
    for f in (fa, fb, fa):
        m._dispatch_state(f, _st())
    assert len(c.vistos) == 2
    assert next(r for r in c.vistos if r.clave == "Nangong Yu").n_obs == 2


# --- abstención -----------------------------------------------------------------------------

def test_un_frame_ilegible_no_borra_el_latch_ni_ensucia_la_cobertura(monkeypatch):
    """Regresión viva: el último `[S15]` antes de salir a Equipamiento suele ser el frame del
    click, con el OCR abstenido. Si eso borrara el latch o contara como observación, la siembra
    no serviría justo en el caso que la motiva."""
    import app.core.parser_agent_stats as p
    monkeypatch.setattr(p, "_match_agent_scored",
                        lambda t, *a, **k: (None, None, None, None, None))
    c = _censo()
    m = _monitor(_SeqOcr([""]), censo=c)
    m._last_agent_name = "Ellen"
    m._detail_source = "menu"
    m._dispatch_state(_frames()[0], _st())
    assert m._last_agent_name == "Ellen"
    assert c.vistos == [] and c.dudosos == []
    assert len(c.pendientes) == 3


# --- progreso -------------------------------------------------------------------------------

def test_el_progreso_se_avisa_solo_cuando_cambia_el_estado():
    """El callback es para la UI de la fase 5. Dispararlo en cada frame la haría parpadear sin
    que haya pasado nada."""
    eventos = []
    c = _censo()
    fa, fb, _ = _frames()
    m = _monitor(_SeqOcr(["Nangong Yu", "Nangong Yu", "Jane"]), censo=c,
                 on_census_progress=eventos.append)
    for f in (fa, fb, fa):
        m._dispatch_state(f, _st())
    assert [e["clave"] for e in eventos] == ["Nangong Yu", "Jane"]
    assert eventos[-1]["vistos"] == 2 and eventos[-1]["total_db"] == 3


def test_el_progreso_se_ve_en_el_PANEL_no_solo_en_el_archivo():
    """QA en vivo 2026-08-17: el censo contaba bien pero Daniel no veía nada, porque las líneas
    iban a `app.log` y él miraba el panel de la app. Para una tarea de 51 selecciones eso es
    inservible — el progreso tiene que estar donde está el usuario, no en un archivo aparte.

    El panel ES el log visible, así que esto no contradice "solo log": lo que se descartó fue el
    toast (interrumpe) y el panel de progreso dedicado (es fase 5)."""
    panel: list[str] = []
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane"]), censo=c, on_diagnostic=panel.append)
    for f in _frames()[:2]:
        m._dispatch_state(f, _st())
    censo_lineas = [p for p in panel if p.startswith("[censo]")]
    assert len(censo_lineas) == 2
    assert "Nangong Yu" in censo_lineas[0] and "1/3" in censo_lineas[0]
    assert "Jane" in censo_lineas[1] and "2/3" in censo_lineas[1]


def test_el_panel_no_repite_al_volver_a_pasar_por_un_pj_ya_visto():
    """Mismo criterio que el log: la línea es por flanco. Si repitiera, el panel se llenaría de
    ruido justo cuando el usuario necesita ver qué le falta."""
    panel: list[str] = []
    c = _censo()
    fa, fb, _ = _frames()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane", "Nangong Yu"]), censo=c, on_diagnostic=panel.append)
    for f in (fa, fb, fa):
        m._dispatch_state(f, _st())
    assert len([p for p in panel if p.startswith("[censo]")]) == 2


# --- cierre por hotkey ----------------------------------------------------------------------

def test_f8_esta_registrada_como_hotkey_valida():
    """Si el nombre no está en el mapa, `HotkeyManager.on` tira ValueError y el cierre queda sin
    forma de dispararse. F8 y no F12: esa la reservan depuradores y grabadoras."""
    from app.core.hotkeys import _KEY_NAMES, _VK_CODES
    assert "f8" in _VK_CODES and _KEY_NAMES["f8"] == "cerrar_censo"


def test_cerrar_censo_emite_reporte_y_resumen(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("DANIBOD_READONLY", "1")     # no tocar dominio en el test
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    m.cerrar_censo()                       # advierte por los pendientes
    reg = m.cerrar_censo()                 # confirma
    assert reg is not None and reg["completo"] is True
    assert set(reg["huerfanos"]) == {"Jane", "Ellen"}
    assert list((tmp_path / "audit" / "censos").glob("*.md"))


def test_cerrar_censo_marca_los_huerfanos_de_verdad_en_el_dominio(tmp_path, monkeypatch):
    """Este test existe por un fallo propio: `cerrar_censo` usaba `datetime` sin importarlo (en
    este módulo solo se importa dentro de otras funciones), tiraba NameError, y el `except` que
    envuelve la marca se lo comía. Los huérfanos no se marcaban **en silencio**.

    El test anterior no lo vio porque corría en readonly y solo miraba el reporte. Verificar el
    efecto real —la fila del dominio— es lo único que distingue "se marcó" de "se intentó"."""
    import sqlite3
    dom = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(dom)
    con.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, notas TEXT)")
    con.executemany("INSERT INTO agents (id, nombre, notas) VALUES (?,?,?)",
                    [(i, n, None) for i, n in _ROSTER])
    con.commit(); con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(dom))
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)

    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    m.cerrar_censo()                       # advierte
    m.cerrar_censo()                       # confirma

    con = sqlite3.connect(dom)
    notas = dict(con.execute("SELECT nombre, notas FROM agents"))
    con.close()
    assert notas["Nangong Yu"] is None, "el visto no se marca"
    for huerfano in ("Jane", "Ellen"):
        assert notas[huerfano] and "no_visto_en_censo_" in notas[huerfano]


# --- la guarda del cierre parcial -------------------------------------------------------------

def test_una_pasada_COMPLETA_cierra_al_primer_F8(tmp_path, monkeypatch):
    """Sin pendientes no hay nada que advertir: cero fricción en el caso normal."""
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane", "Ellen"]), censo=c)
    for f in _frames():
        m._dispatch_state(f, _st())
    assert m.cerrar_censo() is not None


def test_una_pasada_PARCIAL_no_cierra_al_primer_F8_y_dice_a_quienes_declararia_huerfanos():
    """Riesgo real, visto en vivo el 2026-08-17: tras cerrar una pasada completa, volver al menú
    a revisar unos pocos PJs abre una corrida NUEVA. Cerrarla ahí declararía huérfanos a los 49
    por los que no se volvió a pasar — y el reporte mentiría con cara de completo.

    El cierre es una DECLARACIÓN, así que cuando lo que se va a declarar es grande, se pide
    decirlo dos veces."""
    panel: list[str] = []
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c, on_diagnostic=panel.append)
    m._dispatch_state(_frames()[0], _st())
    assert m.cerrar_censo() is None, "no debe cerrar de una con pendientes"
    assert c.abierta, "la corrida sigue viva"
    aviso = " ".join(p for p in panel if "censo" in p)
    assert "2" in aviso and ("Jane" in aviso and "Ellen" in aviso)


def test_el_segundo_F8_confirma_y_cierra(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    assert m.cerrar_censo() is None
    reg = m.cerrar_censo()
    assert reg is not None
    assert set(reg["huerfanos"]) == {"Jane", "Ellen"}


def test_la_confirmacion_caduca_y_vuelve_a_advertir(monkeypatch):
    """Si el aviso quedó armado hace rato, el segundo F8 ya no es una confirmación consciente:
    puede ser el usuario intentando cerrar de nuevo sin haber leído nada."""
    import app.core.monitor as mon
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    assert m.cerrar_censo() is None
    m._cierre_pedido_ts -= mon._CIERRE_CONFIRM_S + 1.0
    assert m.cerrar_censo() is None, "caducada: vuelve a advertir en vez de cerrar"
    assert c.abierta


def test_cerrar_censo_sin_corrida_no_revienta():
    m = _monitor(_SeqOcr(["Nangong Yu"]))
    assert m.cerrar_censo() is None


def test_cerrar_censo_dos_veces_no_duplica_el_reporte(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    m.cerrar_censo()                       # advierte
    assert m.cerrar_censo() is not None    # confirma y cierra
    assert m.cerrar_censo() is None, "ya no hay pasada abierta"
    assert len(list((tmp_path / "audit" / "censos").glob("*.json"))) == 1


def test_una_corrida_cerrada_deja_de_acumular():
    c = _censo()
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane"]), censo=c)
    m._dispatch_state(_frames()[0], _st())
    c.cerrar(ts=10.0)
    m._dispatch_state(_frames()[1], _st())
    assert {r.clave for r in c.vistos} == {"Nangong Yu"}

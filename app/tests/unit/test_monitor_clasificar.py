"""`Monitor._clasificar`: primero el atajo `sigue_en`, después la clasificación completa (fase 2 del hito
"El ritmo de Daniel"). Con un detector falso que cuenta llamadas."""
from __future__ import annotations


from app.core.detector import ScreenState


class _Det:
    def __init__(self, sigue=None):
        self.sigue = sigue
        self.completas = 0
        self.atajos = 0

    def sigue_en(self, code, frame):
        self.atajos += 1
        return self.sigue

    def classify(self, frame):
        self.completas += 1
        return ScreenState("S11", 0.99, "s11_desmontaje.png")


def _monitor(det):
    import app.core.monitor as mon
    m = mon.Monitor(ocr=object(), detector=det)
    return m


S11 = ScreenState("S11", 0.99, "s11_desmontaje.png")
SIGUE = ScreenState("S11", 0.98, "s11_desmontaje.png", method="sigue")


def test_sin_pantalla_confirmada_clasifica_completo():
    det = _Det(sigue=SIGUE)
    m = _monitor(det)
    assert m._clasificar(None, 10.0).code == "S11"
    assert (det.completas, det.atajos) == (1, 0)


def test_con_pantalla_confirmada_usa_el_atajo():
    det = _Det(sigue=SIGUE)
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)                       # completa: arranca la red
    st = m._clasificar(None, 10.3)
    assert st.method == "sigue"
    assert (det.completas, det.atajos) == (1, 1)


def test_si_el_atajo_no_afirma_clasifica_completo():
    det = _Det(sigue=None)
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)
    m._clasificar(None, 10.3)
    assert det.completas == 2


def test_la_red_clasifica_completo_cada_tanto():
    import app.core.monitor as mon
    det = _Det(sigue=SIGUE)
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)
    m._clasificar(None, 10.0 + mon._RED_CLASIFICACION_S + 0.01)
    assert det.completas == 2


def test_un_detector_sin_atajo_o_un_mock_no_rompe():
    """Los tests con MagicMock devuelven un MagicMock de `sigue_en`: no es un ScreenState."""
    from unittest.mock import MagicMock
    det = MagicMock()
    det.classify.return_value = S11
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)
    assert m._clasificar(None, 10.3) is S11


def test_el_interruptor_lo_apaga(monkeypatch):
    monkeypatch.setenv("DANIBOD_SIN_SIGUE", "1")
    det = _Det(sigue=SIGUE)
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)
    m._clasificar(None, 10.3)
    assert (det.completas, det.atajos) == (2, 0)


def test_si_el_atajo_revienta_clasifica_completo():
    class _Roto(_Det):
        def sigue_en(self, code, frame):
            raise RuntimeError("boom")
    det = _Roto()
    m = _monitor(det)
    m._confirmed_state = S11
    m._clasificar(None, 10.0)
    assert m._clasificar(None, 10.3).code == "S11"
    assert det.completas == 2


# --- Fase 3: los modales breves se confirman con un frame -------------------------------------

def _buffer_con(*codes):
    from app.core.detector import TemporalBuffer
    b = TemporalBuffer(window_size=3)
    for c in codes:
        b.add(ScreenState(c, 0.99, "x"))
    return b


def test_la_confirmacion_del_desmontaje_se_confirma_con_un_frame():
    """S25 vive 0,75-1,5 s: con el voto 2/3 no se vio nunca en la línea de base del 2026-10-03."""
    from app.core.monitor import Monitor
    b = _buffer_con("S11", "S11", "S11")
    st = Monitor._votar(b, ScreenState("S25", 0.99, "s23_sustitucion.png", method="template"))
    assert st is not None and st.code == "S25"


def test_un_estado_comun_sigue_votando_dos_de_tres():
    from app.core.monitor import Monitor
    b = _buffer_con("S11", "S11", "S11")
    assert Monitor._votar(b, ScreenState("S5", 0.99, "s5.png", method="template")) is None


def test_un_modal_que_no_vino_del_template_verificado_no_se_promueve():
    from app.core.monitor import Monitor
    b = _buffer_con("S11", "S11", "S11")
    assert Monitor._votar(b, ScreenState("S24", 0.55, "hsv", method="hsv")) is None


# --- Los modales breves se despachan en el ciclo en que se confirman ----------------------------

def test_un_modal_recien_confirmado_se_despacha_sin_esperar_la_cadencia():
    """Reproducción 2026-10-03: S24 confirmado, despacho diferido por cadencia, tanda abandonada."""
    from app.core.monitor import Monitor
    s24 = ScreenState("S24", 1.0, "s24_obtenido_desmontaje.png")
    assert Monitor._debe_despachar(False, 120.0, 500, s24, continuous=True)


def test_un_estado_comun_respeta_la_cadencia():
    from app.core.monitor import Monitor
    s5 = ScreenState("S5", 1.0, "s5.png")
    assert not Monitor._debe_despachar(False, 120.0, 1000, s5, continuous=True)
    assert Monitor._debe_despachar(False, 1200.0, 1000, s5, continuous=True)


def test_un_modal_ya_confirmado_respeta_la_cadencia():
    """Sólo la TRANSICIÓN se apura: mientras el modal sigue en pantalla, cadencia de siempre."""
    from app.core.monitor import Monitor
    assert not Monitor._debe_despachar(False, 120.0, 500, None, continuous=True)

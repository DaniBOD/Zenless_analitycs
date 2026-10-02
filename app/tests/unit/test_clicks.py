"""`ClickListener`: los clicks sobre el juego, sólo lectura (hito "El ritmo de Daniel", 2026-10-02).

Sin hook real: el listener de pynput se inyecta. Lo que se prueba es lo que decide la clase:
sólo el apretar, sólo con el juego enfocado, sólo dentro de la ventana, normalizado a 0-1.
"""
from __future__ import annotations

from app.core.capturer import WindowBounds
from app.core.clicks import Click, ClickListener

VENTANA = WindowBounds(left=100, top=50, width=2000, height=1000, title="ZZZ", hwnd=7)


class _Boton:
    def __init__(self, name):
        self.name = name


class _ListenerFalso:
    def __init__(self, on_click):
        self.on_click = on_click
        self.iniciado = self.parado = False

    def start(self):
        self.iniciado = True

    def stop(self):
        self.parado = True


def _listener(enfocado=True, ventana=VENTANA):
    reloj = iter(float(i) for i in range(1, 1000))
    fabricados = []

    def fabrica(cb):
        fabricados.append(_ListenerFalso(cb))
        return fabricados[-1]

    cl = ClickListener(lambda: ventana, foco_fn=lambda _v: enfocado,
                       listener_factory=fabrica, reloj=lambda: next(reloj))
    assert cl.start()
    return cl, fabricados[0]


def test_un_click_se_guarda_normalizado_a_la_ventana():
    cl, hook = _listener()
    hook.on_click(1100, 550, _Boton("left"), True)
    assert cl.desde(0.0) == [Click(t=1.0, x=0.5, y=0.5, boton="left")]
    assert cl.evento.is_set()


def test_soltar_el_boton_no_cuenta():
    cl, hook = _listener()
    hook.on_click(1100, 550, _Boton("left"), False)
    assert cl.desde(0.0) == []
    assert not cl.evento.is_set()


def test_sin_el_juego_enfocado_no_se_registra():
    """Un click en el navegador o en la app no es del juego."""
    cl, hook = _listener(enfocado=False)
    hook.on_click(1100, 550, _Boton("left"), True)
    assert cl.desde(0.0) == []


def test_fuera_de_la_ventana_no_se_registra():
    cl, hook = _listener()
    hook.on_click(50, 550, _Boton("left"), True)        # a la izquierda del juego
    hook.on_click(1100, 1200, _Boton("left"), True)     # debajo
    assert cl.desde(0.0) == []


def test_sin_ventana_no_se_registra():
    cl, hook = _listener(ventana=None)
    hook.on_click(1100, 550, _Boton("left"), True)
    assert cl.desde(0.0) == []


def test_desde_devuelve_solo_los_posteriores_en_orden():
    cl, hook = _listener()
    for x in (300, 700, 1500):
        hook.on_click(x, 550, _Boton("left"), True)
    assert [c.x for c in cl.desde(1.0)] == [0.3, 0.7]
    assert cl.ultimo().x == 0.7


def test_un_callback_que_falla_no_mata_el_hook():
    """Una excepción en el callback de pynput detiene el listener entero."""
    cl = ClickListener(lambda: 1 / 0, foco_fn=lambda _v: True,
                       listener_factory=_ListenerFalso)
    cl.start()
    cl._on_click(1100, 550, _Boton("left"), True)       # no levanta
    assert cl.desde(0.0) == []


def test_si_el_hook_no_arranca_la_app_sigue_sin_clicks():
    def roto(_cb):
        raise OSError("sin hook")
    cl = ClickListener(lambda: VENTANA, listener_factory=roto)
    assert cl.start() is False
    cl.stop()                                            # no levanta


def test_stop_para_el_hook():
    cl, hook = _listener()
    cl.stop()
    assert hook.parado

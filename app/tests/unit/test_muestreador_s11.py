"""`MuestreadorS11`: una muestra por cada cambio de tildes en S11 (hito "El ritmo de Daniel")."""
from __future__ import annotations

import numpy as np

from app.core.muestreador_s11 import ROI_HEADER, ROI_PANEL, MuestreadorS11


def _frame(v=40, h=144, w=256):
    f = np.full((h, w, 3), v, np.uint8)
    return f


def _muestreador(frames, tildes, es_s11=lambda f: True, max_pendientes=32):
    it_f, it_t = iter(frames), iter(tildes)
    reloj = iter(float(i) for i in range(100))
    return MuestreadorS11(capturar=lambda: next(it_f), es_s11=es_s11,
                          tildes_fn=lambda f: next(it_t), scroll_fn=lambda f: 0.2,
                          reloj=lambda: next(reloj), max_pendientes=max_pendientes,
                          con_hilo=False)


def test_la_primera_vuelta_guarda_la_referencia_y_después_sólo_los_cambios():
    """La referencia (tildes + contador de partida) es lo que deja confirmar el primer click."""
    m = _muestreador([_frame()] * 2, [frozenset({(0, 0)})] * 2)
    primera = m.paso()
    assert primera is not None and primera.referencia
    assert m.paso() is None
    assert [x.referencia for x in m.drenar()] == [True]


def test_cada_cambio_de_tildes_deja_una_muestra_en_orden():
    """Dos clicks entre dos vueltas del loop: el muestreador los ve por separado."""
    t = [frozenset(), frozenset({(0, 0)}), frozenset({(0, 0)}), frozenset({(0, 0), (0, 1)})]
    m = _muestreador([_frame()] * 4, t)
    for _ in range(4):
        m.paso()
    ms = m.drenar()
    assert [x.tildes for x in ms] == [t[0], t[1], t[3]]
    assert [x.referencia for x in ms] == [True, False, False]
    assert m.drenar() == []                       # drenar vacía


def test_fuera_de_s11_no_muestrea():
    """Con el diálogo de confirmación encima no hay tildes que contar: no se guarda nada."""
    m = _muestreador([_frame()] * 3, [frozenset(), frozenset({(0, 0)}), frozenset()],
                     es_s11=lambda f: False)
    for _ in range(3):
        m.paso()
    assert m.drenar() == []


def test_sin_frame_no_rompe():
    m = _muestreador([None], [frozenset()])
    assert m.paso() is None


def test_la_muestra_se_reconstruye_con_sus_recortes_en_su_lugar():
    f = np.zeros((144, 256, 3), np.uint8)
    f[:, :] = (np.arange(256) % 255).astype(np.uint8)[None, :, None]      # cada columna distinta
    m = _muestreador([f, f], [frozenset(), frozenset({(1, 2)})])
    m.paso(); m.paso()
    _ref, mu = m.drenar()
    r = mu.reconstruir()
    assert r.shape == f.shape
    for roi in (ROI_HEADER, ROI_PANEL):
        x, y, w, h = roi
        x0, y0 = int(x * 256), int(y * 144)
        x1, y1 = min(256, int((x + w) * 256)), min(144, int((y + h) * 144))
        assert np.array_equal(r[y0:y1, x0:x1], f[y0:y1, x0:x1])
    assert r[140, 5].sum() == 0                    # fuera de los recortes, negro


def test_con_el_tope_lleno_descarta_las_más_viejas_y_las_cuenta():
    t = [frozenset()] + [frozenset({(0, i)}) for i in range(5)]
    m = _muestreador([_frame()] * 6, t, max_pendientes=3)
    for _ in range(6):
        m.paso()
    ms = m.drenar()
    assert [x.tildes for x in ms] == t[3:]
    assert m.descartadas == 3                     # la referencia y los dos primeros cambios


def test_activar_reinicia_la_referencia():
    t = [frozenset({(0, 0)}), frozenset({(0, 0), (0, 1)}), frozenset({(0, 5)})]
    m = _muestreador([_frame()] * 3, t)
    m._activo.set()
    m.paso(); m.paso()
    m.drenar()
    m.desactivar()
    m.activar()                                   # nueva visita: no compara con la vieja
    m.parar()
    assert m.paso().referencia


# --- ProcesadorS11: el OCR de las muestras, fuera del loop -------------------------------------

def test_el_procesador_lee_en_orden_y_el_disco_sólo_cuando_sumó_tildes():
    from app.core.muestreador_s11 import ProcesadorS11
    t = [frozenset(), frozenset({(0, 0)}), frozenset({(0, 0), (0, 1)}), frozenset({(0, 1)})]
    m = _muestreador([_frame()] * 4, t)
    for _ in range(4):
        m.paso()
    contadores = iter([0, 1, 2, 1])
    discos = []
    p = ProcesadorS11(m, contador_fn=lambda f: next(contadores),
                      disco_fn=lambda f: discos.append(1) or f"disco{len(discos)}", con_hilo=False)
    assert p.ocupado                                   # hay muestras sin leer
    assert p.procesar_pendientes() == 4
    ls = p.leidas()
    assert [(le.tildes, le.contador, le.disco) for le in ls] == [
        (t[0], 0, None),                                   # la referencia no lee panel
        (t[1], 1, "disco1"), (t[2], 2, "disco2"), (t[3], 1, None)]   # el destilde tampoco
    assert not p.ocupado and p.leidas() == []


def test_reiniciar_vuelve_a_leer_desde_cero():
    from app.core.muestreador_s11 import ProcesadorS11
    m = _muestreador([_frame()] * 2, [frozenset(), frozenset({(0, 0)})])
    m.paso(); m.paso()
    p = ProcesadorS11(m, contador_fn=lambda f: 1, disco_fn=lambda f: "d", con_hilo=False)
    p._previas = frozenset({(0, 0), (0, 1)})          # quedó de la visita anterior
    p.reiniciar()
    p.procesar_pendientes()
    assert p.leidas()[1].disco == "d"


def test_la_referencia_con_selección_empezada_no_lee_panel():
    """Al entrar con dos discos ya marcados, el panel muestra el último: atribuírselo a la
    referencia sería adivinar cuál de los dos es (RNF-02)."""
    from app.core.muestreador_s11 import ProcesadorS11
    m = _muestreador([_frame()], [frozenset({(0, 0), (0, 1)})])
    m.paso()
    p = ProcesadorS11(m, contador_fn=lambda f: 2, disco_fn=lambda f: "d", con_hilo=False)
    p.procesar_pendientes()
    assert p.leidas()[0].disco is None

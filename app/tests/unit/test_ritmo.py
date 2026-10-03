"""Verdad de tierra de una grabación vs lo que la app vio (hito "El ritmo de Daniel").

Casos armados con lo medido el 2026-10-02: una tanda de S11 con clicks cada segundo, una
confirmación cuyo "Obtenido" no llegó a verse, una mejora rápida y el panel del Obtenido.
"""
from __future__ import annotations

from app.core.ritmo import ObsFrame, comparar, corridas, eventos_de_verdad, kpis_de_log, reporte_md


def _o(t, estado, **kw):
    return ObsFrame(t=t, estado=estado, **kw)


def test_corridas_agrupan_frames_consecutivos():
    cs = corridas([_o(0, "S11"), _o(1, "S11"), _o(2, "S25"), _o(2.4, "S24"), _o(3, "S11")])
    assert [(c.estado, c.t_ini, c.t_fin) for c in cs] == [
        ("S11", 0, 2), ("S25", 2, 2.4), ("S24", 2.4, 3), ("S11", 3, 3)]


def test_s11_cuenta_cada_subida_del_contador():
    obs = [_o(0, "S11", contador_s11=0), _o(1, "S11", contador_s11=1),
           _o(1.5, "S11", contador_s11=3),           # dos clicks entre frames: igual son 2
           _o(2, "S11", contador_s11=2),             # destilde: no suma
           _o(3, "S11", contador_s11=4)]
    assert eventos_de_verdad(obs).s11_marcados == 5


def test_tanda_confirmada_por_el_obtenido_o_por_la_seleccion_vaciada():
    """La tercera tanda del 2026-10-02: S25 → S11 sin "Obtenido" visto, con la selección en 0."""
    obs = [_o(0, "S11", contador_s11=10), _o(1, "S25"), _o(2, "S24"), _o(3, "S11", contador_s11=0),
           _o(4, "S11", contador_s11=10), _o(5, "S25"), _o(6, "S11", contador_s11=0),
           _o(7, "S11", contador_s11=3), _o(8, "S25"), _o(9, "S11", contador_s11=3)]   # canceló
    assert eventos_de_verdad(obs).s11_tandas_confirmadas == 2


def test_s10_cuenta_los_niveles_de_cada_visita():
    obs = [_o(0, "S10", nivel_s10=0), _o(0.5, "S10", nivel_s10=3), _o(1, "S7"),
           _o(2, "S10", nivel_s10=3), _o(2.2, "S10", nivel_s10=15)]
    assert eventos_de_verdad(obs).s10_niveles == 15


def test_s22_cuenta_discos_distintos():
    obs = [_o(0, "S22", panel_s22="a"), _o(1, "S22", panel_s22="a"), _o(2, "S22", panel_s22="b"),
           _o(3, "S22")]
    assert eventos_de_verdad(obs).s22_discos == 2


LOG = """\
2026-10-02 13:55:10 INFO app.core.monitor :: [estado] S9 → S11 (conf=0.96)
2026-10-02 13:57:21 INFO app.core.monitor :: [estado] S11 → S25 (conf=0.99)
2026-10-02 13:57:26 INFO app.core.monitor :: [estado] S25 → S24 (conf=1.00)
2026-10-02 13:57:26 INFO app.core.monitor :: [desmontaje] tanda cerrada · 63 desmontados (41 con datos, 22 sin) · material ×63 ✓
2026-10-02 13:44:26 INFO app.core.sync_upgrade :: Upgrade S10: [mejora] nivel 0→3 · sin cambio de roll
2026-10-02 13:44:18 INFO app.core.monitor :: Disco S22 (extracción): [disco] Hado emplumado · slot 5
""".splitlines()


def test_kpis_de_log_lee_las_lineas_de_un_evento():
    k = kpis_de_log(LOG)
    assert (k.s11_declarados, k.s11_con_datos, k.s11_sin_datos, k.s11_tandas_cerradas) == (63, 41, 22, 1)
    assert (k.s10_niveles, k.s22_discos) == (3, 1)
    assert k.breves["S25"] == 1 and k.breves["S24"] == 1


def test_comparar_y_reporte():
    obs = [_o(0, "S11", contador_s11=0)] + [_o(i, "S11", contador_s11=i) for i in range(1, 64)] + \
          [_o(70, "S25"), _o(71, "S24"), _o(72, "S11", contador_s11=0)]
    filas = comparar(eventos_de_verdad(obs), kpis_de_log(LOG))
    s11 = filas[0]
    assert (s11.verdad, s11.app) == (63, 41)
    assert round(s11.cobertura, 2) == 0.65
    md = reporte_md("base", filas)
    assert "| S11 · discos marcados con datos | 63 | 41 | 65% |" in md


def test_los_parpadeos_de_s12_no_parten_una_visita():
    """Grabación 2026-10-03: S10 0,0 · S12 (0,12 s) · S10 3 era UNA visita con la subida 0→3."""
    obs = [_o(86.14, "S10", nivel_s10=0), _o(87.9, "S10", nivel_s10=0), _o(87.95, "S12"),
           _o(88.08, "S10", nivel_s10=0), _o(88.84, "S12"), _o(89.09, "S10", nivel_s10=3),
           _o(91.5, "S5")]
    v = eventos_de_verdad(obs)
    assert v.s10_niveles == 3
    assert [c.estado for c in v.corridas] == ["S10", "S5"]


def test_un_s12_largo_si_es_una_pantalla():
    obs = [_o(0, "S10", nivel_s10=0), _o(1, "S12"), _o(3, "S10", nivel_s10=3)]
    assert [c.estado for c in eventos_de_verdad(obs).corridas] == ["S10", "S12", "S10"]


def test_al_confirmar_el_juego_muestra_s11_con_la_seleccion_antes_del_obtenido():
    """Grabación 2026-10-03: S25 → S11 (todavía 4/300) → S24."""
    obs = [_o(71, "S11", contador_s11=4), _o(74.6, "S25"), _o(76.27, "S11", contador_s11=4),
           _o(76.66, "S24"), _o(77.41, "S11", contador_s11=0)]
    assert eventos_de_verdad(obs).s11_tandas_confirmadas == 1


def test_una_seleccion_nueva_despues_de_s25_es_cancelacion():
    """Cancelar deja la selección; si sigue marcando, el Obtenido que venga después no es de esa
    confirmación."""
    obs = [_o(0, "S11", contador_s11=4), _o(1, "S25"), _o(2, "S11", contador_s11=4),
           _o(3, "S11", contador_s11=6), _o(4, "S24")]
    assert eventos_de_verdad(obs).s11_tandas_confirmadas == 0

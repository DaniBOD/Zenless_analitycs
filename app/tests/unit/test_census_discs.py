"""Censo de discos: el contador del header manda, y la brecha se dice en voz alta.

El censo del roster se construyó sobre una ausencia: *"el menú de personajes no tiene contador
`N/M`"*. De ahí salieron la asimetría PENDIENTE ≠ HUÉRFANO y el cierre explícito por F8 — sin
denominador, sólo una declaración humana puede decir que la pasada terminó.

**Para discos eso no aplica.** El header del inventario dice `Pistas de disco [339/3000]`, igual que
el `N/300` del desmontaje. Hay denominador escrito en pantalla, así que el censo puede saber cuánto
le falta sin preguntar.

## La trampa que el contador destapa

El sistema deduplica discos por identidad, y **22 pares del inventario real son indistinguibles**
(345 identidades para 367 discos). Con 339 en pantalla, una pasada perfecta registra ~317 y **nunca
llega a 339**.

Declarar "completa" al llegar al total sería una condición que no se cumple jamás; bajar el
criterio para que cierre sería mentir sobre la cobertura. La salida es la misma que en el roster:
**el censo reporta la brecha y dice que no puede cerrarla solo.** Que el resto sean gemelos o discos
sin visitar es una pregunta distinta, y el censo no la contesta a las apuradas.
"""
from __future__ import annotations

import pytest

from app.core.census_discs import (
    COMPLETA,
    EN_CURSO,
    SIN_ANCLA,
    DiscCensus,
    DiscSighting,
)


def _s(n: int, *, libre: bool = False, dueno: str | None = None) -> DiscSighting:
    """Avistamiento sintético: la identidad es opaca para el censo, sólo tiene que ser hashable."""
    return DiscSighting(identidad=("set", n % 6 + 1, f"main{n}", ()), libre=libre, dueno=dueno)


def _censo(total: int | None = None) -> DiscCensus:
    c = DiscCensus()
    c.ensure_open(ts=0.0)
    if total is not None:
        c.anclar_total(total, ts=0.0)
    return c


# --- el ancla ---------------------------------------------------------------------------------

def test_sin_contador_leido_el_censo_no_finge_denominador():
    """`None` del OCR significa 'no pude leer', nunca 'cero'. Sin ancla no hay cobertura que
    reportar — es la misma regla que en el contador del desmontaje."""
    c = _censo()
    c.observe(_s(1), ts=1.0)
    assert c.estado == SIN_ANCLA
    assert c.total is None
    assert c.faltan is None, "no se puede restar contra un total que no se leyó"
    assert c.progreso == (1, None)


def test_el_contador_del_header_fija_el_denominador():
    c = _censo(total=339)
    assert c.estado == EN_CURSO
    assert c.total == 339
    assert c.faltan == 339


def test_un_contador_ilegible_no_borra_el_ancla_que_ya_habia():
    """Un frame de transición devuelve None; perder el denominador por eso dejaría al censo
    ciego a mitad de la pasada."""
    c = _censo(total=339)
    c.anclar_total(None, ts=1.0)
    assert c.total == 339


# --- el conteo --------------------------------------------------------------------------------

def test_registra_por_identidad_y_no_cuenta_dos_veces_el_mismo_disco():
    """Una pasada de scroll ve el mismo disco en muchos frames. Sin dedup el censo se declararía
    completo sin haber recorrido nada."""
    c = _censo(total=10)
    for _ in range(5):
        c.observe(_s(1), ts=1.0)
    assert c.registrados == 1
    assert c.faltan == 9


def test_discos_distintos_suman():
    c = _censo(total=10)
    for i in range(4):
        c.observe(_s(i), ts=1.0)
    assert c.registrados == 4 and c.faltan == 6


def test_separa_los_libres_de_los_que_tienen_dueno():
    """El censo necesita las dos cuentas: los libres son los que hasta ahora se veían y se tiraban,
    y saber cuántos son es media validación de la pasada."""
    c = _censo(total=10)
    c.observe(_s(1, dueno="Ellen"), ts=1.0)
    c.observe(_s(2, libre=True), ts=1.0)
    c.observe(_s(3, libre=True), ts=1.0)
    assert c.con_dueno == 1
    assert c.libres == 2


def test_un_disco_sin_dueno_y_sin_afirmacion_cuenta_pero_queda_marcado():
    """Se lo vio (suma a la cobertura) pero no se pudo decir si está libre. Mezclarlo con los
    libres inflaría una cuenta que después se usa para validar."""
    c = _censo(total=10)
    c.observe(_s(1), ts=1.0)
    assert c.registrados == 1
    assert c.libres == 0 and c.con_dueno == 0
    assert c.sin_resolver == 1


# --- el cierre, que es donde está el punto ----------------------------------------------------

def test_llegar_al_total_declara_la_pasada_completa():
    c = _censo(total=3)
    for i in range(3):
        c.observe(_s(i), ts=1.0)
    assert c.estado == COMPLETA
    assert c.faltan == 0


def test_una_pasada_a_la_que_le_faltan_discos_NO_se_declara_completa():
    c = _censo(total=5)
    for i in range(3):
        c.observe(_s(i), ts=1.0)
    assert c.estado == EN_CURSO
    assert c.faltan == 2


def test_la_brecha_por_GEMELOS_se_reporta_en_vez_de_cerrarse_a_la_fuerza():
    """El caso real: 339 en pantalla, 22 pares indistinguibles ⇒ el techo alcanzable es 317.

    Declarar completa al llegar sería una condición que no se cumple nunca; relajar el criterio
    sería mentir sobre la cobertura. El censo dice cuánto falta y que no puede cerrarlo solo."""
    c = _censo(total=339)
    for i in range(317):
        c.observe(_s(i), ts=1.0)
    assert c.estado == EN_CURSO
    assert c.faltan == 22
    aviso = c.motivo_incompleto()
    assert aviso is not None
    assert "22" in aviso
    assert "gemelo" in aviso.lower() or "indistinguible" in aviso.lower(), \
        "tiene que nombrar la causa probable, no sólo el número"


def test_registrar_de_mas_que_el_total_tampoco_se_esconde():
    """Si el censo registra más identidades que las que el header dice que existen, algo está mal
    (contador viejo, o dos pasadas mezcladas). Callarlo dejaría una cobertura > 100 %."""
    c = _censo(total=3)
    for i in range(5):
        c.observe(_s(i), ts=1.0)
    assert c.estado == COMPLETA
    assert c.faltan == 0, "no se reporta una falta negativa"
    assert c.excedente == 2
    assert c.motivo_incompleto() is None


# --- el inventario cambia durante la pasada ---------------------------------------------------

def test_si_el_contador_CAMBIA_el_censo_se_re_ancla_y_lo_dice():
    """Farmear o desmontar durante la pasada mueve el denominador. Quedarse con el viejo daría una
    cobertura falsa; cambiarlo en silencio borraría la única pista de que el inventario se movió."""
    c = _censo(total=339)
    c.observe(_s(1), ts=1.0)
    c.anclar_total(341, ts=2.0)
    assert c.total == 341
    assert any("339" in a and "341" in a for a in c.avisos), \
        "el cambio de denominador tiene que quedar registrado"


def test_el_mismo_contador_leido_mil_veces_no_llena_los_avisos():
    """El header se lee en cada frame; avisar por lectura en vez de por cambio ahogaría el log."""
    c = _censo(total=339)
    for _ in range(50):
        c.anclar_total(339, ts=1.0)
    assert c.avisos == []


# --- resumen ----------------------------------------------------------------------------------

def test_el_resumen_trae_lo_que_hace_falta_para_decidir():
    c = _censo(total=339)
    c.observe(_s(1, dueno="Ellen"), ts=1.0)
    c.observe(_s(2, libre=True), ts=1.0)
    r = c.resumen()
    assert r["total_pantalla"] == 339
    assert r["registrados"] == 2
    assert r["libres"] == 1 and r["con_dueno"] == 1
    assert r["faltan"] == 337
    assert r["estado"] == EN_CURSO


def test_observar_sobre_una_corrida_cerrada_es_no_op():
    c = _censo(total=5)
    c.observe(_s(1), ts=1.0)
    c.cerrar(ts=2.0)
    c.observe(_s(2), ts=3.0)
    assert c.registrados == 1


def test_observar_sin_abrir_no_explota_ni_cuenta():
    c = DiscCensus()
    c.observe(_s(1), ts=1.0)
    assert c.registrados == 0
    assert c.estado == SIN_ANCLA


@pytest.mark.parametrize("total", [0, -1])
def test_un_total_absurdo_no_se_acepta(total):
    """RNF-02: un OCR que devuelva 0 o un negativo no puede fijar el denominador."""
    c = _censo()
    c.anclar_total(total, ts=0.0)
    assert c.total is None and c.estado == SIN_ANCLA

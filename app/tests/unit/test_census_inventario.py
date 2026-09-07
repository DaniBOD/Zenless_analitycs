"""La generalización del censo de inventario: lo que cambia por entidad y lo que NO.

`census_discs.py` pasó a `census_inventario.py` el 2026-09-06 para servir también al inventario de
W-Engines. La regla de la generalización es que **no parametriza conducta**: la aritmética de
cobertura es una sola (B1), y lo único que depende de la entidad es un texto.

El guard de que el flujo de discos no se movió NO está acá: está en `test_census_discs.py`, que
sigue importando los nombres viejos y corriendo los mismos 20 tests de siempre. Que aquellos sigan
verdes es la mitad de esta verificación.
"""
from __future__ import annotations

from app.core.census_inventario import (
    COMPLETA,
    EN_CURSO,
    SIN_ANCLA,
    DiscCensus,
    DiscSighting,
    InventoryCensus,
    Sighting,
)


def _s(n, **kw):
    return Sighting(identidad=("fila", n), **kw)


# --- los alias: el flujo de discos no se entera -------------------------------------------------

def test_los_nombres_viejos_siguen_siendo_los_mismos_objetos():
    assert DiscCensus is InventoryCensus
    assert DiscSighting is Sighting


def test_la_entidad_por_defecto_es_discos():
    """Construir sin argumentos tiene que seguir dando exactamente el censo de discos: el monitor
    hace `DiscCensus()` pelado."""
    assert InventoryCensus().entidad == "discos"


# --- lo único que la entidad cambia -------------------------------------------------------------

def test_la_entidad_solo_cambia_el_texto_de_la_brecha():
    """Mismos números, distinta causa nombrada. Si la entidad cambiara algún conteo, dejaría de ser
    una generalización y sería dos censos con un solo nombre."""
    def _armar(entidad):
        c = InventoryCensus(entidad=entidad)
        c.ensure_open(ts=0.0)
        c.anclar_total(10, ts=0.0)
        for i in range(4):
            c.observe(_s(i), ts=0.0)
        return c

    discos, armas = _armar("discos"), _armar("armas")
    assert discos.resumen()["faltan"] == armas.resumen()["faltan"] == 6
    assert discos.registrados == armas.registrados == 4
    assert discos.estado == armas.estado == EN_CURSO
    assert "gemelos" in discos.motivo_incompleto()
    assert "W-Engine" in armas.motivo_incompleto()
    assert "gemelos" not in armas.motivo_incompleto()


def test_una_entidad_desconocida_cae_a_un_texto_generico():
    """No puede quedarse sin motivo por no tener entrada en el mapa: la brecha se reporta igual."""
    c = InventoryCensus(entidad="lo que sea")
    c.ensure_open(ts=0.0)
    c.anclar_total(5, ts=0.0)
    motivo = c.motivo_incompleto()
    assert motivo and "faltan 5 de 5" in motivo


def test_el_resumen_declara_que_se_censo():
    c = InventoryCensus(entidad="armas")
    assert c.resumen()["entidad"] == "armas"


# --- fuera de catálogo: la causa de brecha que discos no tiene ----------------------------------

def test_lo_que_no_esta_en_el_catalogo_cuenta_para_la_cobertura_pero_se_reporta_aparte():
    """Un arma fuera del catálogo se VIO —cuenta como recorrida— pero no se puede persistir
    (`weapon_id` es NOT NULL contra una tabla curada). Meterla en `faltan` haría el número
    ilegible: es una parte esperada y explicable de la diferencia."""
    c = InventoryCensus(entidad="armas")
    c.ensure_open(ts=0.0)
    c.anclar_total(3, ts=0.0)
    c.observe(_s(1, dueno="Jane"), ts=0.0)
    c.observe(_s(2, en_catalogo=False, confirmada=False), ts=0.0)
    r = c.resumen()
    assert r["registrados"] == 2, "el arma sin catálogo se vio, así que cuenta"
    assert r["faltan"] == 1, "y no infla la brecha"
    assert r["fuera_de_catalogo"] == 1


def test_por_defecto_todo_esta_en_catalogo():
    """El campo nace en `True` para que el flujo de discos —que no tiene catálogo que fallar— no
    tenga que declarar nada."""
    c = InventoryCensus()
    c.ensure_open(ts=0.0)
    c.observe(_s(1), ts=0.0)
    assert c.fuera_de_catalogo == 0


# --- la aritmética sigue siendo la de siempre ---------------------------------------------------

def test_el_ancla_y_los_estados_no_se_movieron():
    c = InventoryCensus(entidad="armas")
    c.ensure_open(ts=0.0)
    assert c.estado == SIN_ANCLA
    c.anclar_total(2, ts=0.0)
    c.observe(_s(1), ts=0.0)
    assert c.estado == EN_CURSO
    c.observe(_s(2), ts=0.0)
    assert c.estado == COMPLETA and c.motivo_incompleto() is None


def test_un_total_que_cambia_se_re_ancla_y_avisa():
    c = InventoryCensus(entidad="armas")
    c.ensure_open(ts=0.0)
    c.anclar_total(57, ts=0.0)
    c.anclar_total(54, ts=1.0)
    assert c.total == 54
    assert any("cambió" in a for a in c.avisos)

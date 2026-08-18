"""Contabilidad de cobertura del censo de roster — la Fase 0.

`RosterCensus` es PURO igual que `TeardownBatch`: no toca OCR, ni sqlite, ni Qt. Todo lo que
decide se prueba con tuplas. Acá vive la parte del censo que no se puede verificar mirando una
captura.

**La tesis que estos tests protegen:** un censo que no sabe qué NO vio es peor que no tener
censo, porque produce una foto parcial con cara de completa. De ahí las dos asimetrías que más
se testean:

1. **PENDIENTE ≠ HUÉRFANO.** Un PJ no visto solo se vuelve huérfano cuando el usuario DECLARA
   que terminó el recorrido. El sistema no puede saber si scrolleaste hasta el final (verificado:
   el menú de personajes no tiene contador `N/M`), así que no debe fingir que sí. Corolario
   asumido: una corrida que nunca se cierra no produce huérfanos jamás.
2. **Reportar un PJ nuevo pide más evidencia que reconocer uno conocido.** Declarar uno de más
   dispara el onboarding de un personaje que no existe.
"""
from __future__ import annotations

import pytest

from app.core.census import MenuSighting, RosterCensus

_ROSTER = [(1, "Ellen"), (2, "Astra Yao"), (3, "Nicole"), (4, "Aria")]

# Personajes que EXISTEN en el juego pero que el jugador no posee. En el runtime salen de la
# diferencia entre `avatar_refs/` (56 con arte) y `agents` (51 poseídos).
_CATALOGO = {"Hugo", "Banyue", "Lichter"}


def _censo(roster=None, catalogo=None) -> RosterCensus:
    c = RosterCensus(roster if roster is not None else _ROSTER,
                     catalogo=_CATALOGO if catalogo is None else catalogo)
    c.ensure_open(ts=0.0)
    return c


def _ok(nombre: str, conf: float = 0.97, score: float = 0.95) -> MenuSighting:
    return MenuSighting(nombre=nombre, texto_crudo=nombre, conf=conf,
                        candidato=nombre, score=score, motivo="ok")


# --- siembra ------------------------------------------------------------------------------

def test_al_abrir_todo_el_roster_esta_pendiente():
    c = _censo()
    assert {r.clave for r in c.pendientes} == {"Ellen", "Astra Yao", "Nicole", "Aria"}
    assert c.vistos == [] and c.dudosos == [] and c.nuevos == []
    assert c.resumen()["cobertura"] == 0.0


def test_huerfanos_esta_vacio_mientras_la_corrida_sigue_abierta():
    """La distinción PENDIENTE/HUÉRFANO es el corazón de la fase 0: nadie es huérfano hasta
    que el usuario declara que terminó."""
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    assert c.huerfanos == []


# --- observación --------------------------------------------------------------------------

def test_lectura_buena_marca_visto_y_avisa_una_vez():
    c = _censo()
    d = c.observe(_ok("Ellen"), ts=1.0)
    assert d.estado == "visto" and d.estado_previo == "pendiente"
    assert d.logs, "la primera vez que se ve un PJ tiene que loguear"
    assert [r.clave for r in c.vistos] == ["Ellen"]
    assert "Ellen" not in {r.clave for r in c.pendientes}


def test_reobservar_no_reloguea_pero_acumula():
    c = _censo()
    c.observe(_ok("Ellen", conf=0.90), ts=1.0)
    d = c.observe(_ok("Ellen", conf=0.99), ts=2.0)
    assert d.logs == [], "volver a pasar por el mismo PJ no vuelve a loguear"
    fila = c.vistos[0]
    assert fila.n_obs == 2
    assert fila.conf_max == pytest.approx(0.99)
    assert fila.ts_ultima == 2.0 and fila.ts_primera == 1.0


@pytest.mark.parametrize("conf,score", [(0.55, 0.95), (0.97, 0.60)])
def test_confianza_o_similitud_baja_dejan_dudoso(conf, score):
    """Son dos señales distintas: `conf` es qué tan seguro está el OCR de los CARACTERES,
    `score` qué tan seguro está el sistema de la IDENTIDAD. Cualquiera de las dos baja alcanza
    para pedir repetición."""
    c = _censo()
    c.observe(MenuSighting("Ellen", "Ellen", conf, "Ellen", score, "ok"), ts=1.0)
    assert [r.clave for r in c.dudosos] == ["Ellen"]
    assert c.vistos == []


def test_un_dudoso_se_confirma_con_una_lectura_buena():
    c = _censo()
    c.observe(MenuSighting("Ellen", "Ellen", 0.50, "Ellen", 0.95, "ok"), ts=1.0)
    d = c.observe(_ok("Ellen"), ts=2.0)
    assert d.estado_previo == "dudoso" and d.estado == "visto"
    assert c.dudosos == [] and [r.clave for r in c.vistos] == ["Ellen"]


def test_visto_no_se_degrada_con_una_lectura_posterior_mala():
    """VISTO es absorbente dentro de la corrida. Es la misma regla que el desmontaje —el scroll
    nunca borra lo ya capturado—: la evidencia de haber visto algo no se pierde porque un frame
    posterior salga borroso."""
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.observe(MenuSighting("Ellen", "Ellen", 0.20, "Ellen", 0.30, "ok"), ts=2.0)
    assert [r.clave for r in c.vistos] == ["Ellen"]
    assert c.dudosos == []


# --- PJ nuevo: la parte que exige MÁS evidencia -------------------------------------------

def test_un_texto_desconocido_una_sola_vez_no_alcanza_para_declarar_pj_nuevo():
    c = _censo()
    d = c.observe(MenuSighting(None, "Zzzarel", 0.93, None, 0.10, "sin_match"), ts=1.0)
    assert d.estado == "dudoso"
    assert c.nuevos == [], "una sola lectura no declara un PJ nuevo"
    assert {r.clave for r in c.dudosos} == {"zzzarel"}


def test_dos_lecturas_concordantes_si_declaran_pj_nuevo():
    c = _censo()
    c.observe(MenuSighting(None, "Zzzarel", 0.93, None, 0.10, "sin_match"), ts=1.0)
    c.observe(MenuSighting(None, "Zzzarel", 0.95, None, 0.10, "sin_match"), ts=2.0)
    nuevos = c.nuevos
    assert [r.clave for r in nuevos] == ["zzzarel"]
    assert nuevos[0].en_db is False
    assert nuevos[0].texto_crudo == "Zzzarel"


def test_un_pj_nuevo_no_cuenta_como_cobertura_del_roster():
    """El denominador es el roster de la DB. Un PJ que la DB no tiene no puede tapar el hueco
    de uno que sí tiene y no se vio."""
    c = _censo()
    for ts in (1.0, 2.0):
        c.observe(MenuSighting(None, "Zzzarel", 0.95, None, 0.10, "sin_match"), ts=ts)
    r = c.resumen()
    assert r["vistos"] == 0 and r["nuevos"] == 1
    assert len(c.pendientes) == 4


# --- PJs GRISES: el menú muestra los que no poseés, mezclados con los tuyos -----------------

def test_un_pj_que_existe_pero_no_poseo_no_es_un_pj_nuevo():
    """El menú de personajes lista en GRIS a los que no tenés, junto a los tuyos. Leerlos es
    inevitable durante el recorrido. Sin esta distinción, cada uno dispararía el onboarding de un
    personaje que el jugador no posee — el mismo daño que un PJ nuevo inventado, pero garantizado
    en cada pasada."""
    c = _censo()
    d = c.observe(MenuSighting(None, "Hugo", 0.96, None, 0.12, "sin_match"), ts=1.0)
    assert d.estado == "no_poseido"
    assert c.nuevos == [], "existe en el juego y no está en la DB porque NO lo tenés: es correcto"
    assert [r.clave for r in c.no_poseidos] == ["Hugo"]


def test_un_pj_no_poseido_no_cuenta_como_cobertura_ni_como_dudoso():
    c = _censo()
    for ts in (1.0, 2.0, 3.0):
        c.observe(MenuSighting(None, "Hugo", 0.96, None, 0.12, "sin_match"), ts=ts)
    r = c.resumen()
    assert r["vistos"] == 0 and r["nuevos"] == 0 and r["dudosos"] == 0
    assert r["no_poseidos"] == 1
    assert len(c.pendientes) == 4, "no poseerlo no tapa el hueco de ninguno de los tuyos"


def test_verlo_muchas_veces_no_promueve_un_no_poseido_a_pj_nuevo():
    """`_OBS_MIN_NUEVO` no alcanza como salvaguarda acá: scrollear el menú pasa por los grises
    tantas veces como quieras."""
    c = _censo()
    for ts in range(1, 8):
        c.observe(MenuSighting(None, "Hugo", 0.99, None, 0.12, "sin_match"), ts=float(ts))
    assert c.nuevos == []
    assert c.no_poseidos[0].n_obs == 7


def test_un_desconocido_que_no_esta_en_el_catalogo_sigue_siendo_candidato_a_pj_nuevo():
    """El catálogo de arte va por delante de la posesión, pero no es infalible: un personaje
    recién salido puede no tener arte todavía. Ese caso sigue reportándose, y el reporte tiene
    que decir que hay DOS lecturas posibles (PJ nuevo o uno que no poseés)."""
    c = _censo()
    for ts in (1.0, 2.0):
        c.observe(MenuSighting(None, "Zzzarel", 0.95, None, 0.10, "sin_match"), ts=ts)
    assert [r.clave for r in c.nuevos] == ["zzzarel"]
    assert c.no_poseidos == []


def test_un_gris_no_se_disfraza_de_pj_propio_por_parecido_de_nombre():
    """Medido: `Lichter` (que no se posee) da **0.667** de similitud contra `Alice`, por encima
    del umbral de identificación (0.55). Sin esta precedencia, el match difuso lo intercepta
    antes del catálogo y le carga ruido a un PJ que sí tenés.

    Un match EXACTO contra la lista de los que existen es evidencia mucho más fuerte que un
    parecido de 0.667, así que gana."""
    c = _censo(roster=[(1, "Alice")], catalogo={"Alice", "Lichter"})
    d = c.observe(MenuSighting("Alice", "Lichter", 0.96, "Alice", 0.667, "ok"), ts=1.0)
    assert d.clave == "Lichter" and d.estado == "no_poseido"
    assert c.vistos == [] and c.dudosos == []
    assert [r.clave for r in c.pendientes] == ["Alice"], "Alice sigue sin verse"


def test_el_catalogo_incluye_a_los_propios_y_el_censo_deriva_los_grises():
    """El llamador pasa `avatar_refs/` entero —los que EXISTEN—; los grises los deriva el censo
    restándole el roster. Si el llamador tuviera que pasar la diferencia ya hecha, cualquier
    error suyo mandaría a un PJ propio a `no_poseido`."""
    c = _censo(roster=[(1, "Ellen")], catalogo={"Ellen", "Hugo"})
    c.observe(MenuSighting("Ellen", "Ellen", 0.97, "Ellen", 0.99, "ok"), ts=1.0)
    assert [r.clave for r in c.vistos] == ["Ellen"]
    assert c.no_poseidos == []


def test_el_catalogo_se_compara_normalizado():
    """El OCR no respeta acentos ni mayúsculas; el catálogo sale de nombres de archivo."""
    c = _censo(catalogo={"Lichter"})
    c.observe(MenuSighting(None, "  lichter ", 0.95, None, 0.11, "sin_match"), ts=1.0)
    assert [r.clave for r in c.no_poseidos] == ["Lichter"]


def test_un_casi_acierto_cae_sobre_el_candidato_y_nunca_es_pj_nuevo():
    """`Astre Yoo` es Astra Yao mal leída, no un personaje nuevo. Confundirlos dispara el
    onboarding de alguien que no existe — por eso hay un piso de similitud por debajo del cual
    recién se considera 'desconocido'."""
    c = _censo()
    d = c.observe(MenuSighting(None, "Astre Yoo", 0.88, "Astra Yao", 0.71, "sin_match"), ts=1.0)
    assert d.clave == "Astra Yao" and d.estado == "dudoso"
    assert c.nuevos == []
    assert {r.clave for r in c.dudosos} == {"Astra Yao"}


def test_un_casi_acierto_sobre_un_GRIS_no_se_cuenta_como_PJ_tuyo():
    """Desde el veto de la declaración, el candidato del matcher puede ser alguien que NO poseés
    — antes siempre salía del roster. `Lichten` es Lichter mal leída: el texto crudo ya no cae en
    la lista de grises, así que llega por la rama del candidato, y esa rama daba `en_db=True` a
    mano. Sin este arreglo un personaje ajeno entraría al censo como uno tuyo pendiente de ver."""
    c = _censo()
    d = c.observe(MenuSighting(None, "Lichten", 0.9, "Lichter", 0.86, "sin_match"), ts=1.0)
    assert d.clave == "Lichter"
    assert d.estado == "no_poseido", "es un gris, no un PJ propio con lectura dudosa"
    assert c.dudosos == [] and c.nuevos == []


# --- frames que no aportan ------------------------------------------------------------------

@pytest.mark.parametrize("motivo", ["sin_roi", "ocr_error", "ocr_vacio"])
def test_un_frame_ilegible_no_cambia_nada_y_avisa_una_sola_vez(motivo):
    c = _censo()
    d1 = c.observe(MenuSighting(None, None, None, None, None, motivo), ts=1.0)
    d2 = c.observe(MenuSighting(None, None, None, None, None, motivo), ts=2.0)
    assert len(c.pendientes) == 4 and c.vistos == [] and c.dudosos == []
    assert d1.logs and not d2.logs, "el aviso de ilegible va por flanco, no por frame"


def test_observar_sobre_una_corrida_cerrada_es_no_op():
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.cerrar(ts=2.0)
    d = c.observe(_ok("Nicole"), ts=3.0)
    assert d.estado is None and d.logs == []
    assert [r.clave for r in c.vistos] == ["Ellen"]


# --- cierre: la única transición que fabrica huérfanos --------------------------------------

def test_cerrar_convierte_pendientes_en_huerfanos_y_respeta_los_dudosos():
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.observe(MenuSighting("Nicole", "Nicole", 0.40, "Nicole", 0.95, "ok"), ts=2.0)
    c.cerrar(ts=3.0)
    assert {r.clave for r in c.huerfanos} == {"Astra Yao", "Aria"}
    assert {r.clave for r in c.dudosos} == {"Nicole"}, \
        "un dudoso no es huérfano: se vio, solo que mal"
    assert c.pendientes == []


def test_cerrar_dos_veces_devuelve_none_la_segunda():
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    assert c.cerrar(ts=2.0) is not None
    assert c.cerrar(ts=3.0) is None


def test_abandonar_una_corrida_no_produce_huerfanos():
    """Vencimiento no es cierre. Una pasada que se abandonó a la mitad no prueba nada sobre lo
    que no se vio — declararlo huérfano sería exactamente la foto parcial con cara de completa."""
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.drop("expirada")
    assert c.huerfanos == []
    assert c.cerrar(ts=2.0) is None


def test_el_registro_de_cierre_declara_si_la_pasada_fue_completa():
    c = _censo()
    for n in ("Ellen", "Astra Yao", "Nicole", "Aria"):
        c.observe(_ok(n), ts=1.0)
    reg = c.cerrar(ts=2.0)
    assert reg["completo"] is True
    assert reg["resumen"]["cobertura"] == pytest.approx(1.0)
    assert reg["huerfanos"] == []


def test_la_cobertura_se_mide_contra_el_roster_de_la_db():
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.observe(_ok("Nicole"), ts=2.0)
    assert c.resumen()["cobertura"] == pytest.approx(0.5)
    assert c.progreso == (2, 4)

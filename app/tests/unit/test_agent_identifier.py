"""
Tests del matcher de avatar (Etapa 2) — `AgentIdentifier`.

Valida el bootstrap: aprender el avatar de un PJ desde S18 (donde el nombre viene
por OCR) y reconocerlo luego en S8 (donde no hay nombre). Usa capturas reales de
Nangong Yu (misma en S18 y S8) y otras como negativos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.agent_identifier import AgentIdentifier  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
NANGONG_S18 = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_1.png"
NANGONG_S8 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_1.png"
OTRO_S18 = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_2.png"
OTRO_S8 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_3.png"


def _read(path: Path):
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _ident(tmp_path) -> AgentIdentifier:
    return AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)


def test_identify_vacio_devuelve_none(tmp_path):
    ident = _ident(tmp_path)
    frame = _read(NANGONG_S8)
    if frame is None:
        pytest.skip("captura no disponible")
    assert ident.identify(frame) is None


def test_bootstrap_s18_identifica_en_s8(tmp_path):
    """Aprende Nangong Yu desde S18 y la reconoce en S8 (sin nombre en pantalla)."""
    s18, s8 = _read(NANGONG_S18), _read(NANGONG_S8)
    if s18 is None or s8 is None:
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    assert ident.learn(s18, "Nangong Yu") is True
    res = ident.identify(s8)
    assert res is not None, "no reconoció a Nangong Yu en S8 tras aprenderla en S18"
    name, corr = res
    assert name == "Nangong Yu"
    assert corr > 0.88


def test_no_confunde_con_otro_pj(tmp_path):
    """Con solo Nangong Yu en la librería, otro PJ NO debe matchear (umbral)."""
    s18, otro = _read(NANGONG_S18), _read(OTRO_S8)
    if s18 is None or otro is None:
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    ident.learn(s18, "Nangong Yu")
    res = ident.identify(otro)
    # O bien None, o bien NO la nombra Nangong con alta confianza
    assert res is None or res[0] != "Nangong Yu" or res[1] < 0.88


def test_discrimina_entre_dos_pj(tmp_path):
    """Con dos PJs aprendidos, cada uno se reconoce como sí mismo."""
    s18a, s8a = _read(NANGONG_S18), _read(NANGONG_S8)
    otro18 = _read(OTRO_S18)
    if any(f is None for f in (s18a, s8a, otro18)):
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    ident.learn(s18a, "Nangong Yu")
    ident.learn(otro18, "PJ_Otro")
    res = ident.identify(s8a)
    assert res is not None and res[0] == "Nangong Yu"


# ---- Semilla -ico: tapa huecos, no compite ni se duplica ---------------------------------
#
# Regresión 2026-07-31. `_seed_ico` sembraba SIEMPRE y ANTES de cargar el .npz; como el .npz ya
# tenía una copia guardada de la semilla, cada ciclo seed → load → save sumaba otra (ni el seed
# ni `load_merge` aplican `_MAX_REFS_PER_NAME`). El grid terminó con 2 refs IDÉNTICAS por clase y
# CERO cosechadas: el arte -ico es de otro dominio, así que nombraba mal con confianza 0.85 —
# 4.3% top-1 sobre badges reales, con Cissia llevándose 14 discos ajenos.

def _grid_ident(tmp_path, refs_previas=None):
    """AgentIdentifier real (con autoload) sobre una librería de grid controlada."""
    from app.core.avatar_descriptor import AvatarMatcher
    base = tmp_path / "lib.npz"
    if refs_previas:
        m = AvatarMatcher()
        for name, img in refs_previas:
            m.add_reference(name, img)
        m.save(base.with_name("avatar_badge_v2.npz"))
    return AgentIdentifier(library_path=base, autoload=True, prune=False)


def _ico(name="Ellen.png"):
    return cv2.imread(str(REPO / "app" / "resources" / "avatar_refs" / name))


def test_la_semilla_ico_no_pisa_a_un_pj_con_cosecha(tmp_path):
    """Un PJ con refs del dominio REAL no recibe la semilla: el -ico es arte de comunidad y solo
    agrega una ref de otro dominio a competir dentro de su propia clase."""
    cosechada = _ico("Ellen.png")
    if cosechada is None:
        pytest.skip("assets no disponibles")
    ident = _grid_ident(tmp_path, refs_previas=[("Ellen", cosechada)])
    assert len(ident._badge._refs["Ellen"]) == 1, "se le sumó la semilla encima de la cosecha"


def test_la_semilla_ico_si_tapa_un_pj_sin_refs(tmp_path):
    """Su función declarada sigue viva: cobertura día-1 de los PJs que no se poseen."""
    ident = _grid_ident(tmp_path)
    sembrados = [k for k, v in ident._badge._refs.items() if v]
    assert sembrados, "sin librería, la semilla tiene que dar algo"
    assert "Ellen" in ident._badge._refs


def test_dos_cargas_seguidas_no_duplican_la_semilla(tmp_path):
    """El bucle que vació el grid: cargar → guardar → volver a cargar no puede crecer."""
    a = _grid_ident(tmp_path)
    n_a = len(a._badge._refs["Ellen"])
    a.save_s17()                                   # persiste la semilla, como hacía la cosecha
    b = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=True, prune=False)
    assert len(b._badge._refs["Ellen"]) == n_a, "la semilla se duplicó al recargar"


def test_identify_face_se_abstiene_bajo_el_guard(tmp_path):
    """QA en vivo 2026-08-01: la página de Remielle Dan —que no tenía refs de fila— dio
    `Vivian conf=0.550`, y dos frames de eso fijaron el latch en Vivian. Los discos eran de
    Remielle, así que el badge tuvo que desautorizar al ancla en los 6 slots.

    Esta ruta devolvía cualquier match que pasara los gates internos del matcher
    (`min_conf=0.45`), la mitad del guard que usa el resto del sistema. El umbral sale medido:
    leave-one-out sobre las refs de fila, la confianza MÍNIMA de un match correcto es 0.928.
    """
    from app.core.avatar_descriptor import AvatarMatcher, MatchResult
    ident = _ident(tmp_path)
    guard = ident.surfaces["row"].guard
    cara = _ico("Ellen.png")
    if cara is None:
        pytest.skip("assets no disponibles")

    ident._row = ident.surfaces["row"].matcher = AvatarMatcher()
    ident._row.match = lambda face: MatchResult(  # type: ignore[assignment]
        name="Vivian", conf=guard - 0.05, margin=0.08, rejected=False, top=[])
    assert ident.identify_face(cara) is None, "un match por debajo del guard no puede nombrar"

    ident._row.match = lambda face: MatchResult(  # type: ignore[assignment]
        name="Vivian", conf=guard + 0.05, margin=0.08, rejected=False, top=[])
    assert ident.identify_face(cara) == ("Vivian", guard + 0.05)


def test_el_baseline_solo_aplica_a_la_libreria_del_runtime(tmp_path, monkeypatch):
    """La red de emergencia es para la ubicación REAL. Apuntar a otro lado —un `library_path`
    explícito, o `DANIBOD_AVATAR_LIB`, que es como el conftest aísla cada test— es deliberado: ahí
    que falte el archivo es información, y volcarle 459 refs del repo rompe el aislamiento (pasó:
    los tests de armas empezaron a ver una librería que se suponía vacía)."""
    from app.core.agent_identifier import _BASELINES
    # con library_path explícito → sin baseline
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)
    assert all(ident.surfaces[s].baseline_path is None for s in ("row", "grid", "detail"))
    # con DANIBOD_AVATAR_LIB (el caso del conftest) → tampoco
    monkeypatch.setenv("DANIBOD_AVATAR_LIB", str(tmp_path / "otra.npz"))
    assert AgentIdentifier(autoload=False).surfaces["grid"].baseline_path is None
    # ruta por defecto → sí, y apuntando al snapshot versionado de audit/
    monkeypatch.delenv("DANIBOD_AVATAR_LIB", raising=False)
    surf = AgentIdentifier(autoload=False).surfaces["grid"]
    assert surf.baseline_path == _BASELINES["grid"]


def test_los_baselines_versionados_existen():
    """Un baseline que apunta a un archivo inexistente es una red de emergencia imaginaria: no
    falla al declararla, falla el día que hace falta."""
    from app.core.agent_identifier import _BASELINES
    faltan = [k for k, p in _BASELINES.items() if not p.exists()]
    assert not faltan, f"baselines declarados pero ausentes de audit/: {faltan}"


def test_los_nombres_ico_quedan_protegidos_de_la_poda(tmp_path):
    """`prune_to_roster` usa `_ico_names` para no borrar a los PJs no obtenidos. Ese set tiene
    que poblarse con TODOS los stems, tenga o no la clase refs sembradas."""
    cosechada = _ico("Ellen.png")
    if cosechada is None:
        pytest.skip("assets no disponibles")
    ident = _grid_ident(tmp_path, refs_previas=[("Ellen", cosechada)])
    assert "Ellen" in ident._ico_names


def test_el_mismo_recorte_se_reconoce_como_clon(tmp_path):
    """QA en vivo 2026-08-11: Lycaon terminó con dos refs a distancia 0.000 entre sí.

    El dedup de la cosecha es por (PJ, arma) y POR SESIÓN, así que una sesión nueva vuelve a
    cosechar la misma arma del mismo PJ. Un clon no agrega discriminación y encima gasta una de
    las 10 ranuras — y cuando se llenan, el desalojo FIFO empieza a tirar las refs DIVERSAS.
    Por eso se dedupea por CONTENIDO: también atrapa la misma cara vista desde otra pantalla.
    """
    cara = _ico("Ellen.png")
    if cara is None:
        pytest.skip("assets no disponibles")
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)
    assert ident.detail_is_near_duplicate(cara, "Ellen") is False, "sin refs no hay clon posible"
    ident.learn_s17_detail(cara, "Ellen")
    assert ident.detail_is_near_duplicate(cara, "Ellen") is True


def test_una_cara_distinta_no_es_clon(tmp_path):
    """El contracaso: el umbral tiene que dejar entrar variación real. Medido sobre la librería
    del runtime, dos refs genuinas del mismo PJ están a 0.098-0.229; un clon, a 0.000."""
    a, b = _ico("Ellen.png"), _ico("Lycaon.png")
    if a is None or b is None:
        pytest.skip("assets no disponibles")
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)
    ident.learn_s17_detail(a, "Ellen")
    assert ident.detail_is_near_duplicate(b, "Ellen") is False


def test_persistencia_round_trip(tmp_path):
    """Aprender + guardar + recargar en otra instancia → sigue reconociendo."""
    s18, s8 = _read(NANGONG_S18), _read(NANGONG_S8)
    if s18 is None or s8 is None:
        pytest.skip("capturas no disponibles")
    path = tmp_path / "lib.npz"
    a = AgentIdentifier(library_path=path, autoload=False)
    a.learn(s18, "Nangong Yu")
    assert a._row_path.exists()      # Fase 5R: la lib de fila se guarda en avatar_row_v2.npz
    b = AgentIdentifier(library_path=path, autoload=True)
    assert "Nangong Yu" in b.names
    res = b.identify(s8)
    assert res is not None and res[0] == "Nangong Yu"

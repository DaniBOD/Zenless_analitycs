"""El motor de discos tiene que decidir como Daniel. Sus casos son la vara (human first, 2026-09-22).

**Por qué existe.** El motor de scoring se escribió en el Hito 2.2 y nunca se midió contra el
criterio de nadie: todo lo que lo alimenta es default (umbral 0,75/0,50 igual para los 52 PJs,
pesos de arquetipo para 42). El 2026-09-22 Daniel contestó 8 casos —"¿cuál le equipás?", "¿qué
hacés con este disco nuevo?"— con su razonamiento, y de ahí salieron 17 reglas (registro completo
en `Dev_IA/documentacion_cruda/2026-09/2026-09-22_SPEC_Criterio_de_equipamiento_casos_human_first.md`).
Cada caso de `fixtures/criterio_equipar/casos.json` es un test: el motor se juzga por **cuántas
decisiones de Daniel reproduce**, que es la métrica aterrizada que no teníamos.

**Cómo leer los xfail.** Los casos que el motor todavía NO reproduce están marcados `xfail`
ESTRICTO, cada uno con la razón medida. Estricto es a propósito, en las dos direcciones:
  - si un cambio rompe un caso que andaba, el test se pone rojo;
  - si un cambio arregla un caso marcado, el xfail pasa a XPASS y **también** se pone rojo — hay
    que sacar la marca y anotar la mejora. Una mejora que nadie registra no se puede defender, y
    una marca que quedó vieja esconde la siguiente regresión.

**El motivo, no sólo el resultado.** Un caso puede acertar la decisión por la razón equivocada
(el motor actual descarta D3 porque descarta TODO disco en Nivel 0, con el mismo puntaje que D1).
Donde eso pasa, el caso trae un `motivo` que también se exige.

**El estado del PJ viaja adentro del caso** (sus stats, su build): el test no lee la DB de
dominio, así que no cambia cuando cambia la cuenta.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.recommender import recomendar
from app.core.score_normalizer import ScoringContext
from app.core.scoring import score_disco
from app.db.repositories import Agent, Archetype, Disc, DiscSetArchetype

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "criterio_equipar" / "casos.json"
DATOS = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASOS = DATOS["casos"]

# ---------------------------------------------------------------------------
# Lo que el motor ACTUAL todavía no reproduce. Medido el 2026-09-22 con este mismo test.
# Cada paso de la etapa 1 que arregle uno tiene que sacarlo de acá (el xfail es estricto).
# ---------------------------------------------------------------------------
NO_REPRODUCE_TODAVIA: dict[str, str] = {
    "caso3": "empate exacto: el motor pesa CR y DC igual, no sabe que Ellen ya tiene DC de sobra "
             "(falta el balance del crítico con los stats del PJ)",
    "caso4": "rompe el 4pc: recomendar() no conoce el 4pc del PJ (sólo el arquetipo del set, 0,7) "
             "y castiga la línea de PV del actual",
    "caso6_D1": "descarta un Nivel 0 bueno: lo normaliza contra el máximo de un +15, no evalúa "
                "potencial",
    "caso6_D3": "acierta 'descartar' por la razón equivocada: mismo puntaje que D1, no ve que el "
                "principal PV % no le sirve a ningún rol",
}


# ---------------------------------------------------------------------------
# Construcción de objetos de dominio desde el fixture
# ---------------------------------------------------------------------------

def _arquetipos() -> dict[str, Archetype]:
    out = {}
    for i, (code, a) in enumerate(DATOS["arquetipos"].items(), start=1):
        out[code] = Archetype(
            id=i, code=code,
            substats_positivos=dict(a["positivos"]),
            substats_perjudiciales=dict(a["perjudiciales"]),
            threshold_stock=a["threshold_stock"],
            mains_4=list(a["mains_4"]), mains_5=list(a["mains_5"]), mains_6=list(a["mains_6"]),
        )
    return out


ARQUETIPOS = _arquetipos()


def _disco(d: dict, disc_id: int = 1, slot: int | None = None) -> Disc:
    return Disc(
        id=disc_id, set_id=d["set"], slot=slot if slot is not None else d["slot"],
        main_stat=d["main"], main_valor=None, main_unidad=None,
        subs=[(stat, valor, None, mejoras) for stat, valor, mejoras in d["subs"]],
        nivel=d["nivel"], equipado=0, agente_asignado=None,
    )


def _set_arquetipos(set_id: int) -> list[DiscSetArchetype]:
    return [
        DiscSetArchetype(set_id=set_id, archetype_id=ARQUETIPOS[code].id,
                         archetype_code=code, prioridad=prio)
        for code, prio in DATOS["set_arquetipos"].get(str(set_id), [])
    ]


def _pj(nombre: str, agent_id: int = 100) -> Agent:
    p = DATOS["pjs"][nombre]
    arq = ARQUETIPOS[p["arquetipo"]]
    return Agent(id=agent_id, nombre=nombre, arquetipo_primario_id=arq.id,
                 arquetipo_primario_code=arq.code, threshold_equip=0.75, threshold_upgrade=0.50,
                 substat_preferences=dict(p["pesos"]))


# Los tres repos que pide `recomendar()`, servidos desde el fixture en vez de la DB.

class _AgentRepo:
    def __init__(self, agentes: list[Agent]):
        self._agentes = agentes

    def get_all(self) -> list[Agent]:
        return list(self._agentes)


class _ArchRepo:
    def get_all(self) -> list[Archetype]:
        return list(ARQUETIPOS.values())

    def get_by_id(self, arch_id: int) -> Archetype | None:
        return next((a for a in ARQUETIPOS.values() if a.id == arch_id), None)


class _SetRepo:
    def get_archetypes_for_set(self, set_id: int) -> list[DiscSetArchetype]:
        return _set_arquetipos(set_id)


def _roster() -> list[Agent]:
    r = DATOS["roster_generico"]
    agentes = [
        Agent(id=10 + i, nombre=f"generico_{code}", arquetipo_primario_id=ARQUETIPOS[code].id,
              arquetipo_primario_code=code, threshold_equip=0.75, threshold_upgrade=0.50,
              substat_preferences={})
        for i, code in enumerate(r["arquetipos"])
    ]
    agentes += [_pj(n, agent_id=100 + i) for i, n in enumerate(r["incluye_pjs"])]
    return agentes


# ---------------------------------------------------------------------------
# Adaptador del MOTOR. Hoy: el motor de pesos del Hito 2.2, leído de la forma más favorable.
# Los pasos siguientes de la etapa 1 cambian lo que hay DETRÁS de estas tres funciones, no el
# contrato de los casos.
# ---------------------------------------------------------------------------

CTX = ScoringContext()


def _puntaje(d: dict, pj: str, slot: int) -> float:
    """Igual que `recomendar()`: sin el 4pc/2pc del PJ, el set sólo cuenta por su arquetipo."""
    agente = _pj(pj)
    disco = _disco(d, slot=slot)
    return score_disco(disco, agente, ARQUETIPOS[agente.arquetipo_primario_code], CTX,
                       disc_set_archetypes=_set_arquetipos(disco.set_id)).score_norm


def decidir_comparacion(caso: dict) -> str:
    """El motor actual no compara: puntúa cada disco solo. Se le concede el orden de sus
    puntajes como 'su' elección. Empate exacto = no eligió."""
    puntos = {k: _puntaje(d, caso["pj"], caso["slot"]) for k, d in caso["opciones"].items()}
    orden = sorted(puntos.items(), key=lambda kv: kv[1], reverse=True)
    if len(orden) > 1 and orden[0][1] == orden[1][1]:
        return "empate"
    return orden[0][0]


def decidir_cambio(caso: dict) -> str:
    actual = _puntaje(caso["actual"], caso["pj"], caso["slot"])
    nuevo = _puntaje(caso["nuevo"], caso["pj"], caso["slot"])
    return "cambiar" if nuevo > actual else "mantener"


def decidir_disco_nuevo(caso: dict) -> tuple[str, float]:
    """`recomendar()` real, contra un roster servido desde el fixture."""
    rec = recomendar(_disco(caso["disco"]), _AgentRepo(_roster()), _ArchRepo(), _SetRepo(), CTX)
    return rec.tipo, rec.score_norm


# ---------------------------------------------------------------------------
# Los casos
# ---------------------------------------------------------------------------

def _decidir(caso: dict) -> str:
    if caso["tipo"] == "comparar":
        return decidir_comparacion(caso)
    if caso["tipo"] == "cambiar":
        return decidir_cambio(caso)
    if caso["tipo"] == "disco_nuevo":
        return decidir_disco_nuevo(caso)[0]
    raise AssertionError(f"tipo de caso desconocido: {caso['tipo']}")


def _por_id(caso_id: str) -> dict:
    return next(c for c in CASOS if c["id"] == caso_id)


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_el_motor_decide_como_daniel(caso, request):
    if caso["id"] in NO_REPRODUCE_TODAVIA:
        request.applymarker(pytest.mark.xfail(strict=True,
                                              reason=NO_REPRODUCE_TODAVIA[caso["id"]]))
    decision = _decidir(caso)
    assert decision == caso["decision"], (
        f"{caso['id']}: el motor dice {decision!r}, Daniel dijo {caso['decision']!r} — "
        f"{caso['razon']}")

    motivo = caso.get("motivo") or {}
    if "puntaje_menor_que" in motivo:
        otro = _por_id(motivo["puntaje_menor_que"])
        propio, ajeno = decidir_disco_nuevo(caso)[1], decidir_disco_nuevo(otro)[1]
        assert propio < ajeno, (
            f"{caso['id']}: acierta la decisión pero no el motivo — puntúa {propio:.3f}, "
            f"no menos que {otro['id']} ({ajeno:.3f})")


def test_el_fixture_no_se_quedo_sin_casos():
    """Si alguien vacía o renombra el fixture, el test parametrizado pasaría sin correr nada."""
    assert len(CASOS) >= 11
    assert {c["tipo"] for c in CASOS} == {"comparar", "cambiar", "disco_nuevo"}


def test_las_marcas_apuntan_a_casos_que_existen():
    """Una marca con un id mal escrito no marca nada y nadie se entera."""
    ids = {c["id"] for c in CASOS}
    assert set(NO_REPRODUCE_TODAVIA) <= ids, set(NO_REPRODUCE_TODAVIA) - ids

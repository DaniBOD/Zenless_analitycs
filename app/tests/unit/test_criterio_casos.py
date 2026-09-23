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

from app.core.recommender import evaluar_cambio, recomendar
from app.core.score_normalizer import ScoringContext
from app.core.stats_vocab import VALOR_POR_MEJORA
from app.db.repositories import (Agent, Archetype, Disc, DiscSetArchetype,
                                 aplicar_ajustes_arquetipo)

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
    "caso6_D1": "descarta un Nivel 0 bueno: lo normaliza contra el máximo de un +15, no evalúa "
                "potencial",
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


# Los ajustes de Daniel encima de los defaults, con la MISMA función que usa el repositorio.
ARQUETIPOS = {
    code: aplicar_ajustes_arquetipo(arch, DATOS["ajustes_usuario"]["arquetipos"].get(code, {}))
    for code, arch in _arquetipos().items()
}


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
# Adaptador del MOTOR. Desde el paso 3 las comparaciones pasan por `evaluar_cambio()` (el disco
# contra el que el PJ ya tiene, con el set medido en el build); los discos nuevos siguen por
# `recomendar()`. Los pasos siguientes cambian lo que hay DETRÁS de estas tres funciones, no el
# contrato de los casos.
# ---------------------------------------------------------------------------

CTX = ScoringContext()


def _bono_2pc(set_id: int) -> tuple[str, float] | None:
    b = DATOS["sets_2pc"].get(str(set_id))
    return None if b is None or b["stat"] not in VALOR_POR_MEJORA else (b["stat"], b["valor"])


def _build(caso: dict, en_el_slot: dict) -> dict[int, Disc]:
    """El build que declara el caso ("4pc": set, "2pc": set), con `en_el_slot` en su slot. Los
    demás slots llevan discos SIN líneas: sólo aportan su set, que es lo que el caso declara."""
    slot = caso["slot"]
    build = {slot: _disco(en_el_slot, disc_id=slot, slot=slot)}
    piezas = [(caso["build"].get("4pc"), 4), (caso["build"].get("2pc"), 2)]
    libres = [s for s in range(1, 7) if s != slot]
    for set_id, cuantas in piezas:
        if set_id is None:
            continue
        faltan = cuantas - (1 if en_el_slot["set"] == set_id else 0)
        for s in libres[:faltan]:
            build[s] = _disco({"set": set_id, "main": None, "nivel": 15, "subs": []}, disc_id=s, slot=s)
        libres = libres[faltan:]
    for s in libres:
        # Un set distinto por slot (negativo, no existe): relleno que no arma ningún 2pc de mentira.
        build[s] = _disco({"set": -s, "main": None, "nivel": 15, "subs": []}, disc_id=s, slot=s)
    return build


def _cambio(caso: dict, actual: dict, nuevo: dict):
    agente = _pj(caso["pj"])
    return evaluar_cambio(agente, ARQUETIPOS[agente.arquetipo_primario_code], _build(caso, actual),
                          _disco(nuevo, disc_id=99, slot=caso["slot"]), CTX, _bono_2pc)


def decidir_comparacion(caso: dict) -> str:
    """Dos opciones para el mismo slot del mismo build: la segunda contra la primera."""
    (k1, d1), (k2, d2) = caso["opciones"].items()
    delta = _cambio(caso, d1, d2).delta
    if delta == 0:
        return "empate"
    return k2 if delta > 0 else k1


def decidir_cambio(caso: dict) -> str:
    return "cambiar" if _cambio(caso, caso["actual"], caso["nuevo"]).delta > 0 else "mantener"


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

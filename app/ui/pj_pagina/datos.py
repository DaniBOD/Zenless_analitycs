"""Lo que lee la página del PJ (SPEC 2026-09-28) — sin Qt.

Todo desde las fuentes que ya existen, sin una segunda definición (B1):

- lo de HOY en el juego: `pj_modal.datos.ficha_pj` (stats, hexágono, arma, despertar);
- la build DECLARADA y los avisos: `ficha_pj.foto` (lo que usa el motor);
- los fijos con su origen, los renglones del 2pc y los principales válidos: las lecturas de
  `app.core.ficha_pj` hechas para esta página.

Si la build declarada no se puede leer, la página se arma igual con lo de hoy y lo dice: el error
va al log con su traceback (A2: que no se confunda con "no declaraste nada").
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field

from app.core.asset_resolver import set_logo_path
from app.core.ficha_pj import (
    FijoFicha,
    FotoFicha,
    Renglon2pc,
    fijos_de_la_ficha,
    foto,
    renglones_2pc,
)
from app.db.repositories import AgentRepo
from app.ui.pj_modal.datos import FichaPJ, ficha_pj

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetInfo:
    id: int
    nombre: str
    logo: str | None


@dataclass(frozen=True)
class FichaPagina:
    hoy: FichaPJ
    #: None = no se pudo leer la build declarada (se logueó).
    foto: FotoFicha | None
    fijos: tuple[FijoFicha, ...] = ()
    #: 4pc → sus renglones de 2pc en el orden de la guía.
    renglones: dict[int, list[Renglon2pc]] = field(default_factory=dict)
    #: Los sets del juego, para nombres y logos.
    sets: dict[int, SetInfo] = field(default_factory=dict)

    @property
    def elemento(self) -> str | None:
        return self.hoy.elemento


def pagina_pj(con: sqlite3.Connection, agente_id: int) -> FichaPagina | None:
    """`None` si el PJ no existe. Espera `row_factory = sqlite3.Row`."""
    hoy = ficha_pj(con, agente_id)
    if hoy is None:
        return None
    declarada: FotoFicha | None = None
    fijos: tuple[FijoFicha, ...] = ()
    try:
        declarada = foto(con, agente_id)
        fijos = tuple(fijos_de_la_ficha(con, AgentRepo(con).get_by_id(agente_id)))
    except Exception:
        log.exception("[pj_pagina] no se pudo leer la build declarada del PJ %s", agente_id)
        declarada, fijos = None, ()
    sets = {}
    for sid, nombre, nombre_en in con.execute("SELECT id, nombre, nombre_en FROM disc_sets ORDER BY nombre"):
        logo = set_logo_path(nombre_en)
        sets[sid] = SetInfo(sid, nombre, str(logo) if logo else None)
    return FichaPagina(hoy=hoy, foto=declarada, fijos=fijos, renglones=renglones_2pc(con, agente_id),
                       sets=sets)


#: Debajo de qué bloque va cada tipo de aviso de `coherencia.avisos`. Un tipo que no esté acá va a
#: "otros", arriba de todo: un aviso nuevo nunca se pierde.
BLOQUE_DE_AVISO = {
    "set_fuera_de_guia": "sets", "4pc_no_se_activa": "sets", "4pc_a_medias": "sets",
    "principal_fuera_de_guia": "principales",
    "substat_no_te_beneficia": "secundarios", "imprescindible_descartado": "secundarios",
    "condicion_como_fijo": "fijos", "fijo_se_busca": "fijos",
}
BLOQUES = ("otros", "sets", "principales", "secundarios", "fijos")


def avisos_por_bloque(avisos) -> dict[str, list]:
    out: dict[str, list] = {b: [] for b in BLOQUES}
    for a in avisos or ():
        out[BLOQUE_DE_AVISO.get(a.tipo, "otros")].append(a)
    return out

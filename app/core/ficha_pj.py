"""La ficha del PJ: leer lo que dice la guía y lo que eligió el usuario (SPEC 2026-09-27) — sin Qt.

La pantalla (brief `BRIEF_ficha_sets_y_stats.md`) pinta lo que arma este módulo y guarda por él;
el motor no pasa por acá: lee la mezcla en `AgentRepo` (`app.db.repositories`).
"""
from __future__ import annotations

import json
import sqlite3

from app.core.coherencia import EleccionPJ, GuiaPJ
from app.db.repositories import CondicionSet, _tabla_existe, principales_de_la_guia


def leer_guia_pj(con: sqlite3.Connection, agente_id: int) -> GuiaPJ:
    """La guía del PJ (mig 43), con la PRIMERA variante como el motor (`pesos_de_la_guia`)."""
    if not _tabla_existe(con, "pj_stats_recomendados"):
        return GuiaPJ()
    niveles: dict[str, int] = {}
    primera = None
    for variante, nivel, stat in con.execute(
            "SELECT variante, nivel, stat FROM pj_stats_recomendados "
            "WHERE agente_id = ? AND linea = 'substat' ORDER BY rowid", (agente_id,)):
        primera = primera or variante
        if variante == primera:
            niveles[stat] = nivel
    principales = principales_de_la_guia(con.execute(
        "SELECT agente_id, variante, linea, stat FROM pj_stats_recomendados "
        "WHERE agente_id = ? AND linea LIKE 'principal_%' ORDER BY rowid", (agente_id,))).get(agente_id, {})
    sets_4pc = tuple(r[0] for r in con.execute(
        "SELECT set_id FROM pj_sets_4pc WHERE agente_id = ? ORDER BY orden", (agente_id,)))
    dos: dict[int, set[int]] = {}
    for s4, s2 in con.execute("SELECT set_4p_id, set_id FROM pj_sets_2pc WHERE agente_id = ?", (agente_id,)):
        dos.setdefault(s4, set()).add(s2)
    return GuiaPJ(niveles=niveles, principales=principales, sets_4pc=sets_4pc, dos_por_4pc=dos)


def leer_eleccion_pj(con: sqlite3.Connection, agente_id: int) -> EleccionPJ:
    """Sólo lo que el usuario tocó (mig 43 y 46): sin filas, una elección vacía."""
    e = EleccionPJ()
    if _tabla_existe(con, "ajustes_usuario_substats"):
        e.niveles = {s: n for s, n in con.execute(
            "SELECT substat, nivel FROM ajustes_usuario_substats WHERE agente_id = ?", (agente_id,))}
    if _tabla_existe(con, "ajustes_usuario_principales"):
        e.principales = {slot: tuple(sorted(json.loads(v))) for slot, v in con.execute(
            "SELECT slot, valor_json FROM ajustes_usuario_principales WHERE agente_id = ?", (agente_id,))}
    if _tabla_existe(con, "ajustes_usuario_build"):
        fila = con.execute("SELECT set_4p_id, set_2p_id FROM ajustes_usuario_build WHERE agente_id = ?",
                           (agente_id,)).fetchone()
        if fila:
            e.set_4p_id, e.set_2p_id = fila[0], fila[1]
    return e


def leer_condiciones(con: sqlite3.Connection) -> list[CondicionSet]:
    if not _tabla_existe(con, "set_condiciones_4pc"):
        return []
    return [CondicionSet(*r) for r in con.execute(
        "SELECT set_id, tipo, stat, umbral, rol, elemento, alcance, texto FROM set_condiciones_4pc")]


def avisos_de(con: sqlite3.Connection, agent) -> list:
    """Los avisos del asesor para un PJ ya cargado por `AgentRepo` (la mezcla que usa el motor)."""
    from app.core.coherencia import avisos
    sets = {r[0]: r[1] for r in con.execute("SELECT id, nombre FROM disc_sets")}
    return avisos(agent.nombre, leer_guia_pj(con, agent.id), leer_eleccion_pj(con, agent.id),
                  rol=agent.rol, elemento=agent.elemento, set_4p_id=agent.set_4p_id,
                  set_2p_id=agent.set_2p_id, condiciones=leer_condiciones(con),
                  stats=agent.stats, stats_fijos=agent.stats_fijos, sets=sets)

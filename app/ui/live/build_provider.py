"""Nombre de un PJ → los datos que el hexágono dibuja. Sólo lecturas.

Existe para que la card no toque la DB: la vista le pide el build a esto y le pasa a la card un
diccionario ya resuelto.

La autoridad es `inventory_discs` (`InventoryDiscRepo.find_equipped_by_agent`). ⚠️ NO
`AgentDiscRepo`: lee `agent_discs`, que tiene 0 filas, y dibujaría hexágonos vacíos para siempre.

Se consulta en cada lectura y no se cachea el build, a propósito: una lectura de S17 acaba de
persistir, y el hexágono tiene que mostrar la DB DESPUÉS de esa escritura. Es una sola consulta.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)


class BuildProvider:
    def __init__(self, con: sqlite3.Connection):
        from app.db.repositories import AgentRepo, InventoryDiscRepo
        self._con = con
        self._agents = AgentRepo(con)
        self._discos = InventoryDiscRepo(con)
        self._logos: dict[int, str | None] | None = None

    def _logo_de_set(self, set_id: int) -> str | None:
        # El catálogo de sets no cambia durante una sesión: ése sí se cachea.
        if self._logos is None:
            from app.core.asset_resolver import set_logo_path
            self._logos = {}
            try:
                for r in self._con.execute("SELECT id, nombre_en FROM disc_sets"):
                    p = set_logo_path(r[1])
                    self._logos[r[0]] = str(p) if p else None
            except sqlite3.Error as e:
                log.warning("[vivo] sin logos de sets: %s", e)
        return self._logos.get(set_id)

    def build_de(self, nombre_pj: str | None) -> dict[int, dict]:
        """`{slot: {"logo": path|None, "nivel": int}}`. Vacío si el PJ no existe o no tiene discos."""
        if not nombre_pj:
            return {}
        try:
            agente_id = self._agents.get_id_by_nombre(nombre_pj)
            if agente_id is None:
                return {}
            return {
                slot: {"logo": self._logo_de_set(d.set_id), "nivel": d.nivel}
                for slot, d in self._discos.find_equipped_by_agent(agente_id).items()
            }
        except sqlite3.Error:
            log.exception("[vivo] no se pudo leer el build de %s", nombre_pj)
            return {}

"""Nombre de un PJ → los datos que el hexágono dibuja. Sólo lecturas.

Existe para que la card no toque la DB: la vista le pide el build a esto y le pasa a la card un
diccionario ya resuelto.

La autoridad es `inventory_discs` (`InventoryDiscRepo.find_equipped_by_agent`). La tabla
`agent_discs` sigue en el esquema pero tiene 0 filas: no leerla (su repo se borró en `2fd8606`).

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
        self._sets: dict[int, tuple[str | None, str | None]] | None = None

    def _set(self, set_id: int) -> tuple[str | None, str | None]:
        """`(nombre español, ruta del logo)`. El catálogo de sets no cambia durante una sesión:
        ése sí se cachea."""
        if self._sets is None:
            from app.core.asset_resolver import set_logo_path
            self._sets = {}
            try:
                for r in self._con.execute("SELECT id, nombre, nombre_en FROM disc_sets"):
                    p = set_logo_path(r[2])
                    self._sets[r[0]] = (r[1], str(p) if p else None)
            except sqlite3.Error as e:
                log.warning("[vivo] sin logos de sets: %s", e)
        return self._sets.get(set_id, (None, None))

    def build_de(self, nombre_pj: str | None) -> dict[int, dict]:
        """`{slot: {"logo": path|None, "nivel": int, "set": nombre|None}}`. Vacío si el PJ no existe
        o no tiene discos. El nombre del set lo usa el modal de PJ para contar piezas."""
        if not nombre_pj:
            return {}
        try:
            agente_id = self._agents.get_id_by_nombre(nombre_pj)
            if agente_id is None:
                return {}
            salida = {}
            for slot, d in self._discos.find_equipped_by_agent(agente_id).items():
                nombre, logo = self._set(d.set_id)
                salida[slot] = {"logo": logo, "nivel": d.nivel, "set": nombre}
            return salida
        except sqlite3.Error:
            log.exception("[vivo] no se pudo leer el build de %s", nombre_pj)
            return {}

"""Los números del sidebar, leídos de la DB. Separado del widget a propósito: el sidebar muestra
números, no sabe de dónde salen, y así se testea cada mitad por su lado.

Sólo lecturas.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

# clave del sidebar → consulta. Discos y armas NO cuentan las bajas lógicas (`descartado = 1`): el
# tab `Estado` que esto reemplaza contaba las armas sin filtrar y habría dicho 58 con 56 reales.
_CONSULTAS: dict[str, str] = {
    "discos":    "SELECT COUNT(*) FROM inventory_discs WHERE COALESCE(descartado, 0) = 0",
    "roster":    "SELECT COUNT(*) FROM agents",
    "armas":     "SELECT COUNT(*) FROM inventory_weapons WHERE COALESCE(descartado, 0) = 0",
    "historico": "SELECT COUNT(*) FROM inventory_disc_evaluations",
    "equipos":   "SELECT COUNT(*) FROM team_compositions",
    "lategame":  "SELECT COUNT(*) FROM lategame_runs",
}


def leer_contadores(con: sqlite3.Connection) -> dict[str, int]:
    """`{clave: cantidad}`. Una consulta que falla (tabla ausente en una DB vieja) deja ESE
    contador sin valor y no tumba los demás."""
    out: dict[str, int] = {}
    for clave, sql in _CONSULTAS.items():
        try:
            out[clave] = int(con.execute(sql).fetchone()[0])
        except sqlite3.Error as e:
            log.warning("[sidebar] contador %s sin valor: %s", clave, e)
    return out

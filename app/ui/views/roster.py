"""Vista Roster — punto de entrada para la ventana.

Hasta la fase 2 de la interfaz (2026-09-13) era una tabla de 8 columnas. Ahora es la pantalla de la
Parte B del diseño v1, que vive en `app/ui/roster/`. Este módulo queda para que `main.py` no tenga
que conocer ese paquete por dentro.
"""
from __future__ import annotations

import sqlite3

from app.ui.roster.view import RosterView


def build_roster_view(con: sqlite3.Connection | None) -> RosterView:
    """`con` es la conexión de LECTURA de la UI (la misma del hexágono y los contadores)."""
    return RosterView(con)

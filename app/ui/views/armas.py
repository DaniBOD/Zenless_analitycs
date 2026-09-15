"""Vista Armas — punto de entrada para la ventana.

Era un placeholder ("Fase 5 — RF-14 pendiente") hasta el 2026-09-15. Ahora es la pantalla del diseño
`Pestana Armas - W-Engines.html` de Claude Design, en `app/ui/armas/`.
"""
from __future__ import annotations

import sqlite3

from app.ui.armas.view import ArmasView


def build_armas_view(con: sqlite3.Connection | None) -> ArmasView:
    """`con` es la conexión de LECTURA de la UI (la misma del roster y de discos)."""
    return ArmasView(con)

"""Vista Discos — punto de entrada para la ventana.

Hasta la fase 3 de la interfaz (2026-09-13) era una `QTableWidget` con `LIMIT 200`, que mostraba
200 de los 385 discos sin avisar, y una columna Score siempre vacía. Ahora es la pantalla del
mockup `22-tab-discos-inventario-completo.png`, en `app/ui/discos/`.
"""
from __future__ import annotations

import sqlite3

from app.ui.discos.view import DiscosView


def build_discos_view(con: sqlite3.Connection | None) -> DiscosView:
    """`con` es la conexión de LECTURA de la UI (la misma del roster y del hexágono)."""
    return DiscosView(con)

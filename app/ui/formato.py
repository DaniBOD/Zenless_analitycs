"""Cómo se escribe un stat en pantalla — una sola regla para toda la interfaz.

La usan la vista en vivo (vía `MonitorController._fmt_sub`), la tabla de discos y el modal de disco.
Antes de la fase 3 vivía sólo en el controller; si la tabla la copiaba, el mismo disco podía decir
`Daño Crítico 9.6% (+1)` en un lado y `Daño Crítico 9.6 +1` en el otro.
"""
from __future__ import annotations


def formatear_valor(valor, unidad: str | None) -> str:
    """`30%` · `184`. Sin valor, un guion: no un 0."""
    if valor is None:
        return "—"
    return f"{float(valor):g}{'%' if unidad == '%' else ''}"


def formatear_sub(nombre: str | None, valor, unidad: str | None, rolls: int | None) -> str:
    """`ATK 38 (+1)` · `ATK% 3%` · `Daño Crítico 9.6% (+1)`. Los rolls sólo si hay."""
    texto = nombre or "?"
    if valor is not None:
        texto += f" {formatear_valor(valor, unidad)}"
    if rolls:
        texto += f" (+{rolls})"
    return texto

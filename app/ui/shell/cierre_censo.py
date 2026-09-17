"""Cerrar una pasada de censo desde un botón: el ida y vuelta entre la UI y el hilo del monitor.

Reemplaza a la hotkey F8 (2026-09-17). ZZZ corre como administrador y Windows (UIPI) no le entrega
las teclas a un proceso sin elevar mientras el juego tiene el foco: F8 no andaba justo en juego.

El flujo tiene dos vueltas y **ninguna cierra desde el hilo de la UI**:

1. El botón pide; el monitor responde con lo que cerraría (`accion="confirmar"`) sin cerrar nada.
2. El diálogo lo muestra. Si se acepta, se vuelve a pedir con esa misma instantánea como
   confirmación, y el monitor cierra sólo si lo abierto sigue siendo exactamente eso — si cambió,
   pregunta otra vez (`Monitor.cerrar_censo`).

La pregunta al usuario es inyectable (`preguntar`): la ventana principal no se construye en los
tests, así que el flujo tiene que poder probarse sin ella.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Slot

#: Cuántos nombres de huérfanos se muestran antes de resumir con "(+N)".
MUESTRA_HUERFANOS = 8


def _total(n) -> str:
    return "?" if n is None else str(n)


def texto_confirmacion(inst: dict) -> str:
    """Lo que el diálogo dice: qué pasadas se cierran, con su cobertura, y a quiénes se declararía
    huérfanos. Los números son los de la instantánea — lo mismo que el monitor va a comparar."""
    lineas: list[str] = []
    for clave, nombre in (("discos", "Discos"), ("armas", "W-Engines")):
        r = inst.get(clave)
        if r is None:
            continue
        linea = f"{nombre}: {r['registrados']}/{_total(r.get('total_pantalla'))} registrados"
        if r.get("faltan"):
            linea += f" (faltan {r['faltan']})"
        lineas.append(linea)
    roster = inst.get("roster")
    if roster is not None:
        pend = list(roster["pendientes"])
        linea = f"Roster: {roster['vistos']}/{roster['total']} vistos"
        if pend:
            muestra = ", ".join(pend[:MUESTRA_HUERFANOS])
            if len(pend) > MUESTRA_HUERFANOS:
                muestra += f", … (+{len(pend) - MUESTRA_HUERFANOS})"
            linea += f" — se declararían HUÉRFANOS {len(pend)}: {muestra}"
        else:
            linea += " — sin huérfanos"
        lineas.append(linea)
    cuerpo = "\n".join(f"• {l}" for l in lineas)
    return (f"Se van a cerrar estas pasadas de censo:\n\n{cuerpo}\n\n"
            "Una pasada cerrada no se reabre en esta sesión.")


def lineas_resultado(res: dict) -> list[str]:
    """La respuesta del monitor, en líneas para la consola de la vista en vivo."""
    accion = res.get("accion")
    if accion == "nada":
        return ["[censo] no hay ninguna pasada abierta que cerrar"]
    if accion == "sin_monitor":
        return ["[censo] el monitor está detenido — no hay pasada que cerrar"]
    if accion == "error":
        return ["[censo] el cierre falló — ver app.log"]
    if accion != "cerrado":
        return []
    lineas: list[str] = []
    d = res.get("discos")
    if d is not None:
        lineas.append(f"[censo-discos] pasada cerrada — {d['registrados']}/"
                      f"{_total(d.get('total_pantalla'))} registrados · {d['con_dueno']} con dueño · "
                      f"{d['libres']} libres · {d['sin_resolver']} sin resolver")
    a = res.get("armas")
    if a is not None:
        lineas.append(f"[censo-armas] pasada cerrada — {a['registrados']}/"
                      f"{_total(a.get('total_pantalla'))} registradas · {a['con_dueno']} con dueño · "
                      f"{a['sin_resolver']} sin resolver · {a['fuera_de_catalogo']} fuera de catálogo")
    reg = res.get("roster")
    if reg is not None:
        r = reg["resumen"]
        lineas.append(f"[censo] pasada del roster cerrada — {r['vistos']}/{r['total_db']} vistos · "
                      f"{r['huerfanos']} huérfanos")
    return lineas


class FlujoCierreCenso(QObject):
    """Cablea las acciones del sidebar con el controller.

    Es un `QObject` a propósito: `censo_cierre_resultado` se emite desde el hilo del monitor, y sólo
    con un receptor QObject Qt encola la llamada al hilo de la UI — que es donde puede abrirse un
    diálogo.
    """

    def __init__(self, controller, sidebar, log: Callable[[str], None],
                 preguntar: Callable[[str], bool], parent: QObject | None = None):
        super().__init__(parent)
        self._c = controller
        self._sidebar = sidebar
        self._log = log
        self._preguntar = preguntar
        sidebar.pausa_pedida.connect(controller.toggle_pause)
        sidebar.cierre_censo_pedido.connect(self._pedir)
        controller.censo_cierre_resultado.connect(self._on_resultado)
        controller.monitor_started.connect(sidebar.on_monitor_started)
        controller.monitor_stopped.connect(sidebar.on_monitor_stopped)
        controller.pause_changed.connect(sidebar.on_pause_changed)

    @Slot()
    def _pedir(self) -> None:
        self._c.pedir_cierre_censo()

    @Slot(dict)
    def _on_resultado(self, res: dict) -> None:
        if res.get("accion") == "confirmar":
            inst = res["instantanea"]
            if self._preguntar(texto_confirmacion(inst)):
                # El botón sigue en "Cerrando…": la respuesta de esta segunda vuelta lo libera.
                self._c.pedir_cierre_censo(inst)
                return
            self._log("[censo] cierre cancelado — no se cerró nada")
        else:
            for linea in lineas_resultado(res):
                self._log(linea)
        self._sidebar.cierre_terminado()

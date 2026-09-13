"""La vista "Captura en vivo" completa: card del ítem, región derecha (vacía) y consola.

Recibe las señales del `MonitorController` y reparte:

| señal | a dónde |
|---|---|
| `disc_observed` (S17/S9, dueño en pantalla) | card → disco, con el build del dueño |
| `disc_detected` (drops S3/S6/S7) | card → disco **sin** dueño; score y variante se IGNORAN |
| `weapon_seen` | card → arma |
| `log_message`, `error_occurred` | consola |
| `state_changed` | consola (estado actual) |

`disc_detected` trae un score y un "PJ sugerido" que salen del scoring, que **no está calibrado**
(los 51 thresholds en el default). Por eso se traduce a la forma de `disc_observed` descartando
esos campos: la card nunca ve un `target`, y no puede dibujar el build de un PJ que el scoring eligió.

La región derecha queda EN BLANCO por decisión de Daniel, en un contenedor propio y sustituible
(`region_derecha`) para que ahí entre después lo que se decida — cards de scoring o la consola
agrandada — sin rearmar el layout.

Los nombres de las señales y slots de control son los del `LivePanel` viejo, para que el cableado
de `main.py` cambie de destino y no de forma.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.live.console import Console
from app.ui.live.item_card import ItemCard

#: Nombre de PJ → {slot: {"logo", "nivel"}}. Inyectable para testear sin DB.
BuildFn = Callable[[str], dict]


def drop_como_observacion(payload: dict) -> dict:
    """Payload de `disc_detected` → forma de `disc_observed`, SIN lo que sale del scoring.

    Un drop recién obtenido no tiene dueño: su tenencia es `nuevo`. `target`, `score`, `variant`,
    `threshold` y `urgency` no pasan — ése es el punto de la función."""
    main_value = payload.get("main_value") or ""
    # Los crudos primero (`main_valor`/`main_unidad`, desde el 2026-09-12): el texto está redondeado
    # a un decimal. El parseo del texto queda como respaldo para payloads viejos.
    valor, unidad = payload.get("main_valor"), payload.get("main_unidad")
    if valor is None and main_value:
        unidad = "%" if main_value.endswith("%") else "flat"
        try:
            valor = float(main_value.rstrip("%"))
        except ValueError:
            valor = None
    rareza = payload.get("rarity")
    return {
        "set":          payload.get("set") or "?",
        "set_logo":     payload.get("set_logo"),
        "set_tier":     None,
        "slot":         payload.get("slot"),
        "rareza":       rareza if rareza in ("S", "A", "B") else None,
        "nivel":        payload.get("nivel"),
        "main":         payload.get("main") or "?",
        "main_valor":   valor,
        "main_unidad":  unidad,
        "subs_detail":  list(payload.get("subs_detail") or []),
        "dueno":        None,
        "dueno_avatar": None,
        "tenencia":     "nuevo",
    }


class LiveView(QWidget):
    start_monitor_requested = Signal()
    stop_monitor_requested = Signal()
    pause_toggle_requested = Signal()      # compat con el cableado de F10 en main.py

    def __init__(self, build_fn: BuildFn | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_fn = build_fn or (lambda _n: {})
        self.setStyleSheet(f"background: {T.BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        arriba = QHBoxLayout()
        arriba.setSpacing(12)
        self.item_card = ItemCard()
        self.item_card.setFixedWidth(400)
        arriba.addWidget(self.item_card)
        self.region_derecha = QWidget()
        self.region_derecha.setObjectName("region_derecha")
        QVBoxLayout(self.region_derecha).setContentsMargins(0, 0, 0, 0)
        arriba.addWidget(self.region_derecha, 1)
        root.addLayout(arriba, 1)

        self.console = Console()
        self.console.setFixedHeight(210)
        root.addWidget(self.console)

        self.console.start_monitor_requested.connect(self.start_monitor_requested.emit)
        self.console.stop_monitor_requested.connect(self.stop_monitor_requested.emit)

    # --- ítems --------------------------------------------------------------------------------

    def on_disc_observed(self, payload: dict) -> None:
        dueno = payload.get("dueno")
        build = self._build_fn(dueno) if dueno else None
        self.item_card.mostrar_disco(payload, build)

    def on_disc_detected(self, payload: dict) -> None:
        self.item_card.mostrar_disco(drop_como_observacion(payload), None)

    def on_weapon_seen(self, payload: dict) -> None:
        self.item_card.mostrar_arma(payload)

    # --- consola y estado ---------------------------------------------------------------------

    def append_log(self, msg: str) -> None:
        self.console.append_log(msg)

    def on_error(self, msg: str) -> None:
        self.console.append_log(f"[error] {msg}")

    def on_state_changed(self, code: str, confidence: float) -> None:
        self.console.on_state_changed(code, confidence)

    def on_monitor_started(self) -> None:
        self.console.on_monitor_started()
        self.console.append_log("[monitor] Capturando. F10 pausa.")

    def on_monitor_stopped(self) -> None:
        self.console.on_monitor_stopped()
        self.console.append_log("[monitor] Detenido.")

    def on_pause_changed(self, paused: bool) -> None:
        self.console.append_log("[monitor] Pausado." if paused else "[monitor] Reanudado.")

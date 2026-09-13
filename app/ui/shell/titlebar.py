"""Barra de título propia (la ventana es frameless) — portada de `TitleBar` en panel.jsx.

Logo, estado del monitor y los botones de ventana. **Sin FPS ni latencia**: decisión de Daniel (no
le dicen nada al usuario), y además el `18 FPS` del mockup era ficción — el ciclo real del
inventario tarda 1569 ms (`audit/latencia_y_badges_20260912.md`).

El estado del monitor sí va: es lo único de esta franja que responde "¿me está mirando?".

El arrastre de la ventana NO se implementa acá: lo resuelve Windows vía `WM_NCHITTEST` en
`window.py`, que le dice al sistema qué zona de esta barra es "caption". Esta clase sólo expone
`is_drag_area(pos)`.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui import tokens as T

_ESTADOS = {
    "reposo":  ("EN REPOSO", T.TEXT_MUTED),
    "captura": ("CAPTURA",   T.POSITIVE),
    "pausado": ("PAUSADO",   T.YELLOW),
}


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    def __init__(self, version: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(T.TITLEBAR_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("titlebar")
        self.setStyleSheet(
            f"QWidget#titlebar {{ background: {T.BG_DEEP};"
            f" border-bottom: 1px solid {T.BORDER_SUBTLE}; }}"
        )
        self._running = False
        self._paused = False
        self._build(version)
        self._apply_state()

    def _build(self, version: str) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 6, 0)
        lay.setSpacing(10)

        mark = QLabel("D")
        mark.setFixedSize(22, 22)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFont(T.font_display(10, bold=True))
        mark.setStyleSheet(
            f"color: {T.YELLOW}; border: 2px solid {T.YELLOW}; border-radius: 11px;"
        )
        lay.addWidget(mark)

        titulo = QLabel(
            f'<span style="color:{T.TEXT_PRIMARY}">DANIBOD</span>'
            f' <span style="color:{T.YELLOW}">//</span>'
            f' <span style="color:{T.TEXT_PRIMARY}">ZZZ ANALYTICS</span>'
        )
        titulo.setFont(T.font_display(10, bold=True))
        self._titulo = titulo
        lay.addWidget(titulo)
        if version:
            v = QLabel(version)
            v.setFont(T.font_mono(7))
            v.setStyleSheet(f"color: {T.TEXT_MUTED};")
            lay.addWidget(v)

        lay.addStretch(1)

        self._state = QLabel()
        self._state.setFont(T.font_caps(8, bold=True))
        lay.addWidget(self._state)
        lay.addSpacing(12)

        self._btn_min = self._boton("—", self.minimize_requested.emit)
        self._btn_max = self._boton("□", self.maximize_toggle_requested.emit)
        self._btn_close = self._boton("✕", self.close_requested.emit, peligro=True)
        for b in (self._btn_min, self._btn_max, self._btn_close):
            lay.addWidget(b)

    def _boton(self, glifo: str, slot, peligro: bool = False) -> QPushButton:
        b = QPushButton(glifo)
        b.setFixedSize(34, 26)
        b.setFont(T.font_ui(9))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        hover = T.WARNING if peligro else T.BG_PANEL_HI
        b.setStyleSheet(f"""
            QPushButton {{ color: {T.TEXT_MUTED}; background: transparent; border: none; }}
            QPushButton:hover {{ background: {hover}; color: {T.TEXT_PRIMARY}; }}
        """)
        b.clicked.connect(slot)
        return b

    # --- estado del monitor (mismos nombres de slot que el LivePanel viejo) --------------------

    def on_monitor_started(self) -> None:
        self._running, self._paused = True, False
        self._apply_state()

    def on_monitor_stopped(self) -> None:
        self._running, self._paused = False, False
        self._apply_state()

    def on_pause_changed(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._apply_state()

    def _clave_estado(self) -> str:
        if not self._running:
            return "reposo"
        return "pausado" if self._paused else "captura"

    def _apply_state(self) -> None:
        texto, color = _ESTADOS[self._clave_estado()]
        self._state.setText(f"● {texto}")
        self._state.setStyleSheet(f"color: {color};")

    def state_text(self) -> str:
        return _ESTADOS[self._clave_estado()][0]

    # --- arrastre -----------------------------------------------------------------------------

    def is_drag_area(self, pos: QPoint) -> bool:
        """¿Ese punto (en coordenadas de esta barra) arrastra la ventana? Todo menos los botones."""
        hijo = self.childAt(pos)
        return not isinstance(hijo, QPushButton)

"""La consola de reconocimiento — la franja de abajo de la vista en vivo.

A la izquierda, la pantalla que el detector cree estar viendo. A la derecha, el log de siempre
(`controller.log_message`) con el tag de cada línea coloreado.

Conserva el tope del `QTextEdit` viejo: **1000 bloques** (RNF-06 — un log sin techo es una fuga en
una sesión larga de censo).

Y lleva el único control de la pantalla: iniciar / detener la captura. No es un "botón de acción"
de los que Daniel sacó —esos actuaban sobre el JUEGO—: controla la app, y sin él una sesión con
`DANIBOD_NO_AUTOSTART=1` no tendría forma de arrancar.
"""
from __future__ import annotations

import datetime
import html
import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.ui import tokens as T

MAX_BLOQUES = 1000

_TAG = re.compile(r"^\[([^\]]+)\]\s*")
_TAG_COLOR = {
    "error": T.WARNING, "reconocido": T.POSITIVE, "persistido": T.POSITIVE,
    "censo": T.YELLOW, "monitor": T.INFO, "auto": T.INFO, "disco": T.TEXT_SECONDARY,
    "asignado": T.PURPLE, "equipamiento": T.PURPLE,
}


def formatear_linea(ts: str, msg: str) -> str:
    """Línea del log → HTML con el tag coloreado. Todo lo que viene del log se ESCAPA: los nombres
    leídos por OCR pueden traer `<` o `&`, y sin escapar romperían el render o se interpretarían."""
    m = _TAG.match(msg)
    tag_html = ""
    cuerpo = msg
    if m:
        tag = m.group(1)
        color = _TAG_COLOR.get(tag.split("/")[0].lower(), T.TEXT_MUTED)
        tag_html = f'<span style="color:{color}">[{html.escape(tag)}]</span> '
        cuerpo = msg[m.end():]
    return (f'<span style="color:{T.TEXT_DIM}">{html.escape(ts)}</span>&nbsp;&nbsp;'
            f'{tag_html}<span style="color:{T.TEXT_SECONDARY}">{html.escape(cuerpo)}</span>')


class Console(QFrame):
    start_monitor_requested = Signal()
    stop_monitor_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("console")
        self.setStyleSheet(
            f"QFrame#console {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER_SUBTLE};"
            f" border-radius: 4px; }}"
        )
        self._running = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        cab = QFrame()
        cab.setStyleSheet(f"QFrame {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(12, 6, 8, 6)
        punto = QLabel("●")
        punto.setStyleSheet(f"color: {T.PURPLE}; border: none;")
        titulo = QLabel("CONSOLA · RECONOCIMIENTO DE PANTALLAS")
        titulo.setFont(T.font_caps(8, bold=True))
        titulo.setStyleSheet(f"color: {T.TEXT_PRIMARY}; border: none;")
        self._toggle = QPushButton("Iniciar captura")
        self._toggle.setFixedHeight(22)
        self._toggle.setFont(T.font_caps(7, bold=True))
        self._toggle.clicked.connect(self._on_toggle)
        cl.addWidget(punto)
        cl.addWidget(titulo, 1)
        cl.addWidget(self._toggle)
        root.addWidget(cab)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)

        izq = QFrame()
        izq.setFixedWidth(200)
        izq.setStyleSheet(f"QFrame {{ border-right: 1px solid {T.BORDER_SUBTLE}; }}")
        il = QVBoxLayout(izq)
        il.setContentsMargins(14, 10, 14, 10)
        il.setSpacing(2)
        rot = QLabel("ESTADO ACTUAL")
        rot.setFont(T.font_caps(7, bold=True))
        rot.setStyleSheet(f"color: {T.TEXT_MUTED}; border: none;")
        self._estado = QLabel("—")
        self._estado.setFont(T.font_display(18, bold=True))
        self._estado.setStyleSheet(f"color: {T.YELLOW}; border: none;")
        self._conf = QLabel("")
        self._conf.setFont(T.font_mono(8))
        self._conf.setStyleSheet(f"color: {T.TEXT_MUTED}; border: none;")
        il.addWidget(rot)
        il.addWidget(self._estado)
        il.addWidget(self._conf)
        il.addStretch(1)
        cuerpo.addWidget(izq)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.document().setMaximumBlockCount(MAX_BLOQUES)
        self._log.setFont(T.font_mono(8))
        self._log.setStyleSheet(
            f"QTextEdit {{ background: {T.BG_DEEP}; border: none; color: {T.TEXT_SECONDARY};"
            f" padding: 6px 10px; }}"
        )
        cuerpo.addWidget(self._log, 1)
        root.addLayout(cuerpo, 1)
        self._restyle_toggle()

    # --- log ----------------------------------------------------------------------------------

    def append_log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append(formatear_linea(ts, str(msg)))
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def texto_log(self) -> str:
        return self._log.toPlainText()

    def bloques(self) -> int:
        return self._log.document().blockCount()

    # --- estado del detector ------------------------------------------------------------------

    def on_state_changed(self, code: str, confidence: float) -> None:
        self._estado.setText(code or "—")
        self._conf.setText(f"conf {confidence:.2f}" if confidence is not None else "")

    def estado_text(self) -> str:
        return self._estado.text()

    # --- control de la captura ----------------------------------------------------------------

    def on_monitor_started(self) -> None:
        self._running = True
        self._restyle_toggle()

    def on_monitor_stopped(self) -> None:
        self._running = False
        self._restyle_toggle()

    def _on_toggle(self) -> None:
        (self.stop_monitor_requested if self._running else self.start_monitor_requested).emit()

    def toggle_text(self) -> str:
        return self._toggle.text()

    def _restyle_toggle(self) -> None:
        acento = T.WARNING if self._running else T.POSITIVE
        self._toggle.setText("Detener captura" if self._running else "Iniciar captura")
        self._toggle.setStyleSheet(f"""
            QPushButton {{ color: {acento}; background: transparent; border: 1px solid {acento};
                           border-radius: 3px; padding: 0 10px; }}
            QPushButton:hover {{ background: {acento}; color: {T.BG_BASE}; }}
        """)

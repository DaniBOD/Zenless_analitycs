"""Barra inferior — portada de `StatusBar` en panel.jsx. Reemplaza a la vieja pestaña `Estado`.

Sólo muestra datos que el sistema CONOCE. Lo que el mockup inventaba no va:

- `CICLO ACTUAL · 12 / 28d` — el ciclo de Shiyu no lo lee nada todavía.
- `OCR · TESSERACT 5.4` — el backend lo elige el proceso del OCR, no la UI; queda un setter
  (`set_ocr`) y hasta que alguien lo llame dice `—`.

Y agrega uno que el mockup no tenía y que sí importa: **SÓLO LECTURA** cuando la app corre con la DB
protegida (QA). Sin eso, una sesión de prueba se ve idéntica a una que escribe.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui import tokens as T

UID = "1000860143"


def _mb(path: Path | None) -> str:
    try:
        return f"{path.stat().st_size / (1024 * 1024):.1f} MB" if path else "—"
    except OSError:
        return "—"


class StatusBar(QWidget):
    def __init__(self, db_path: Path | None = None, readonly: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(T.STATUSBAR_H)
        self.setObjectName("statusbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#statusbar {{ background: {T.BG_STATUSBAR};"
            f" border-top: 1px solid {T.BORDER_SUBTLE}; }}"
        )
        self._db_path = db_path
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(16)

        self._db = self._lbl(f"SQLITE · {_mb(db_path)}")
        self._ocr = self._lbl("OCR · —")
        lay.addWidget(self._db)
        lay.addWidget(self._ocr)
        self._ro = self._lbl("SÓLO LECTURA", T.YELLOW)
        self._ro.setVisible(readonly)
        lay.addWidget(self._ro)
        lay.addStretch(1)
        lay.addWidget(self._lbl(f"UID {UID}"))
        self._clock = self._lbl("")
        lay.addWidget(self._clock)

        self._tick()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _lbl(self, texto: str, color: str = T.TEXT_MUTED) -> QLabel:
        l = QLabel(texto)
        l.setFont(T.font_mono(7))
        l.setStyleSheet(f"color: {color};")
        return l

    def _tick(self) -> None:
        self._clock.setText(datetime.datetime.now().strftime("%H:%M:%S"))

    def set_ocr(self, texto: str) -> None:
        self._ocr.setText(f"OCR · {texto or '—'}")

    def refresh_db_size(self) -> None:
        self._db.setText(f"SQLITE · {_mb(self._db_path)}")

    def readonly_visible(self) -> bool:
        return not self._ro.isHidden()

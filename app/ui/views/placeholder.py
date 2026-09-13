"""Vista de relleno para las secciones que todavía no existen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def make_placeholder(title: str, description: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl = QLabel(title)
    lbl.setObjectName("title")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    desc = QLabel(description)
    desc.setObjectName("subtitle")
    desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.addWidget(lbl)
    v.addWidget(desc)
    return w

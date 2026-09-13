"""La banda de filtros de la pantalla Roster — 104 px, tres filas de chips.

Los filtros son **del dominio** (elemento, rango, rol, facción), no genéricos. La tercera fila es la
banda ámbar de "estado de build" que heredan Discos y Armas: responde *a qué le faltan datos*.

Cada chip lleva el conteo sobre el roster completo, no sobre lo filtrado: un número que cambia al
tocar otro chip se lee como un error. La lógica de qué pasa el filtro vive en `datos.filtrar`.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui import tokens as T
from app.ui.roster.celda import AMBAR
from app.ui.roster.datos import ESTADOS, CeldaPJ, cumple_estado

_ORDEN_RANGO = ["∞", "S", "A"]


def _chip_css(color: str) -> str:
    return (
        f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent;"
        f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}"
        f"QPushButton:hover {{ border-color: {color}; }}"
        f"QPushButton:checked {{ color: {T.BG_BASE}; background: {color}; border-color: {color}; }}"
    )


def _titulo(texto: str) -> QLabel:
    l = QLabel(texto.upper())
    l.setFont(T.font_caps(7, bold=True))
    l.setFixedWidth(70)
    l.setStyleSheet(f"color: {T.TEXT_MUTED}; background: transparent; border: none;")
    return l


class BandaFiltros(QFrame):
    """`cambiaron()` cada vez que se toca un chip. `seleccion()` → dict para `datos.filtrar`."""

    cambiaron = Signal()
    ALTO = 104

    def __init__(self, celdas: list[CeldaPJ], parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(self.ALTO)
        self.setObjectName("banda_filtros")
        self.setStyleSheet(f"QFrame#banda_filtros {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        self._chips: dict[tuple[str, str], QPushButton] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 6, 16, 6)
        v.setSpacing(4)

        elementos = Counter(c.elemento for c in celdas if c.elemento)
        rangos = Counter(c.rango for c in celdas if c.rango)
        roles = Counter(c.rol for c in celdas if c.rol)
        facciones = Counter(c.faccion for c in celdas if c.faccion)

        # Repartido para que ninguna fila pida más ancho que la ventana mínima (el cuerpo mide
        # ~1100 px): una fila de chips demasiado larga estiraba TODA la vista a 2500 px.

        # fila 1 · elemento
        f1 = self._fila("Elemento")
        for e in sorted(elementos):
            f1.addWidget(self._chip("elemento", e, f"{e} {elementos[e]}", T.color_elemento(e)))
        f1.addStretch()
        v.addLayout(f1)

        # fila 2 · rango + rol
        f2 = self._fila("Rango")
        for r in [r for r in _ORDEN_RANGO if r in rangos]:
            f2.addWidget(self._chip("rango", r, f"{r} {rangos[r]}", T.YELLOW))
        f2.addSpacing(12)
        f2.addWidget(_titulo("Rol"))
        for r in sorted(roles):
            f2.addWidget(self._chip("rol", r, f"{r} {roles[r]}", T.YELLOW))
        f2.addStretch()
        v.addLayout(f2)

        # fila 3 · facción + estado de build (ámbar)
        f3 = self._fila("Facción")
        self.combo_faccion = QComboBox()
        self.combo_faccion.addItem(f"Todas ({len(facciones)})", None)
        for fac in sorted(facciones):
            self.combo_faccion.addItem(f"{fac} · {facciones[fac]}", fac)
        self.combo_faccion.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_faccion.setMinimumContentsLength(22)
        self.combo_faccion.setStyleSheet(
            f"QComboBox {{ color: {T.TEXT_SECONDARY}; background: {T.BG_PANEL};"
            f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}")
        self.combo_faccion.currentIndexChanged.connect(lambda _i: self.cambiaron.emit())
        f3.addWidget(self.combo_faccion)
        f3.addSpacing(12)
        f3.addWidget(_titulo("Estado"))
        for clave, texto in ESTADOS.items():
            n = sum(1 for c in celdas if cumple_estado(c, clave))
            f3.addWidget(self._chip("estado", clave, f"{texto} {n}", AMBAR))
        f3.addStretch()
        self._btn_limpiar = QPushButton("Limpiar filtros")
        self._btn_limpiar.setStyleSheet(
            f"QPushButton {{ color: {T.TEXT_MUTED}; background: transparent; border: none; }}"
            f"QPushButton:hover {{ color: {T.TEXT_PRIMARY}; }}")
        self._btn_limpiar.clicked.connect(self.limpiar)
        f3.addWidget(self._btn_limpiar)
        v.addLayout(f3)

    def _fila(self, titulo: str) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(4)
        h.addWidget(_titulo(titulo))
        return h

    def _chip(self, eje: str, valor: str, texto: str, color: str) -> QPushButton:
        b = QPushButton(texto)
        b.setCheckable(True)
        b.setFont(T.font_ui(8))
        b.setStyleSheet(_chip_css(color))
        b.toggled.connect(lambda _on: self.cambiaron.emit())
        self._chips[(eje, valor)] = b
        return b

    # --- API ------------------------------------------------------------------------------------

    def chip(self, eje: str, valor: str) -> QPushButton:
        return self._chips[(eje, valor)]

    def seleccion(self) -> dict[str, set[str]]:
        sel: dict[str, set[str]] = {}
        for (eje, valor), b in self._chips.items():
            if b.isChecked():
                sel.setdefault(eje, set()).add(valor)
        fac = self.combo_faccion.currentData()
        if fac:
            sel["faccion"] = {fac}
        return sel

    def limpiar(self) -> None:
        for b in self._chips.values():
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.combo_faccion.blockSignals(True)
        self.combo_faccion.setCurrentIndex(0)
        self.combo_faccion.blockSignals(False)
        self.cambiaron.emit()

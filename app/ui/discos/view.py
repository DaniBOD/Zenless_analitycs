"""La pantalla Discos — mockup `22-tab-discos-inventario-completo.png` sin lo que sale del scoring.

| banda | alto | |
|---|--:|---|
| header | 56 | título + totales + cuántos visibles |
| filtros | 76 | `BandaFiltrosDiscos` |
| cuerpo | resto | la tabla (con scroll: 385 filas no entran, decisión de Daniel) + el lateral |
| leyenda | 32 | qué significa cada color |

Fuera del mockup, a propósito: la columna y el filtro de SCORE (0/385 discos lo tienen), las
acciones rápidas, el insight de IA, el paginado y el badge de rareza (no hay columna que lo diga).

La vista no abre el modal: emite `disco_pedido(id)` y lo abre la ventana.
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableView,
    QVBoxLayout, QWidget,
)

from app.ui import tokens as T
from app.ui.discos.datos import FilaDisco, filtrar, leer_inventario
from app.ui.discos.filtros import BandaFiltrosDiscos
from app.ui.discos.lateral import LateralDiscos
from app.ui.discos.tabla import (
    AMBAR_NIVEL, C_DUENO, C_ESTADO, C_ID, C_MAIN, C_NV, C_ROLLS, C_SET, C_SLOT, C_SUBS, COLUMNAS,
    ModeloDiscos,
)
from app.ui.live.item_card import TENENCIA_TEXTO

log = logging.getLogger(__name__)


def _lbl(texto: str, font, color: str) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


class DiscosView(QWidget):
    disco_pedido = Signal(int)

    def __init__(self, con: sqlite3.Connection | None, parent: QWidget | None = None):
        super().__init__(parent)
        self._con = con
        self._filas: list[FilaDisco] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(56)
        header.setObjectName("discos_header")
        header.setStyleSheet(f"QFrame#discos_header {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(14)
        hl.addWidget(_lbl("Discos", T.font_display(16, bold=True), T.TEXT_PRIMARY))
        self._totales = _lbl("", T.font_mono(9), T.TEXT_SECONDARY)
        hl.addWidget(self._totales)
        self._visibles = _lbl("", T.font_mono(9), T.YELLOW)
        hl.addWidget(self._visibles)
        hl.addStretch()
        root.addWidget(header)

        self._slot_filtros = QVBoxLayout()
        self._slot_filtros.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._slot_filtros)
        self.filtros: BandaFiltrosDiscos | None = None

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        self.modelo = ModeloDiscos(self)
        self.tabla = QTableView()
        self.tabla.setModel(self.modelo)
        self.tabla.setSortingEnabled(True)
        # Activar el orden hace que Qt ordene YA por la columna 0 descendente (#ID): se fija el
        # orden de diseño explícitamente después.
        self.tabla.sortByColumn(C_SET, Qt.SortOrder.AscendingOrder)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        self.tabla.setShowGrid(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        cab = self.tabla.horizontalHeader()
        for col, ancho in ((C_ID, 64), (C_SET, 170), (C_SLOT, 34), (C_MAIN, 170), (C_ROLLS, 52),
                           (C_NV, 38), (C_DUENO, 130), (C_ESTADO, 90)):
            cab.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.tabla.setColumnWidth(col, ancho)
        cab.setSectionResizeMode(C_SUBS, QHeaderView.ResizeMode.Stretch)
        cab.setMinimumSectionSize(30)
        self.tabla.setStyleSheet(
            f"QTableView {{ background: {T.BG_BASE}; alternate-background-color: {T.BG_PANEL};"
            f" color: {T.TEXT_PRIMARY}; border: none; selection-background-color: {T.YELLOW_TINT};"
            f" selection-color: {T.TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{ background: {T.BG_DEEP}; color: {T.TEXT_MUTED}; border: none;"
            f" border-bottom: 1px solid {T.BORDER_SUBTLE}; padding: 4px 6px; font-size: 8pt; }}")
        self.tabla.clicked.connect(self._fila_clickeada)
        cuerpo.addWidget(self.tabla, 1)
        self._slot_lateral = QVBoxLayout()
        self._slot_lateral.setContentsMargins(0, 0, 0, 0)
        cuerpo.addLayout(self._slot_lateral)
        self.lateral: LateralDiscos | None = None
        root.addLayout(cuerpo, 1)

        root.addWidget(self._leyenda())
        self.refrescar()

    def _leyenda(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(32)
        f.setObjectName("discos_leyenda")
        f.setStyleSheet(f"QFrame#discos_leyenda {{ border-top: 1px solid {T.BORDER_SUBTLE}; background: {T.BG_DEEP}; }}")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(18)
        for texto, color in ((TENENCIA_TEXTO["equipada"][0], TENENCIA_TEXTO["equipada"][1]),
                             (TENENCIA_TEXTO["libre"][0] + " · sin dueño", TENENCIA_TEXTO["libre"][1]),
                             ("Nv ámbar · nivel distinto de 15", AMBAR_NIVEL),
                             ("click en una fila · detalle del disco", T.TEXT_MUTED)):
            h.addWidget(_lbl(texto, T.font_ui(8), color))
        h.addStretch()
        f.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return f

    # --- datos --------------------------------------------------------------------------------------

    def refrescar(self) -> None:
        self._filas = []
        if self._con is not None:
            try:
                self._filas = leer_inventario(self._con)
            except sqlite3.Error:
                log.exception("[discos] no se pudo leer el inventario")
                self._totales.setText("error al leer la DB")
        eq = sum(1 for f in self._filas if f.equipado)
        self._totales.setText(f"{len(self._filas)} discos · {eq} equipados · {len(self._filas) - eq} libres")

        if self.filtros is not None:
            self._slot_filtros.removeWidget(self.filtros)
            self.filtros.deleteLater()
        self.filtros = BandaFiltrosDiscos(self._filas)
        self.filtros.cambiaron.connect(self._aplicar_filtros)
        self._slot_filtros.addWidget(self.filtros)

        if self.lateral is not None:
            self._slot_lateral.removeWidget(self.lateral)
            self.lateral.deleteLater()
        self.lateral = LateralDiscos(self._filas)
        self.lateral.set_elegido.connect(lambda s: self.filtros.elegir("set", s))
        self._slot_lateral.addWidget(self.lateral)

        self._aplicar_filtros()

    def _aplicar_filtros(self) -> None:
        visibles = filtrar(self._filas, self.filtros.seleccion())
        self.modelo.set_filas(visibles)
        self._visibles.setText(f"{len(visibles)} visibles")

    def _fila_clickeada(self, index) -> None:
        if index.isValid():
            self.disco_pedido.emit(self.modelo.fila(index.row()).id)

    def showEvent(self, ev):
        """Al volver a la pestaña se relee: una lectura del monitor pudo cambiar el inventario."""
        super().showEvent(ev)
        if self._filas and self._con is not None:
            sel = self.filtros.seleccion() if self.filtros else {}
            self.refrescar()
            for eje, valores in sel.items():
                for v in valores:
                    if eje in ("set", "main", "dueno"):
                        self.filtros.elegir(eje, v)
                    else:
                        self.filtros.chip(eje, v).setChecked(True)

    # --- introspección para tests -----------------------------------------------------------------

    def ids_visibles(self) -> list[int]:
        return self.modelo.ids()

    def columnas(self) -> list[str]:
        return list(COLUMNAS)

    def texto_header(self) -> str:
        return f"{self._totales.text()}  {self._visibles.text()}"

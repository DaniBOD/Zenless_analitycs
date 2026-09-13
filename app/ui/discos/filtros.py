"""La banda de filtros de Discos — mismo patrón que la del Roster, con los ejes del dominio.

Dos filas para que ninguna pida más ancho que la ventana mínima:

- chips de **slot** (1–6) y de **estado** (equipado / libre), con su conteo;
- combos de **set**, **main** y **asignado**, que tienen demasiados valores para chips.

Los conteos son sobre el inventario completo, no sobre lo filtrado (un número que cambia al tocar
otro filtro se lee como un error). Qué pasa un filtro lo decide `datos.filtrar`.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.discos.datos import FilaDisco
from app.ui.live.item_card import TENENCIA_TEXTO

ALTO = 76


def _chip_css(color: str) -> str:
    return (f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent;"
            f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}"
            f"QPushButton:hover {{ border-color: {color}; }}"
            f"QPushButton:checked {{ color: {T.BG_BASE}; background: {color}; border-color: {color}; }}")


def _titulo(texto: str) -> QLabel:
    l = QLabel(texto.upper())
    l.setFont(T.font_caps(7, bold=True))
    l.setStyleSheet(f"color: {T.TEXT_MUTED}; background: transparent; border: none;")
    return l


class BandaFiltrosDiscos(QFrame):
    cambiaron = Signal()

    def __init__(self, filas: list[FilaDisco], parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(ALTO)
        self.setObjectName("banda_filtros_discos")
        self.setStyleSheet(f"QFrame#banda_filtros_discos {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        self._chips: dict[tuple[str, object], QPushButton] = {}
        self._combos: dict[str, QComboBox] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 6, 16, 6)
        v.setSpacing(4)

        slots = Counter(f.slot for f in filas)
        f1 = QHBoxLayout()
        f1.setSpacing(4)
        f1.addWidget(_titulo("Slot"))
        for s in range(1, 7):
            f1.addWidget(self._chip("slot", s, f"{s} · {slots.get(s, 0)}", T.YELLOW))
        f1.addSpacing(14)
        f1.addWidget(_titulo("Estado"))
        n_eq = sum(1 for f in filas if f.equipado)
        for clave, n, tenencia in (("equipado", n_eq, "equipada"), ("libre", len(filas) - n_eq, "libre")):
            texto, color = TENENCIA_TEXTO[tenencia]
            f1.addWidget(self._chip("estado", clave, f"{texto.capitalize()} {n}", color))
        f1.addStretch()
        limpiar = QPushButton("Limpiar filtros")
        limpiar.setStyleSheet(f"QPushButton {{ color: {T.TEXT_MUTED}; background: transparent; border: none; }}"
                              f"QPushButton:hover {{ color: {T.TEXT_PRIMARY}; }}")
        limpiar.clicked.connect(self.limpiar)
        f1.addWidget(limpiar)
        v.addLayout(f1)

        f2 = QHBoxLayout()
        f2.setSpacing(6)
        for eje, titulo, valores in (
            ("set", "Set", Counter(f.set for f in filas if f.set)),
            ("main", "Main", Counter(f.main for f in filas if f.main)),
            ("dueno", "Asignado", Counter(f.dueno for f in filas if f.dueno)),
        ):
            f2.addWidget(_titulo(titulo))
            c = QComboBox()
            c.addItem(f"Todos ({len(valores)})", None)
            for val, n in sorted(valores.items(), key=lambda x: x[0].casefold()):
                c.addItem(f"{val} · {n}", val)
            c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(16)
            c.setStyleSheet(f"QComboBox {{ color: {T.TEXT_SECONDARY}; background: {T.BG_PANEL};"
                            f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}")
            c.currentIndexChanged.connect(lambda _i: self.cambiaron.emit())
            self._combos[eje] = c
            f2.addWidget(c)
            f2.addSpacing(10)
        f2.addStretch()
        v.addLayout(f2)

    def _chip(self, eje: str, valor, texto: str, color: str) -> QPushButton:
        b = QPushButton(texto)
        b.setCheckable(True)
        b.setFont(T.font_ui(8))
        b.setStyleSheet(_chip_css(color))
        b.toggled.connect(lambda _on: self.cambiaron.emit())
        self._chips[(eje, valor)] = b
        return b

    # --- API ------------------------------------------------------------------------------------

    def chip(self, eje: str, valor) -> QPushButton:
        return self._chips[(eje, valor)]

    def elegir(self, eje: str, valor: str | None) -> None:
        """Selecciona `valor` en el combo del eje (None = Todos)."""
        c = self._combos[eje]
        i = c.findData(valor) if valor is not None else 0
        c.setCurrentIndex(max(i, 0))

    def seleccion(self) -> dict[str, set]:
        sel: dict[str, set] = {}
        for (eje, valor), b in self._chips.items():
            if b.isChecked():
                sel.setdefault(eje, set()).add(valor)
        for eje, c in self._combos.items():
            if c.currentData() is not None:
                sel[eje] = {c.currentData()}
        return sel

    def limpiar(self) -> None:
        for w in [*self._chips.values(), *self._combos.values()]:
            w.blockSignals(True)
        for b in self._chips.values():
            b.setChecked(False)
        for c in self._combos.values():
            c.setCurrentIndex(0)
        for w in [*self._chips.values(), *self._combos.values()]:
            w.blockSignals(False)
        self.cambiaron.emit()

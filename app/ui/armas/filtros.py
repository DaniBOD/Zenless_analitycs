"""La banda de filtros de Armas — porta `EFilters` de `engines-screen.jsx`.

Dos filas:

1. **ejes**: rareza (S / A), estado (equipada / libre) y especialidad.
2. **la banda ámbar** de auditoría y progreso, el patrón que hereda del Roster:
   PJs sin arma · sin usar · nivel < 60 · P < 5 · **nivel sin leer · P sin leer** · sin ícono.

"Sin leer" y "por subir" son chips distintos a propósito (lo remarca el diseño): un nivel que no se
leyó no es un nivel bajo. Hoy los dos "sin leer" dan 0 — el censo leyó todo —, y se muestran igual,
deshabilitados: que el contador exista es lo que dice que se miró.

Del diseño no se porta el "agrupar por" (una celda por arma física, decisión de Daniel) ni los
botones del header (Exportar, Comparar): el comparador va en otra fase.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.armas.celda import AMBAR, color_rareza
from app.ui.armas.datos import AUDITORIA, FilaArma, auditoria
from app.ui.live.item_card import TENENCIA_TEXTO

ALTO = 76


def _chip_css(color: str) -> str:
    return (f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent;"
            f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}"
            f"QPushButton:hover {{ border-color: {color}; }}"
            f"QPushButton:checked {{ color: {T.BG_BASE}; background: {color}; border-color: {color}; }}"
            f"QPushButton:disabled {{ color: {T.TEXT_DIM}; border-color: {T.BORDER_SUBTLE}; }}")


def _titulo(texto: str, color: str = T.TEXT_MUTED) -> QLabel:
    l = QLabel(texto.upper())
    l.setFont(T.font_caps(7, bold=True))
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


class BandaFiltrosArmas(QFrame):
    cambiaron = Signal()

    def __init__(self, filas: list[FilaArma], n_pjs_sin_arma: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(ALTO)
        self.setObjectName("banda_filtros_armas")
        self.setStyleSheet(f"QFrame#banda_filtros_armas {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        self._chips: dict[tuple[str, str], QPushButton] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 6, 16, 6)
        v.setSpacing(4)

        f1 = QHBoxLayout()
        f1.setSpacing(4)
        f1.addWidget(_titulo("Rareza"))
        rarezas = Counter(f.rareza for f in filas)
        for r in ("S", "A"):
            f1.addWidget(self._chip("rareza", r, f"{r} {rarezas.get(r, 0)}", color_rareza(r)))
        f1.addSpacing(12)
        f1.addWidget(_titulo("Estado"))
        n_eq = sum(1 for f in filas if f.equipado)
        for clave, n, tenencia in (("equipada", n_eq, "equipada"), ("libre", len(filas) - n_eq, "libre")):
            texto, color = TENENCIA_TEXTO[tenencia]
            f1.addWidget(self._chip("estado", clave, f"{texto.capitalize()} {n}", color))
        f1.addSpacing(12)
        f1.addWidget(_titulo("Especialidad"))
        esp = Counter(f.especialidad or "sin dato" for f in filas)
        self.combo_especialidad = QComboBox()
        self.combo_especialidad.addItem(f"Todas ({len(esp)})", None)
        for nombre, n in sorted(esp.items(), key=lambda x: x[0].casefold()):
            self.combo_especialidad.addItem(f"{nombre} · {n}", nombre)
        self.combo_especialidad.setStyleSheet(
            f"QComboBox {{ color: {T.TEXT_SECONDARY}; background: {T.BG_PANEL};"
            f" border: 1px solid {T.BORDER_MID}; padding: 2px 8px; }}")
        self.combo_especialidad.currentIndexChanged.connect(lambda _i: self.cambiaron.emit())
        f1.addWidget(self.combo_especialidad)
        f1.addStretch()
        limpiar = QPushButton("Limpiar filtros")
        limpiar.setStyleSheet(f"QPushButton {{ color: {T.TEXT_MUTED}; background: transparent; border: none; }}"
                              f"QPushButton:hover {{ color: {T.TEXT_PRIMARY}; }}")
        limpiar.clicked.connect(self.limpiar)
        f1.addWidget(limpiar)
        v.addLayout(f1)

        f2 = QHBoxLayout()
        f2.setSpacing(4)
        grupos = auditoria(filas)
        f2.addWidget(_titulo("Auditoría", AMBAR))
        f2.addWidget(self._chip("auditoria", "pjs_sin_arma", f"PJs sin arma {n_pjs_sin_arma}", AMBAR))
        for clave in ("libres", "sin_icono"):
            f2.addWidget(self._chip("auditoria", clave, f"{AUDITORIA[clave]} {len(grupos[clave])}", AMBAR))
        f2.addSpacing(12)
        f2.addWidget(_titulo("Progreso", AMBAR))
        for clave in ("nivel_bajo", "refin_bajo", "nivel_sin_leer", "refin_sin_leer"):
            b = self._chip("auditoria", clave, f"{AUDITORIA[clave]} {len(grupos[clave])}", AMBAR)
            if clave.endswith("sin_leer"):
                b.setEnabled(bool(grupos[clave]))
                b.setToolTip("Sin leer NO es por subir: son contadores separados.")
            f2.addWidget(b)
        f2.addStretch()
        v.addLayout(f2)

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

    def seleccion(self) -> dict[str, set]:
        sel: dict[str, set] = {}
        for (eje, valor), b in self._chips.items():
            if b.isChecked():
                sel.setdefault(eje, set()).add(valor)
        esp = self.combo_especialidad.currentData()
        if esp is not None:
            # "sin dato" en el combo es `None` en la fila: se traduce acá, no en `datos.filtrar`.
            sel["especialidad"] = {None if esp == "sin dato" else esp}
        return sel

    def limpiar(self) -> None:
        widgets = [*self._chips.values(), self.combo_especialidad]
        for w in widgets:
            w.blockSignals(True)
        for b in self._chips.values():
            b.setChecked(False)
        self.combo_especialidad.setCurrentIndex(0)
        for w in widgets:
            w.blockSignals(False)
        self.cambiaron.emit()

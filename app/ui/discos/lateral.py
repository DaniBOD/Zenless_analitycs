"""La columna lateral de Discos: distribución por set (clickeable) y libres por slot.

Del mockup se sacaron "acciones rápidas" (filtrar, limpiar descartes, re-puntuar) y el "insight"
de IA: la pantalla sólo informa (decisión de Daniel, 2026-09-13). En su lugar entra "libres por
slot", que es la pregunta que el inventario sí puede contestar hoy.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.discos.datos import FilaDisco, distribucion_por_set, libres_por_slot

ANCHO = 240


def _caps(texto: str, color: str = T.TEXT_PRIMARY) -> QLabel:
    l = QLabel(texto.upper())
    l.setFont(T.font_caps(8, bold=True))
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


class _BarraSet(QPushButton):
    """Nombre · conteo, con la barra proporcional abajo. Pintada a mano."""

    def __init__(self, nombre: str, n: int, maximo: int):
        super().__init__()
        self.nombre, self.n, self._frac = nombre, n, n / max(maximo, 1)
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Filtrar la tabla por {nombre}")
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def paintEvent(self, _ev):
        p = QPainter(self)
        r = self.rect()
        if self.underMouse():
            p.fillRect(r, QColor(255, 203, 5, 16))
        p.setFont(T.font_ui(8))
        p.setPen(QColor(T.TEXT_SECONDARY))
        texto = QRectF(4, 0, r.width() - 40, r.height() - 6)
        p.drawText(texto, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   p.fontMetrics().elidedText(self.nombre, Qt.TextElideMode.ElideRight, int(texto.width())))
        p.setFont(T.font_mono(8))
        p.setPen(QColor(T.YELLOW))
        p.drawText(QRectF(r.width() - 36, 0, 32, r.height() - 6),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(self.n))
        base = QRectF(4, r.height() - 5, r.width() - 8, 2)
        p.fillRect(base, QColor(255, 255, 255, 18))
        p.fillRect(QRectF(base.x(), base.y(), base.width() * self._frac, base.height()), QColor(T.YELLOW))
        p.end()


class LateralDiscos(QFrame):
    set_elegido = Signal(str)

    def __init__(self, filas: list[FilaDisco], parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(ANCHO)
        self.setObjectName("lateral_discos")
        self.setStyleSheet(f"QFrame#lateral_discos {{ border-left: 1px solid {T.BORDER_SUBTLE}; }}")
        self._botones: dict[str, _BarraSet] = {}
        self._libres = libres_por_slot(filas)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(2)
        v.addWidget(_caps("Distribución por set"))
        dist = distribucion_por_set(filas)
        maximo = dist[0][1] if dist else 1
        # Los 28 sets en filas de 26 px piden ~730 px: la lista va en su PROPIO scroll. Sin él, la
        # vista entera medía 1106 px de alto y se salía de la ventana.
        lista = QWidget()
        lv = QVBoxLayout(lista)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        for nombre, n in dist:
            b = _BarraSet(nombre, n, maximo)
            b.clicked.connect(lambda _c=False, s=nombre: self.set_elegido.emit(s))
            self._botones[nombre] = b
            lv.addWidget(b)
        lv.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(lista)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        v.addWidget(scroll, 1)
        v.addSpacing(14)
        v.addWidget(_caps("Libres por slot"))
        for slot, n in self._libres.items():
            h = QHBoxLayout()
            h.setContentsMargins(4, 0, 4, 0)
            h.addWidget(_caps(f"Slot {slot}", T.TEXT_SECONDARY))
            h.addStretch()
            valor = QLabel(str(n))
            valor.setFont(T.font_mono(9))
            valor.setStyleSheet(f"color: {T.INFO if n else T.TEXT_DIM}; background: transparent; border: none;")
            h.addWidget(valor)
            v.addLayout(h)
        v.addStretch()

    # --- introspección para tests -----------------------------------------------------------------

    def boton_set(self, nombre: str) -> _BarraSet:
        return self._botones[nombre]

    def textos_libres(self) -> dict[int, int]:
        return dict(self._libres)

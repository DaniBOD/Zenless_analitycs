"""Sidebar del panel principal — portado de `Sidebar` en panel.jsx (mockup de Claude Design).

220 px, gradiente oscuro, bloque de cuenta arriba, tres grupos de navegación y la card de acciones
abajo. Dos diferencias con el mockup, a propósito:

- **Los contadores son de la DB** (`contadores.leer_contadores`), no los del dibujo. Un 0 se ve.
- **Donde el mockup dibujaba hotkeys hay un BOTÓN de pausa** (2026-09-17). ZZZ corre como
  administrador y Windows (UIPI) no le entrega las teclas a la app con el juego en foco: F10 no
  andaba justo en juego. F9 (mostrar el panel) no tiene botón: un botón no puede mostrar la ventana
  en la que vive; lo cubre la bandeja. F8 (cerrar la pasada de censo) se fue sin reemplazo: el
  sistema está siempre operativo y cada ítem nuevo entra solo, no hay pasada que abrir ni cerrar.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui import tokens as T

#: (grupo, [(clave, etiqueta), ...]) en el orden del mockup. La clave es la que usa el stack.
GRUPOS: list[tuple[str, list[tuple[str, str]]]] = [
    ("MONITOREO", [("live", "Captura en vivo"), ("historico", "Histórico"), ("lategame", "Lategame")]),
    ("BUILD",     [("discos", "Discos"), ("roster", "Roster"), ("armas", "Armas"), ("equipos", "Equipos")]),
    ("SISTEMA",   [("catalogos", "Catálogos"), ("config", "Configuración")]),
]

#: Textos del botón de pausa. Los tests afirman sobre estos mismos valores.
TXT_PAUSAR = "Pausar"
TXT_REANUDAR = "Reanudar"

UID = "1000860143"


def _fmt_contador(n: int | None) -> str:
    if n is None:
        return ""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


class _Item(QPushButton):
    """Un ítem de navegación: etiqueta a la izquierda, contador a la derecha, barra amarilla si
    está activo."""

    def __init__(self, clave: str, etiqueta: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.clave = clave
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)
        self._lbl = QLabel(etiqueta)
        self._lbl.setFont(T.font_ui(10))
        self._lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._count = QLabel("")
        self._count.setFont(T.font_mono(8))
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Alto fijo: sin esto la caja se estiraba a todo el alto de la fila (se vio en la captura).
        self._count.setFixedHeight(16)
        self._count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._lbl, 1)
        lay.addWidget(self._count, 0, Qt.AlignmentFlag.AlignVCenter)
        # Arranca OCULTO: un ítem sin contador no dibuja una caja vacía.
        self.set_count("")
        self.toggled.connect(lambda _c: self._restyle())

    def set_count(self, texto: str) -> None:
        self._count.setText(texto)
        self._count.setVisible(bool(texto))
        self._restyle()

    def count_text(self) -> str:
        return self._count.text()

    def count_visible(self) -> bool:
        # `isHidden` y no `isVisible`: offscreen y antes del primer show, `isVisible` da False para
        # TODO y el test pasaría sin mirar nada.
        return not self._count.isHidden()

    def _restyle(self) -> None:
        activo = self.isChecked()
        self.setStyleSheet(f"""
            QPushButton {{
                background: {T.YELLOW_TINT if activo else "transparent"};
                border: none;
                border-left: 2px solid {T.YELLOW if activo else "transparent"};
                margin: 0 8px;
                text-align: left;
            }}
            QPushButton:hover {{ background: {T.BG_ROW_HOVER}; }}
        """)
        self._lbl.setStyleSheet(
            f"color: {T.YELLOW if activo else T.TEXT_SECONDARY}; background: transparent;"
            f"{' font-weight: 600;' if activo else ''}"
        )
        self._count.setStyleSheet(
            f"color: {T.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {T.BORDER_SUBTLE}; border-radius: 3px; padding: 0 5px;"
        )


class Sidebar(QWidget):
    """Navegación y la pausa. Emite `item_selected(clave)` y `pausa_pedida`; no conoce las vistas
    que hay detrás ni al monitor (los cablea la ventana principal)."""

    item_selected = Signal(str)
    pausa_pedida = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(T.SIDEBAR_W)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._items: dict[str, _Item] = {}
        self._running = False
        self._paused = False
        self._build()
        self._set_checked("live")

    # --- construcción -------------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 10)
        root.setSpacing(0)
        root.addWidget(self._bloque_cuenta())
        root.addSpacing(10)

        for grupo, items in GRUPOS:
            cab = QLabel(grupo)
            cab.setFont(T.font_caps(7, bold=True))
            cab.setStyleSheet(f"color: {T.TEXT_MUTED}; padding: 4px 14px 6px 14px;")
            root.addWidget(cab)
            for clave, etiqueta in items:
                it = _Item(clave, etiqueta)
                it.clicked.connect(lambda _c=False, k=clave: self.select(k))
                self._items[clave] = it
                root.addWidget(it)
            root.addSpacing(8)

        root.addStretch(1)
        root.addWidget(self._card_acciones())

    def _bloque_cuenta(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"QFrame {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 6, 14, 12)
        lay.setSpacing(10)
        badge = QLabel("D")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(T.font_display(13, bold=True))
        badge.setStyleSheet(
            f"color: {T.BG_BASE}; border: none; border-radius: 10px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {T.YELLOW}, stop:1 {T.YELLOW_DEEP});"
        )
        col = QVBoxLayout()
        col.setSpacing(1)
        nombre = QLabel("DaniBOD")
        nombre.setFont(T.font_ui(10, bold=True))
        nombre.setStyleSheet(f"color: {T.TEXT_PRIMARY}; border: none;")
        # El mockup ponía "NIVEL 60": el sistema no conoce el nivel de la cuenta, así que no se
        # muestra (RNF-02). El UID sí es un dato fijo y verificado.
        uid = QLabel(f"UID {UID}")
        uid.setFont(T.font_mono(7))
        uid.setStyleSheet(f"color: {T.TEXT_MUTED}; border: none;")
        col.addWidget(nombre)
        col.addWidget(uid)
        lay.addWidget(badge)
        lay.addLayout(col, 1)
        return w

    def _card_acciones(self) -> QWidget:
        card = QFrame()
        card.setObjectName("acciones")
        card.setStyleSheet(
            f"QFrame#acciones {{ margin: 0 10px; border: 1px solid {T.BORDER_SUBTLE};"
            f" border-radius: 6px; background: rgba(0,0,0,0.4); }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)
        cab = QLabel("ACCIONES")
        cab.setFont(T.font_caps(7, bold=True))
        cab.setStyleSheet(f"color: {T.TEXT_MUTED}; border: none;")
        lay.addWidget(cab)
        self.btn_pausa = self._boton_accion(TXT_PAUSAR)
        self.btn_pausa.clicked.connect(lambda _c=False: self.pausa_pedida.emit())
        lay.addWidget(self.btn_pausa)
        self._apply_acciones()
        return card

    def _boton_accion(self, texto: str) -> QPushButton:
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(T.font_ui(8))
        b.setFixedHeight(24)
        b.setStyleSheet(f"""
            QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent;
                          border: 1px solid {T.BORDER_MID}; border-radius: 4px; }}
            QPushButton:hover {{ background: {T.BG_ROW_HOVER}; color: {T.TEXT_PRIMARY}; }}
            QPushButton:disabled {{ color: {T.TEXT_MUTED}; border-color: {T.BORDER_SUBTLE}; }}
        """)
        return b

    # --- acciones: estado ---------------------------------------------------------------------

    def on_monitor_started(self) -> None:
        # Cada arranque crea un Monitor nuevo, que nace corriendo (no pausado).
        self._running, self._paused = True, False
        self._apply_acciones()

    def on_monitor_stopped(self) -> None:
        self._running, self._paused = False, False
        self._apply_acciones()

    def on_pause_changed(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._apply_acciones()

    def _apply_acciones(self) -> None:
        self.btn_pausa.setEnabled(self._running)
        self.btn_pausa.setText(TXT_REANUDAR if self._paused else TXT_PAUSAR)

    def paintEvent(self, ev):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(T.BG_SIDEBAR_TOP))
        g.setColorAt(1.0, QColor(T.BG_SIDEBAR_BOT))
        p.fillRect(self.rect(), g)
        p.setPen(QColor(T.BORDER_SUBTLE))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()
        super().paintEvent(ev)

    # --- API ----------------------------------------------------------------------------------

    def select(self, clave: str) -> None:
        """Activa el ítem y emite su clave. Una clave desconocida no hace nada."""
        if clave not in self._items:
            return
        self._set_checked(clave)
        self.item_selected.emit(clave)

    def _set_checked(self, clave: str) -> None:
        for k, it in self._items.items():
            it.blockSignals(True)
            it.setChecked(k == clave)
            it.blockSignals(False)
            it._restyle()
        self._activo = clave

    def active_key(self) -> str:
        return self._activo

    def set_counters(self, contadores: dict[str, int]) -> None:
        for clave, n in contadores.items():
            if clave in self._items:
                self._items[clave].set_count(_fmt_contador(n))

    def counter_text(self, clave: str) -> str:
        return self._items[clave].count_text() if clave in self._items else ""

    def counter_visible(self, clave: str) -> bool:
        return self._items[clave].count_visible() if clave in self._items else False

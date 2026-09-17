"""El modal de disco — unos 1000×620, sin marco, centrado sobre la ventana.

| mockup | acá |
|---|---|
| encabezado con chips `EQUIPADO · Yanagi` y `SCORE 87.3 · S` | el de estado sí; **el de score no** |
| col 1: set, main, substats con rolls, efectos del conjunto | igual; el badge de rareza **no** (no hay columna) |
| col 2: PJs compatibles ranked | **el dueño con su build** y este slot destacado (decisión de Daniel) |
| col 3: arquetipo, score proyectado, recomendación, historial | **otros discos del mismo set y slot**, sin score |
| pie: bloquear, descartar, reasignar, mejorar, confirmar | **nada** |

Recibe `(con, disco_id)` y no una ficha armada: una alternativa clickeada cambia el disco que se
muestra sin abrir otro modal encima.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui import tokens as T
from app.ui.disco_modal.datos import FichaDisco, ficha_disco
from app.ui.formato import formatear_valor
from app.ui.live.hexagon import BuildHexagon
from app.ui.live.item_card import TENENCIA_TEXTO

ANCHO, ALTO = 1000, 620


def _nivel_txt(nivel: int | None) -> str:
    """`?` cuando el nivel no se leyó (Fase 3). Un `None` interpolado imprimiría literalmente
    "None", y un 0 diría que el disco está en Nivel 0, que es otra cosa."""
    return "?" if nivel is None else str(nivel)


def _lbl(texto: str, font, color: str, wrap: bool = False) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setWordWrap(wrap)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _caps(texto: str, color: str = T.TEXT_MUTED) -> QLabel:
    return _lbl(texto.upper(), T.font_caps(8, bold=True), color)


def _pixmap(path: str | None, lado: int) -> QPixmap | None:
    if not path or not Path(path).exists():
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class _Rolls(QWidget):
    """Cinco casilleros: los rolls de un substat (0–5)."""

    def __init__(self, n: int):
        super().__init__()
        self.n = n
        self.setFixedSize(5 * 8, 8)

    def paintEvent(self, _ev):
        p = QPainter(self)
        for i in range(5):
            lleno = i < self.n
            p.setPen(QColor(T.YELLOW if lleno else T.BORDER_MID))
            p.setBrush(QColor(T.YELLOW) if lleno else Qt.BrushStyle.NoBrush)
            p.drawRect(i * 8, 1, 5, 5)
        p.end()


class DiscoModal(QDialog):
    pj_pedido = Signal(int)

    def __init__(self, con: sqlite3.Connection, disco_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._con = con
        self._ficha: FichaDisco | None = None
        self.hexagono: BuildHexagon | None = None
        self.boton_dueno: QPushButton | None = None
        self._alternativas: dict[int, QPushButton] = {}
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(ANCHO, ALTO)

        marco = QFrame(self)
        marco.setObjectName("disco_modal")
        marco.setGeometry(0, 0, ANCHO, ALTO)
        marco.setStyleSheet(f"QFrame#disco_modal {{ background: {T.BG_PANEL}; border: 2px solid {T.YELLOW}; }}")
        self._root = QVBoxLayout(marco)
        self._root.setContentsMargins(20, 14, 20, 18)
        self._root.setSpacing(12)
        self._contenido: QWidget | None = None
        self.cargar(disco_id)

    # --- carga ------------------------------------------------------------------------------------

    def disco_id(self) -> int | None:
        return self._ficha.disco.id if self._ficha else None

    def cargar(self, disco_id: int) -> None:
        self._ficha = ficha_disco(self._con, disco_id)
        if self._contenido is not None:
            self._root.removeWidget(self._contenido)
            self._contenido.deleteLater()
        self.hexagono, self.boton_dueno, self._alternativas = None, None, {}
        self._contenido = QWidget()
        v = QVBoxLayout(self._contenido)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        if self._ficha is None:
            v.addWidget(self._encabezado_vacio(disco_id))
            v.addWidget(_lbl("El disco no existe o fue descartado.", T.font_ui(10), T.TEXT_MUTED))
            v.addStretch()
        else:
            v.addWidget(self._encabezado())
            cuerpo = QHBoxLayout()
            cuerpo.setSpacing(0)
            cuerpo.addWidget(self._col_identidad(), 1)
            cuerpo.addWidget(self._separador())
            cuerpo.addWidget(self._col_dueno(), 1)
            cuerpo.addWidget(self._separador())
            cuerpo.addWidget(self._col_alternativas(), 1)
            v.addLayout(cuerpo, 1)
        self._root.addWidget(self._contenido, 1)

    # --- partes -----------------------------------------------------------------------------------

    def _boton_cerrar(self) -> QPushButton:
        b = QPushButton("×")
        b.setFixedSize(28, 28)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton {{ color: {T.TEXT_PRIMARY}; background: transparent; border: 1px solid {T.BORDER_MID};"
                        f" font-size: 14px; }} QPushButton:hover {{ border-color: {T.YELLOW}; }}")
        b.clicked.connect(self.close)
        return b

    def _encabezado_vacio(self, disco_id: int) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(_lbl(f"#{disco_id:05d}", T.font_display(16, bold=True), T.TEXT_PRIMARY))
        h.addStretch()
        h.addWidget(self._boton_cerrar())
        return w

    def _encabezado(self) -> QWidget:
        d = self._ficha.disco
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        barra = QFrame()
        barra.setFixedSize(4, 30)
        barra.setStyleSheet(f"background: {T.YELLOW}; border: none;")
        h.addWidget(barra)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.addWidget(_caps("Detalle de disco"))
        titulo = QHBoxLayout()
        titulo.setSpacing(8)
        titulo.addWidget(_lbl(f"#{d.id:05d} · {(d.set or 'sin set').upper()}", T.font_display(16, bold=True), T.TEXT_PRIMARY))
        titulo.addWidget(_lbl(f"SLOT {d.slot} · NV {_nivel_txt(d.nivel)}", T.font_display(14), T.TEXT_MUTED))
        titulo.addStretch()
        tv.addLayout(titulo)
        h.addLayout(tv, 1)
        texto, color = TENENCIA_TEXTO["equipada" if d.equipado else "libre"]
        chip = _lbl(f"{texto} · {d.dueno}" if d.dueno else texto, T.font_ui(9, bold=True), color)
        chip.setStyleSheet(f"color: {color}; border: 1px solid {color}; border-radius: 9px; padding: 2px 10px;")
        h.addWidget(chip)
        h.addWidget(self._boton_cerrar())
        return w

    def _separador(self) -> QFrame:
        s = QFrame()
        s.setFixedWidth(1)
        s.setStyleSheet(f"background: {T.BORDER_SUBTLE}; border: none;")
        return s

    def _caja(self, nombre: str, borde: str = T.BORDER_SUBTLE, fondo: str = "rgba(255,255,255,0.02)") -> tuple[QFrame, QVBoxLayout]:
        f = QFrame()
        f.setObjectName(nombre)
        f.setStyleSheet(f"QFrame#{nombre} {{ border: 1px solid {borde}; background: {fondo}; }}")
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)
        return f, v

    def _col_identidad(self) -> QWidget:
        f = self._ficha
        d = f.disco
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 18, 0)
        v.setSpacing(10)

        # Fila de alto FIJO: con las etiquetas de efectos que hacen word-wrap, el layout repartía el
        # alto sobrante y abría un hueco de ~90 px entre el logo y la caja del main.
        fila_ident = QWidget()
        fila_ident.setFixedHeight(68)
        ident = QHBoxLayout(fila_ident)
        ident.setContentsMargins(0, 0, 0, 0)
        ident.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(64, 64)
        logo.setStyleSheet(f"background: {T.BG_BASE}; border: 1px solid {T.BORDER_MID}; border-radius: 12px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = _pixmap(f.set_logo, 52)
        if pm is not None:
            logo.setPixmap(pm)
        ident.setAlignment(Qt.AlignmentFlag.AlignTop)
        ident.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.setAlignment(Qt.AlignmentFlag.AlignTop)
        tv.addWidget(_lbl((d.set or "sin set").upper(), T.font_display(13, bold=True), T.YELLOW))
        # Tres casos, no dos: 15 (completo), nivel bajo (ámbar) y SIN LEER (apagado).
        nivel_color = (T.TEXT_DIM if d.nivel is None
                       else T.TEXT_SECONDARY if d.nivel == 15 else "#F0AA3C")
        nivel_txt = "sin leer" if d.nivel is None else f"Nv {d.nivel}/15"
        tv.addWidget(_lbl(f"Slot {d.slot} · {nivel_txt}", T.font_ui(9), nivel_color))
        tv.addStretch()
        ident.addLayout(tv, 1)
        v.addWidget(fila_ident)

        caja, cv = self._caja("caja_main", T.BORDER_SUBTLE, T.YELLOW_TINT)
        cv.addWidget(_caps("Main"))
        fila = QHBoxLayout()
        fila.addWidget(_lbl(d.main or "—", T.font_ui(11, bold=True), T.TEXT_PRIMARY), 1)
        fila.addWidget(_lbl(formatear_valor(d.main_valor, d.main_unidad), T.font_mono(12), T.YELLOW))
        cv.addLayout(fila)
        v.addWidget(caja)

        caja, cv = self._caja("caja_subs")
        cv.addWidget(_caps(f"Substats · {d.rolls_total} rolls"))
        for nombre, valor, unidad, rolls in d.subs:
            fila = QHBoxLayout()
            fila.setSpacing(8)
            fila.addWidget(_lbl(nombre, T.font_ui(9), T.TEXT_SECONDARY), 1)
            fila.addWidget(_lbl(formatear_valor(valor, unidad), T.font_mono(9), T.TEXT_PRIMARY))
            fila.addWidget(_Rolls(rolls))
            cv.addLayout(fila)
        v.addWidget(caja)

        caja, cv = self._caja("caja_efectos", T.YELLOW_DEEP, "rgba(255,203,5,0.04)")
        cv.addWidget(_caps("Efectos del conjunto", T.YELLOW))
        cv.addWidget(_lbl(f"2pc · {f.bono_2p}" if f.bono_2p else "2pc · sin registro", T.font_ui(8), T.TEXT_SECONDARY, wrap=True))
        cv.addWidget(_lbl(f"4pc · {f.bono_4p}" if f.bono_4p else "4pc · sin registro", T.font_ui(8), T.TEXT_SECONDARY, wrap=True))
        v.addWidget(caja)
        v.addStretch()
        return w

    def _col_dueno(self) -> QWidget:
        f = self._ficha
        d = f.disco
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 0, 18, 0)
        v.setSpacing(10)
        v.addWidget(_caps("Dueño"))
        if d.dueno is None:
            texto, color = TENENCIA_TEXTO["libre"]
            v.addWidget(_lbl(texto, T.font_display(16, bold=True), color))
            v.addWidget(_lbl("sin dueño: no está equipado en ningún PJ", T.font_ui(9), T.TEXT_MUTED, wrap=True))
            v.addStretch()
            return w

        self.boton_dueno = QPushButton(d.dueno)
        self.boton_dueno.setObjectName("dueno")
        self.boton_dueno.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_dueno.setToolTip(f"Abrir la ficha de {d.dueno}")
        pm = _pixmap(f.dueno_avatar, 36)
        if pm is not None:
            self.boton_dueno.setIcon(QIcon(pm))
            self.boton_dueno.setIconSize(QSize(36, 36))
        self.boton_dueno.setFont(T.font_display(12, bold=True))
        self.boton_dueno.setStyleSheet(
            f"QPushButton {{ color: {T.TEXT_PRIMARY}; background: rgba(255,255,255,0.03); text-align: left;"
            f" border: 1px solid {T.YELLOW}; padding: 6px 10px; }}"
            f"QPushButton:hover {{ background: {T.YELLOW_TINT}; }}")
        self.boton_dueno.clicked.connect(lambda: self.pj_pedido.emit(d.dueno_id))
        v.addWidget(self.boton_dueno)

        v.addWidget(_caps(f"Build de {d.dueno} · este disco en el slot {d.slot}"))
        self.hexagono = BuildHexagon(lado=240)
        self.hexagono.set_build(f.build, d.slot, f.dueno_avatar)
        v.addWidget(self.hexagono, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addStretch()
        return w

    def _col_alternativas(self) -> QWidget:
        f = self._ficha
        d = f.disco
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(_caps(f"Otros discos · slot {d.slot} · {d.set or 'sin set'}"))
        if not f.alternativas:
            v.addWidget(_lbl("no hay otros discos de este set en este slot", T.font_ui(9), T.TEXT_MUTED, wrap=True))
        visibles = f.alternativas[:12]
        for a in visibles:
            dueno = a.dueno or TENENCIA_TEXTO["libre"][0]
            b = QPushButton(f"#{a.id:05d}   {a.main or '—'} {formatear_valor(a.main_valor, a.main_unidad)}"
                            f"   Nv {_nivel_txt(a.nivel)}   ·   {dueno}")
            b.setObjectName("alternativa")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(T.font_mono(8))
            color = TENENCIA_TEXTO["libre"][1] if a.libre else T.TEXT_SECONDARY
            b.setStyleSheet(
                f"QPushButton {{ color: {color}; background: transparent; text-align: left;"
                f" border: 1px dashed {T.BORDER_MID}; padding: 5px 8px; }}"
                f"QPushButton:hover {{ border: 1px solid {T.YELLOW}; }}")
            b.clicked.connect(lambda _c=False, i=a.id: self.cargar(i))
            self._alternativas[a.id] = b
            v.addWidget(b)
        if len(f.alternativas) > len(visibles):
            v.addWidget(_lbl(f"+{len(f.alternativas) - len(visibles)} más · filtrá la tabla por set y slot",
                             T.font_ui(8), T.TEXT_MUTED))
        v.addWidget(_lbl("orden: libres primero, después por nivel", T.font_ui(7), T.TEXT_DIM))
        v.addStretch()
        return w

    # --- eventos ------------------------------------------------------------------------------------

    def showEvent(self, ev):
        super().showEvent(ev)
        padre = self.parentWidget()
        if padre is not None:
            centro = padre.mapToGlobal(padre.rect().center())
            self.move(centro.x() - ANCHO // 2, centro.y() - ALTO // 2)

    # --- introspección para tests -------------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        vivos = self._contenido.findChildren(QLabel) if self._contenido else []
        return [l.text() for l in vivos if l.text() and not l.isHidden()]

    def boton_alternativa(self, disco_id: int) -> QPushButton:
        return self._alternativas[disco_id]

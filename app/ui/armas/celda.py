"""La celda de un W-Engine — porta `EngineCell` de `engines-screen.jsx`.

Del diseño se conserva lo que significa algo:

- **el arte manda**: es una tarjeta, no una fila de tabla;
- **franja de rareza** a la izquierda y badge redondo arriba a la derecha;
- **`×n`** cuando hay más copias del mismo modelo;
- **franja de tenencia abajo, con el avatar del dueño** — era la corrección del diseño: la tenencia
  es el dato más caro de esta pantalla y no puede ir en gris de 9 px;
- **refinamiento con mínimo 1**: cinco estrellas vacías se leerían como P0, que no existe. Sin
  lectura va texto, no estrellas.

Lo que cambia respecto del mockup: la **paleta es la de la app** (amarillo sobre negro, decisión de
Daniel 2026-09-15), no el violeta del documento de confirmaciones pasivas; y los colores de tenencia
son los mismos de Discos (`TENENCIA_TEXTO`), así "equipada" significa lo mismo en las dos pantallas.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.armas.datos import FilaArma
from app.ui.live.item_card import TENENCIA_TEXTO

#: Tamaño de diseño de la celda (`EC` en engines-screen.jsx).
CELDA_W, CELDA_H = 120, 116
AMBAR = "#F0AA3C"


def color_rareza(rareza: str | None) -> str:
    return {"S": T.YELLOW, "A": T.PURPLE, "B": T.INFO}.get(rareza or "", T.BORDER_STRONG)


def _lbl(texto: str, font, color: str) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _pixmap(path: str | None, lado: int, redondo: bool = False) -> QPixmap | None:
    if not path or not Path(path).exists():
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    modo = (Qt.AspectRatioMode.KeepAspectRatioByExpanding if redondo
            else Qt.AspectRatioMode.KeepAspectRatio)
    pm = pm.scaled(lado, lado, modo, Qt.TransformationMode.SmoothTransformation)
    if not redondo:
        return pm
    out = QPixmap(lado, lado)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    camino = QPainterPath()
    camino.addEllipse(0, 0, lado, lado)
    p.setClipPath(camino)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


class _BadgeRareza(QWidget):
    """Círculo con la letra. S y A tienen su color; sin dato, gris."""

    def __init__(self, rareza: str | None):
        super().__init__()
        self.rareza = rareza or "?"
        self.escala = 1.0
        self.setFixedSize(17, 17)

    def set_escala(self, s: float) -> None:
        self.escala = s
        self.setFixedSize(round(17 * s), round(17 * s))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(color_rareza(self.rareza))
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(QColor(0, 0, 0, 140))
        p.setPen(QPen(c, 1.5))
        p.drawEllipse(r)
        f = T.font_display(7, bold=True)
        f.setPointSizeF(7 * self.escala)
        p.setFont(f)
        p.setPen(c)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.rareza)
        p.end()


class Refinamiento(QWidget):
    """Cinco estrellas, `refinamiento` llenas. Sólo existe si SE LEYÓ: el mínimo real es 1."""

    def __init__(self, refinamiento: int):
        super().__init__()
        self.refinamiento = refinamiento
        self.escala = 1.0
        self.setFixedSize(5 * 11, 12)
        self.setToolTip(f"Refinamiento P{refinamiento} (el juego lo llama P1–P5)")

    def set_escala(self, s: float) -> None:
        self.escala = s
        self.setFixedSize(round(5 * 11 * s), round(12 * s))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        f = T.font_ui(9)
        f.setPointSizeF(9 * self.escala)
        p.setFont(f)
        paso = 11 * self.escala
        for i in range(5):
            p.setPen(QColor(T.YELLOW) if i < self.refinamiento else QColor(T.BORDER_MID))
            p.drawText(QRectF(i * paso, 0, paso, self.height()),
                       Qt.AlignmentFlag.AlignCenter, "★")
        p.end()


class CeldaArma(QFrame):
    """Una celda clickeable. `clicked(inventory_id)` · `dueno_pedido(agente_id)`."""

    clicked = Signal(int)
    dueno_pedido = Signal(int)

    def __init__(self, fila: FilaArma, parent: QWidget | None = None):
        super().__init__(parent)
        self.fila = fila
        self.seleccionada = False
        self.boton_dueno: QPushButton | None = None
        self._escala_contenido = 1.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("celda_arma")
        self._pintar_borde()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 0)
        raiz.setSpacing(1)

        # Copias y rareza van SUPERPUESTAS en las esquinas (se ubican en `resizeEvent`), no en una
        # fila propia: con 56 celdas en la ventana mínima la celda baja a ~90 px de alto, y esa fila
        # le robaba el lugar al pie con el refinamiento — que es un dato, no un adorno.
        self._copias = _lbl(f"×{fila.copias}", T.font_mono(7), T.BG_BASE)
        self._copias.setParent(self)
        self._copias.setStyleSheet(f"color: {T.BG_BASE}; background: {T.YELLOW_SOFT}; padding: 0 3px;")
        self._copias.setToolTip(f"{fila.copias} copias de {fila.nombre} en el inventario")
        self._copias.setVisible(fila.copias > 1)
        self._badge = _BadgeRareza(fila.rareza)
        self._badge.setParent(self)

        # ícono
        self._icono = QLabel()
        self._icono.setFixedSize(44, 44)
        self._icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icono.setStyleSheet("background: transparent; border: none;")
        self._poner_icono(44)
        raiz.addWidget(self._icono, 0, Qt.AlignmentFlag.AlignHCenter)

        # nombre
        self._nombre = _lbl(fila.nombre, T.font_display(8, bold=True), T.TEXT_PRIMARY)
        self._nombre.setWordWrap(True)
        self._nombre_una_linea = False
        self._nombre.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._nombre.setToolTip(fila.nombre)
        raiz.addWidget(self._nombre, 1)

        # pie: refinamiento · nivel
        pie = QHBoxLayout()
        pie.setContentsMargins(0, 0, 0, 2)
        pie.setSpacing(4)
        self._refin: Refinamiento | None = None
        if fila.refinamiento is None:
            self._refin_sin_leer = _lbl("P sin leer", T.font_caps(6, bold=True), AMBAR)
            pie.addWidget(self._refin_sin_leer)
        else:
            self._refin_sin_leer = None
            self._refin = Refinamiento(fila.refinamiento)
            pie.addWidget(self._refin)
        pie.addStretch()
        if fila.nivel is None:
            self._nivel = _lbl("Nv sin leer", T.font_caps(6, bold=True), AMBAR)
        else:
            color = T.TEXT_SECONDARY if fila.nivel == 60 else AMBAR
            self._nivel = _lbl(f"Nv {fila.nivel}", T.font_mono(7), color)
        pie.addWidget(self._nivel)
        raiz.addLayout(pie)

        # franja de tenencia
        texto, color = TENENCIA_TEXTO["equipada" if fila.equipado else "libre"]
        franja = QFrame()
        self._franja = franja
        franja.setObjectName("franja")
        franja.setFixedHeight(19)
        franja.setStyleSheet(
            f"QFrame#franja {{ background: rgba(255,255,255,0.03); border: none;"
            f" border-top: 1px solid {color}; }}")
        fl = QHBoxLayout(franja)
        fl.setContentsMargins(5, 0, 5, 0)
        fl.setSpacing(4)
        if fila.equipado and fila.dueno:
            self.boton_dueno = QPushButton(fila.dueno)
            self.boton_dueno.setObjectName("dueno")
            self.boton_dueno.setCursor(Qt.CursorShape.PointingHandCursor)
            self.boton_dueno.setFont(T.font_caps(6, bold=True))
            self.boton_dueno.setToolTip(f"Abrir la ficha de {fila.dueno}")
            pm = _pixmap(fila.dueno_avatar, 14, redondo=True)
            if pm is not None:
                self.boton_dueno.setIcon(QIcon(pm))
                self.boton_dueno.setIconSize(QSize(14, 14))
            self.boton_dueno.setStyleSheet(
                f"QPushButton {{ color: {color}; background: transparent; border: none;"
                f" text-align: left; padding: 0; }}"
                f"QPushButton:hover {{ color: {T.TEXT_PRIMARY}; }}")
            self.boton_dueno.clicked.connect(lambda: self.dueno_pedido.emit(fila.dueno_id))
            fl.addWidget(self.boton_dueno, 1)
        else:
            self._tenencia = _lbl(texto, T.font_caps(6, bold=True), color)
            fl.addWidget(self._tenencia, 1)
        raiz.addWidget(franja)

        pendientes = []
        if not fila.icono:
            pendientes.append("sin archivo de ícono")
        if not fila.especialidad:
            pendientes.append("sin especialidad en el catálogo")
        if pendientes:
            self.setToolTip(f"{fila.nombre} — " + " · ".join(pendientes))

        self._fuentes = [(self._nombre, 8), (self._nivel, 7 if fila.nivel is not None else 6),
                         (self._copias, 7)]
        if self.boton_dueno is not None:
            self._fuentes.append((self.boton_dueno, 6))
        if self._refin_sin_leer is not None:
            self._fuentes.append((self._refin_sin_leer, 6))
        if self.boton_dueno is None:
            self._fuentes.append((self._tenencia, 6))

    # --- estado ---------------------------------------------------------------------------------

    def _pintar_borde(self) -> None:
        borde = T.YELLOW if self.seleccionada else T.BORDER_MID
        fondo = T.YELLOW_TINT if self.seleccionada else T.BG_PANEL
        self.setStyleSheet(
            f"QFrame#celda_arma {{ background: {fondo}; border: 1px solid {borde}; }}"
            f"QFrame#celda_arma:hover {{ border: 1px solid {T.YELLOW_SOFT}; }}")

    def set_seleccion(self, on: bool) -> None:
        self.seleccionada = on
        self._pintar_borde()

    def _poner_icono(self, lado: int) -> None:
        pm = _pixmap(self.fila.icono, lado)
        if pm is not None:
            self._icono.setPixmap(pm)
        else:
            self._icono.setPixmap(QPixmap())
            self._icono.setText("—")
            self._icono.setStyleSheet(
                f"color: {T.TEXT_DIM}; background: transparent; border: 1px dashed {T.BORDER_MID};")

    def set_escala(self, escala: float) -> None:
        """El pie (refinamiento y nivel) NUNCA se esconde: es dato. Achicada, el ícono se achica y el
        nombre pasa a una línea recortada (con tooltip); agrandada, crece todo como en el Roster."""
        chica = escala < 1.0
        if chica != self._nombre_una_linea:
            self._nombre_una_linea = chica
            self._nombre.setWordWrap(not chica)
            self._ajustar_nombre()
        if chica:
            lado = max(24, round(44 * escala))
            if self._icono.width() != lado:
                self._icono.setFixedSize(lado, lado)
                self._poner_icono(lado)
        s = round(max(1.0, escala), 2)
        if s == self._escala_contenido:
            return
        if s == 1.0 and not chica:
            self._icono.setFixedSize(44, 44)
            self._poner_icono(44)
        self._escala_contenido = s
        for lbl, base in self._fuentes:
            f = lbl.font()
            f.setPointSizeF(base * s)
            lbl.setFont(f)
        lado = round(44 * s)
        self._icono.setFixedSize(lado, lado)
        self._poner_icono(lado)
        self._badge.set_escala(s)
        if self._refin is not None:
            self._refin.set_escala(s)
        self._franja.setFixedHeight(round(19 * s))
        if self.boton_dueno is not None:
            lado_av = round(14 * s)
            pm = _pixmap(self.fila.dueno_avatar, lado_av, redondo=True)
            if pm is not None:
                self.boton_dueno.setIcon(QIcon(pm))
                self.boton_dueno.setIconSize(QSize(lado_av, lado_av))
        self._copias.adjustSize()

    def escala_contenido(self) -> float:
        return self._escala_contenido

    def _ajustar_nombre(self) -> None:
        if self._nombre_una_linea:
            ancho = max(10, self.width() - 12)
            self._nombre.setText(self._nombre.fontMetrics().elidedText(
                self.fila.nombre, Qt.TextElideMode.ElideRight, ancho))
        else:
            self._nombre.setText(self.fila.nombre)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        m = round(4 * self._escala_contenido)
        extra = 10 if (not self.fila.icono or not self.fila.especialidad) else 0
        self._badge.move(self.width() - self._badge.width() - m - extra, m)
        self._copias.adjustSize()
        self._copias.move(m + 3, m)
        self._badge.raise_()
        self._copias.raise_()
        self._ajustar_nombre()

    # --- introspección para tests -----------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        textos = [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]
        if self._nombre.text() != self.fila.nombre:
            textos.append(self.fila.nombre)        # el nombre recortado sigue siendo este
        if self.boton_dueno is not None:
            textos.append(self.boton_dueno.text())
        return textos

    # --- eventos --------------------------------------------------------------------------------

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit(self.fila.id)
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        # franja de rareza a la izquierda
        p.fillRect(QRectF(0, 0, 3, self.height()), QColor(color_rareza(self.fila.rareza)))
        # esquina rayada ámbar cuando falta un dato del catálogo
        if not self.fila.icono or not self.fila.especialidad:
            lado = round(13 * self._escala_contenido)
            w = self.width()
            tri = QPainterPath()
            tri.moveTo(QPointF(w - lado, 0))
            tri.lineTo(QPointF(w, 0))
            tri.lineTo(QPointF(w, lado))
            tri.closeSubpath()
            p.setClipPath(tri)
            p.fillPath(tri, QColor(AMBAR + "33"))
            p.setPen(QPen(QColor(AMBAR), 1.2))
            for k in range(-lado, lado * 2, 4):
                p.drawLine(QPointF(w - lado + k, 0), QPointF(w + k, lado))
        p.end()

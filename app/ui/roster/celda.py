"""La celda de un PJ en la pantalla Roster.

Recibe una `CeldaPJ` ya calculada (`datos.py`) y la pinta; no consulta nada. Tamaño de diseño
122×96, escalado por `set_escala` para que la grilla entre entera sin scroll.

Marcas (README del diseño v1, §2), cada una con su significado y nada más:

- **esquina rayada ámbar** → le faltan datos (sin umbrales). Pintada en `paintEvent`.
- **`∞`** → cápsula MACIZA con halo naranja; S y A son un círculo HUECO. No es "una S con adorno".
- **nivel** → "sin leer" en gris si no se capturó; teñido ámbar sólo si no es 60 (42 de 51 estaban
  en 60 cuando se diseñó: pintar el caso normal es ruido).
- **discos** → seis casilleros; por encima de 6, `+n` (la grilla no se estira por una excepción).
- **atuendo** → borde punteado violeta + `ATUENDO · <base>`.

Lo web-only del diseño (chamfers por `clip-path`, glows compuestos) no se porta.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core.asset_resolver import agent_avatar_path, faction_logo_path
from app.ui import tokens as T
from app.ui.roster.datos import CeldaPJ

AMBAR = "#F0AA3C"       # "le faltan datos" — mismo ámbar que el editor de roster
VIOLETA = "#B06FF0"     # atuendo — el violeta del editor
NARANJA_INF = "#FF8A3D" # rango ∞


def _lbl(texto: str, font, color: str) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _pixmap(path: Path | None, lado: int, redondo: bool = False) -> QPixmap | None:
    if path is None or not Path(path).exists():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    pm = pm.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
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


class _Rango(QWidget):
    """S/A: círculo hueco. ∞: cápsula maciza con halo."""

    def __init__(self, rango: str | None):
        super().__init__()
        self.rango = rango or "?"
        self.escala = 1.0
        self.setFixedSize(26, 16)

    def set_escala(self, s: float) -> None:
        self.escala = s
        self.setFixedSize(round(26 * s), round(16 * s))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.rango == "∞":
            p.setPen(QPen(QColor(NARANJA_INF + "66"), 3))
            p.setBrush(QBrush(QColor(NARANJA_INF)))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setPen(QColor(T.BG_BASE))
        else:
            color = T.YELLOW if self.rango == "S" else T.PURPLE
            lado = r.height()
            circ = QRectF(r.right() - lado, r.top(), lado, lado)
            p.setPen(QPen(QColor(color), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(circ)
            r = circ
            p.setPen(QColor(color))
        f = T.font_display(7, bold=True)
        f.setPointSizeF(7 * self.escala)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.rango)
        p.end()


class _Discos(QWidget):
    """Seis casilleros; lo que pasa de 6 va como `+n`."""

    def __init__(self, n: int):
        super().__init__()
        self.n = n
        self.escala = 1.0
        # Tamaño FIJO explícito: sin sizeHint el layout le daba 0 px de ancho y los casilleros no
        # se veían (pasó en la primera captura, con los tests en verde porque miraban textos).
        self.setFixedSize(6 * 8 + (16 if n > 6 else 0), 8)

    def set_escala(self, s: float) -> None:
        self.escala = s
        self.setFixedSize(round((6 * 8 + (16 if self.n > 6 else 0)) * s), round(8 * s))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        s = self.escala
        lado, gap = 6 * s, 2 * s
        for i in range(6):
            x = i * (lado + gap)
            lleno = i < self.n
            p.setPen(QColor(T.BORDER_STRONG if not lleno else T.YELLOW))
            p.setBrush(QColor(T.YELLOW) if lleno else Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x, s, lado - 1, lado - 1))
        if self.n > 6:
            p.setPen(QColor(T.YELLOW))
            f = T.font_mono(6)
            f.setPointSizeF(6 * s)
            p.setFont(f)
            p.drawText(QPointF(6 * (lado + gap) + 1, 8 * s), f"+{self.n - 6}")
        p.end()


class CeldaRoster(QFrame):
    """Una celda clickeable. `clicked(agente_id)`."""

    clicked = Signal(int)

    def __init__(self, celda: CeldaPJ, parent: QWidget | None = None):
        super().__init__(parent)
        self.celda = celda
        self.marca_faltan_datos = celda.sin_thresholds
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("celda_roster")
        acento = T.color_elemento(celda.elemento)
        if celda.variante_de:
            borde = f"1px dashed {VIOLETA}"
        else:
            borde = f"1px solid {T.BORDER_SUBTLE}"
        self.setStyleSheet(
            f"QFrame#celda_roster {{ background: {T.BG_PANEL}; border: {borde}; }}"
            f"QFrame#celda_roster:hover {{ border: 1px solid {acento}; }}"
        )

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 5, 6, 5)
        v.setSpacing(2)

        # fila 1: facción · rango
        fila1 = QHBoxLayout()
        fila1.setSpacing(4)
        self._faccion = QLabel()
        self._faccion.setFixedSize(16, 16)
        self._faccion.setStyleSheet("background: transparent; border: none;")
        pm = _pixmap(faction_logo_path(celda.faccion), 16)
        if pm is not None:
            self._faccion.setPixmap(pm)
        self._faccion.setToolTip(celda.faccion or "")
        fila1.addWidget(self._faccion)
        fila1.addStretch()
        self._rango = _Rango(celda.rango)
        fila1.addWidget(self._rango)
        if celda.sin_thresholds:
            fila1.addSpacing(9)       # que la esquina rayada no tape el rango
        v.addLayout(fila1)

        # fila 2: avatar + nombre
        fila2 = QHBoxLayout()
        fila2.setSpacing(5)
        self._avatar = QLabel()
        self._avatar.setFixedSize(28, 28)
        self._avatar.setStyleSheet("background: transparent; border: none;")
        pm = _pixmap(agent_avatar_path(celda.nombre, "ico"), 28, redondo=True)
        if pm is not None:
            self._avatar.setPixmap(pm)
        fila2.addWidget(self._avatar)
        self._nombre = _lbl(celda.nombre, T.font_display(8, bold=True), T.TEXT_PRIMARY)
        self._nombre.setWordWrap(True)
        fila2.addWidget(self._nombre, 1)
        v.addLayout(fila2)

        # fila 3: atuendo, o elemento · rol
        if celda.variante_de:
            self._detalle = _lbl(f"ATUENDO · {celda.variante_de}", T.font_caps(6, bold=True), VIOLETA)
        else:
            self._detalle = _lbl(f"{celda.elemento or '—'} · {celda.rol or '—'}",
                                 T.font_ui(7), acento)
        v.addWidget(self._detalle)

        # fila 4: nivel · discos
        fila4 = QHBoxLayout()
        fila4.setSpacing(4)
        if celda.nivel is None:
            self._nivel = _lbl("sin leer", T.font_ui(7), T.TEXT_MUTED)
            self._nivel.setToolTip("Nivel no capturado todavía: se lee en la pantalla de atributos del PJ.")
        else:
            color = T.TEXT_SECONDARY if celda.nivel == 60 else AMBAR
            self._nivel = _lbl(f"Nv {celda.nivel}", T.font_mono(7), color)
        fila4.addWidget(self._nivel)
        fila4.addStretch()
        self._discos = _Discos(celda.discos)
        fila4.addWidget(self._discos)
        v.addLayout(fila4)

        self._escala_contenido = 1.0
        #: (label, tamaño base en pt) — lo que crece cuando la celda crece.
        self._fuentes = [(self._nombre, 8), (self._detalle, 6 if celda.variante_de else 7),
                         (self._nivel, 7)]
        if celda.sin_thresholds:
            self.setToolTip("Le faltan datos: sin umbrales (agent_thresholds) — onboarding a medias.")

    # --- escala ---------------------------------------------------------------------------------

    def set_escala(self, escala: float) -> None:
        """Achicada: debajo de 0.8 se esconde la línea de detalle y debajo de 0.7 el avatar — el
        nombre y el rango tienen prioridad. Agrandada (ventana maximizada): el CONTENIDO crece con la
        celda; si sólo creciera el recuadro, quedarían celdas grandes con el texto chico adentro."""
        self._detalle.setVisible(escala >= 0.8)
        self._avatar.setVisible(escala >= 0.7)
        s = round(max(1.0, escala), 2)
        if s == self._escala_contenido:
            return
        self._escala_contenido = s
        for lbl, base in self._fuentes:
            f = lbl.font()
            f.setPointSizeF(base * s)
            lbl.setFont(f)
        lado_av, lado_fac = round(28 * s), round(16 * s)
        self._avatar.setFixedSize(lado_av, lado_av)
        pm = _pixmap(agent_avatar_path(self.celda.nombre, "ico"), lado_av, redondo=True)
        if pm is not None:
            self._avatar.setPixmap(pm)
        self._faccion.setFixedSize(lado_fac, lado_fac)
        pm = _pixmap(faction_logo_path(self.celda.faccion), lado_fac)
        if pm is not None:
            self._faccion.setPixmap(pm)
        self._rango.set_escala(s)
        self._discos.set_escala(s)

    def escala_contenido(self) -> float:
        return self._escala_contenido

    # --- introspección para tests -----------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        return [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]

    # --- eventos --------------------------------------------------------------------------------

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit(self.celda.id)
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self.marca_faltan_datos:
            return
        # Esquina rayada ámbar, arriba a la derecha, 13 px.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, lado = self.width(), round(13 * self._escala_contenido)   # int: `range` abajo
        tri = QPainterPath()
        tri.moveTo(QPointF(w - lado, 0))
        tri.lineTo(QPointF(w, 0))
        tri.lineTo(QPointF(w, lado))
        tri.closeSubpath()
        p.setClipPath(tri)
        p.fillPath(tri, QColor(AMBAR + "40"))
        p.setPen(QPen(QColor(AMBAR), 1.5))
        for k in range(-lado, lado * 2, 4):
            p.drawLine(QPointF(w - lado + k, 0), QPointF(w + k, lado))
        p.end()

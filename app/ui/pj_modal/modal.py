"""El modal de PJ — 1000×640, sin marco, centrado sobre la ventana.

Recibe una `FichaPJ` ya armada y la pinta; no consulta nada (se testea sin DB).

Del mockup se porta lo que informa y se deja lo que recomienda:

| mockup | acá |
|---|---|
| portada con arte + degradado de la paleta del PJ | igual, pero el color **sale del elemento** (decisión de Daniel) |
| "BUILD COMPLETION 87%" | **no**: sale del scoring sin calibrar |
| stats con barra y marca amarilla al 75 % | barra sí; **la marca no** — es un umbral inventado. `None` → "sin leer", sin barra |
| hexágono + sets | `BuildHexagon` de la vista en vivo (orden de slots del JUEGO) + filas de set |
| W-Engine con R1–R5 | P1–P5, que es como lo llama el juego |
| despertar "4/6 · próximo nodo desbloquea…" | el nivel sí; **la frase no** (no hay de dónde sacarla) |
| 4 botones de acción | **no** |
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui import tokens as T
from app.ui.live.hexagon import BuildHexagon
from app.ui.pj_modal.datos import STATS, FichaPJ

ANCHO, ALTO = 1000, 640
HERO_H = 200

#: Escala VISUAL de las barras, la misma del mockup (`pct = valor / divisor`). No es un umbral ni
#: un objetivo: sólo decide cuánto se llena la barra.
_ESCALA_BARRA = {"pv": 200, "ataque": 30, "defensa": 14, "impacto": 2, "prob_critico": 1,
                 "dano_critico": 2, "maestria_anomalia": 5, "rec_energia": 0.02}


def _lbl(texto: str, font, color: str, wrap: bool = False) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setWordWrap(wrap)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _pixmap(path: str | None) -> QPixmap | None:
    if not path or not Path(path).exists():
        return None
    pm = QPixmap(path)
    return None if pm.isNull() else pm


def _caps(texto: str, color: str) -> QLabel:
    return _lbl(texto, T.font_caps(8, bold=True), color)


class _Hero(QWidget):
    """Degradado del acento + arte extendido a la derecha. Los textos van como hijos."""

    def __init__(self, ficha: FichaPJ, acento: str):
        super().__init__()
        self.setFixedHeight(HERO_H)
        self._acento = acento
        self._arte = _pixmap(ficha.arte)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect()
        g = QLinearGradient(0, 0, r.width(), r.height())
        base = QColor(self._acento)
        g.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 200))
        medio = base.darker(260)
        g.setColorAt(0.5, medio)
        g.setColorAt(1.0, QColor(T.BG_BASE))
        p.fillRect(r, g)
        if self._arte is not None:
            alto = 320
            pm = self._arte.scaledToHeight(alto, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(r.width() - pm.width() - 30, -40, pm)
        sombra = QLinearGradient(0, 0, 0, r.height())
        sombra.setColorAt(0.4, QColor(0, 0, 0, 0))
        sombra.setColorAt(1.0, QColor(10, 10, 10, 160))
        p.fillRect(r, sombra)
        p.end()


class _Gauge(QWidget):
    def __init__(self, etiqueta: str, texto: str | None, crudo, divisor: float, acento: str):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 6)
        v.setSpacing(3)
        fila = QHBoxLayout()
        self.etiqueta = _lbl(etiqueta, T.font_ui(9), T.TEXT_SECONDARY)
        if texto is None:
            self.valor = _lbl("sin leer", T.font_ui(9), T.TEXT_MUTED)
            self.valor.setToolTip("Sin capturar: se lee al abrir los atributos del PJ en el juego.")
        else:
            self.valor = _lbl(texto, T.font_mono(10), T.TEXT_PRIMARY)
        fila.addWidget(self.etiqueta, 1)
        fila.addWidget(self.valor)
        v.addLayout(fila)
        self._pct = None if crudo is None else max(0.0, min(1.0, float(crudo) / divisor / 100))
        self._acento = acento
        self._barra = QWidget()
        self._barra.setFixedHeight(4)
        v.addWidget(self._barra)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._pct is None:
            return
        p = QPainter(self)
        g = self._barra.geometry()
        p.fillRect(g, QColor(255, 255, 255, 13))
        lleno = QRectF(g.x(), g.y(), g.width() * self._pct, g.height())
        c = QColor(self._acento)
        c.setAlpha(170)
        p.fillRect(lleno, c)
        p.end()


class PjModal(QDialog):
    def __init__(self, ficha: FichaPJ, parent: QWidget | None = None):
        super().__init__(parent)
        self.ficha = ficha
        self.acento = T.color_elemento(ficha.elemento)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(ANCHO, ALTO)
        self._stats: dict[str, QLabel] = {}

        marco = QFrame(self)
        marco.setObjectName("pj_modal")
        marco.setGeometry(0, 0, ANCHO, ALTO)
        marco.setStyleSheet(f"QFrame#pj_modal {{ background: {T.BG_PANEL}; border: 2px solid {self.acento}; }}")
        root = QVBoxLayout(marco)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)
        root.addWidget(self._portada())

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._col_stats(), 1)
        cuerpo.addWidget(self._separador())
        cuerpo.addWidget(self._col_build(), 0)
        cuerpo.addWidget(self._separador())
        cuerpo.addWidget(self._col_arma(), 1)
        root.addLayout(cuerpo, 1)

    # --- portada ----------------------------------------------------------------------------------

    def _portada(self) -> QWidget:
        f = self.ficha
        hero = _Hero(f, self.acento)

        self.btn_cerrar = QPushButton("×", hero)
        self.btn_cerrar.setFixedSize(28, 28)
        self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar.setStyleSheet(
            f"QPushButton {{ color: {T.TEXT_PRIMARY}; background: rgba(0,0,0,0.6);"
            f" border: 1px solid {self.acento}; font-size: 14px; }}"
            f"QPushButton:hover {{ background: {self.acento}; color: {T.BG_BASE}; }}")
        self.btn_cerrar.move(ANCHO - 4 - 14 - 28, 14)
        self.btn_cerrar.clicked.connect(self.close)

        ident = QWidget(hero)
        h = QHBoxLayout(ident)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        avatar = QLabel()
        avatar.setFixedSize(96, 96)
        avatar.setStyleSheet(f"background: {T.BG_BASE}; border: 2px solid {self.acento}; border-radius: 16px;")
        pm = _pixmap(f.avatar)
        if pm is not None:
            avatar.setPixmap(self._redondeado(pm, 92, 14))
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignBottom)

        v = QVBoxLayout()
        v.setSpacing(4)
        fila_fac = QHBoxLayout()
        fila_fac.setSpacing(8)
        logo = QLabel()
        logo.setStyleSheet("background: transparent; border: none;")
        pm = _pixmap(f.faccion_logo)
        if pm is not None:
            logo.setPixmap(pm.scaledToHeight(22, Qt.TransformationMode.SmoothTransformation))
            fila_fac.addWidget(logo)
        fila_fac.addWidget(_caps(f.faccion or "facción sin registro", "rgba(255,255,255,0.8)"))
        fila_fac.addStretch()
        v.addLayout(fila_fac)
        nombre = _lbl(f.nombre, T.font_display(30, bold=True), "#ffffff")
        fn = nombre.font()
        fn.setItalic(True)
        nombre.setFont(fn)
        v.addWidget(nombre)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for texto, color, macizo in ((f.elemento or "—", self.acento, False),
                                     (f.rol or "—", self.acento, False),
                                     (f"M{f.mindscape}" if f.mindscape is not None else "M?", self.acento, True)):
            c = _lbl(texto.upper(), T.font_ui(9, bold=True), T.BG_BASE if macizo else color)
            c.setStyleSheet(
                f"color: {T.BG_BASE if macizo else color}; padding: 3px 10px;"
                f" background: {color if macizo else 'rgba(0,0,0,0.5)'}; border: 1px solid {color};")
            chips.addWidget(c)
        chips.addStretch()
        v.addLayout(chips)
        h.addLayout(v)
        ident.adjustSize()
        ident.setGeometry(24, HERO_H - 18 - 110, 560, 110)
        return hero

    @staticmethod
    def _redondeado(pm: QPixmap, lado: int, radio: int) -> QPixmap:
        pm = pm.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        out = QPixmap(lado, lado)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        camino = QPainterPath()
        camino.addRoundedRect(0, 0, lado, lado, radio, radio)
        p.setClipPath(camino)
        p.drawPixmap(0, 0, pm)
        p.end()
        return out

    # --- columnas ---------------------------------------------------------------------------------

    def _separador(self) -> QFrame:
        s = QFrame()
        s.setFixedWidth(1)
        s.setStyleSheet(f"background: {T.BORDER_SUBTLE}; border: none;")
        return s

    def _col_stats(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(4)
        v.addWidget(_caps("Stats combate", self.acento))
        crudos = self.ficha.stats_crudos
        for (etiqueta, texto), (_e, col) in zip(self.ficha.stats, STATS, strict=True):
            g = _Gauge(etiqueta, texto, crudos.get(col), _ESCALA_BARRA.get(col, 1), self.acento)
            self._stats[etiqueta] = g.valor
            v.addWidget(g)
        v.addStretch()
        return w

    def _col_build(self) -> QWidget:
        f = self.ficha
        w = QWidget()
        w.setFixedWidth(280)
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 14, 12, 14)
        v.setSpacing(8)
        v.addWidget(_caps("Build · 6 slots", self.acento))
        hexa = BuildHexagon(lado=220)
        hexa.set_build(f.slots, None, f.avatar)
        v.addWidget(hexa, 0, Qt.AlignmentFlag.AlignHCenter)
        if not f.slots:
            v.addWidget(_lbl("sin discos equipados", T.font_ui(9), T.TEXT_MUTED))
        for nombre, piezas in f.sets:
            fila = QFrame()
            fila.setStyleSheet(f"QFrame {{ border: 1px solid {T.BORDER_SUBTLE}; background: rgba(255,255,255,0.02); }}")
            h = QHBoxLayout(fila)
            h.setContentsMargins(8, 5, 8, 5)
            logo = QLabel()
            logo.setFixedSize(22, 22)
            logo.setStyleSheet("border: none; background: transparent;")
            pm = _pixmap(f.set_logos.get(nombre))
            if pm is not None:
                logo.setPixmap(pm.scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
            h.addWidget(logo)
            tv = QVBoxLayout()
            tv.setSpacing(0)
            tv.addWidget(_lbl(nombre, T.font_ui(9, bold=True), T.TEXT_PRIMARY))
            tv.addWidget(_lbl(f"{piezas} PIEZAS", T.font_caps(7), T.TEXT_MUTED))
            h.addLayout(tv, 1)
            v.addWidget(fila)
        v.addStretch()
        return w

    def _col_arma(self) -> QWidget:
        f = self.ficha
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        v.addWidget(_caps("W-Engine", self.acento))
        caja = QFrame()
        caja.setObjectName("caja_arma")
        caja.setStyleSheet(f"QFrame#caja_arma {{ border: 1px solid {self.acento}; background: rgba(255,255,255,0.03); }}")
        h = QHBoxLayout(caja)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(12)
        if f.arma is None:
            h.addWidget(_lbl("sin arma equipada", T.font_ui(10), T.TEXT_MUTED))
        else:
            ico = QLabel()
            ico.setFixedSize(56, 56)
            ico.setStyleSheet("border: none; background: transparent;")
            pm = _pixmap(f.arma.icono)
            if pm is not None:
                ico.setPixmap(pm.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            h.addWidget(ico)
            tv = QVBoxLayout()
            tv.setSpacing(4)
            tv.addWidget(_lbl(f.arma.nombre, T.font_display(12, bold=True), T.TEXT_PRIMARY))
            ref = f.arma.refinamiento
            nivel = f"Nv {f.arma.nivel}" if f.arma.nivel is not None else "Nv sin leer"
            tv.addWidget(_lbl(f"{nivel}  ·  P{ref}" if ref else f"{nivel}  ·  P sin leer",
                              T.font_mono(9), self.acento))
            barras = QHBoxLayout()
            barras.setSpacing(4)
            for i in range(5):
                b = QFrame()
                b.setFixedSize(16, 4)
                lleno = ref is not None and i < ref
                b.setStyleSheet(f"background: {self.acento if lleno else 'rgba(255,255,255,0.1)'}; border: none;")
                barras.addWidget(b)
            barras.addStretch()
            tv.addLayout(barras)
            h.addLayout(tv, 1)
        v.addWidget(caja)

        bono = QFrame()
        bono.setObjectName("caja_bono")
        bono.setStyleSheet(f"QFrame#caja_bono {{ border: 1px solid {T.BORDER_SUBTLE}; background: rgba(255,255,255,0.02); }}")
        bv = QVBoxLayout(bono)
        bv.setContentsMargins(12, 10, 12, 10)
        bv.addWidget(_caps("Bonus elemental", T.TEXT_MUTED))
        if f.bono is None:
            bv.addWidget(_lbl("sin leer", T.font_ui(10), T.TEXT_MUTED))
        else:
            bv.addWidget(_lbl(f.bono, T.font_ui(10, bold=True), self.acento))
        v.addWidget(bono)

        v.addWidget(_caps("Despertar", self.acento))
        if f.despertar is None:
            v.addWidget(_lbl("sin registro", T.font_ui(9), T.TEXT_MUTED))
        else:
            grid = QGridLayout()
            grid.setSpacing(4)
            for i in range(6):
                activo = i < f.despertar
                c = _lbl(f"nv{i + 1}", T.font_mono(8), self.acento if activo else T.TEXT_MUTED)
                c.setAlignment(Qt.AlignmentFlag.AlignCenter)
                c.setFixedHeight(22)
                c.setStyleSheet(
                    f"color: {self.acento if activo else T.TEXT_MUTED};"
                    f" border: 1px solid {self.acento if activo else T.BORDER_MID};"
                    f" background: {'rgba(255,255,255,0.06)' if activo else 'transparent'};")
                grid.addWidget(c, 0, i)
            v.addLayout(grid)
            texto = f"Nivel {f.despertar}/6"
            if f.despertar_nombre:
                texto += f" · {f.despertar_nombre}"
            v.addWidget(_lbl(texto, T.font_ui(9), T.TEXT_SECONDARY, wrap=True))
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
        return [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]

    def textos_de_stats(self) -> dict[str, str]:
        return {k: lbl.text() for k, lbl in self._stats.items()}

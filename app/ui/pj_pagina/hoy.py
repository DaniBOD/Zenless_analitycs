"""Lo que el PJ tiene HOY en el juego, para la página del PJ (SPEC 2026-09-28).

Portado sin cambios de `app/ui/pj_modal/modal.py` (el modal se retiró): el hero, las barras de stats
y el selector de prioridad. Cambia sólo el armado. La portada es ancha, sin la ×, porque se vuelve
con "←". Las columnas del modal (stats | build | arma) pasan a dos: stats con arma, bonus y
despertar debajo, y el hexágono con sus sets, porque la otra mitad de la página es la build
declarada.

Del mockup se porta lo que informa y se deja lo que recomienda (decisiones de Daniel 2026-09-13):
ni "build completion", ni la marca del 75 %, ni la frase del próximo nodo del despertar, ni
botones de acción. El color sale del elemento.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import tokens as T
from app.ui.live.hexagon import BuildHexagon
from app.ui.pj_modal.datos import FichaPJ, stats_de_rol
from app.ui.roster.celda import AMBAR as AMBAR_AVISO

HERO_H = 200

#: Escala VISUAL de las barras, la misma del mockup (`pct = valor / divisor`). No es un umbral ni
#: un objetivo: sólo decide cuánto se llena la barra.
_ESCALA_BARRA = {"pv": 200, "ataque": 30, "defensa": 14, "impacto": 2, "prob_critico": 1,
                 "dano_critico": 2, "maestria_anomalia": 5, "rec_energia": 0.02,
                 "dano_laceracion": 2, "acumulacion_afiladura": 0.02}


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


#: La nota del selector: qué IMPLICA cada valor (handoff design_v3). Sin toast al cambiar.
PRIO_NOTA = {
    "alta": "Recibe discos primero · nadie de menor prioridad se los saca",
    "normal": "Por defecto · se mueve sólo si quien lo tiene no pierde",
    "baja": "Cede discos a PJs de prioridad mayor",
}


class _SelectorPrioridad(QFrame):
    """Prioridad de buildeo en la ficha del PJ (handoff design_v3): 262 px sobre el hero, a la
    izquierda de la cruz. Guarda al click con `EditorPrioridades` — una sesión por ficha abierta,
    así que un backup por ficha, no por click (RNF-01)."""

    cambiada = Signal(str)
    ANCHO = 262

    def __init__(self, agente_id: int, nombre: str, valor: str, db_path=None, parent=None):
        super().__init__(parent)
        from app.core.prioridad import EditorPrioridades
        from app.db.connection import is_readonly
        self._id, self._nombre, self.valor = agente_id, nombre, valor
        self._editor = EditorPrioridades(db_path)
        self.setObjectName("selector_prioridad")
        self.setFixedWidth(self.ANCHO)
        self.setStyleSheet("QFrame#selector_prioridad { background: rgba(14,12,18,0.8);"
                           " border: 1px solid rgba(255,255,255,0.16); }")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 9)
        v.setSpacing(6)
        titulo = QLabel("PRIORIDAD DE BUILDEO")
        titulo.setFont(T.font_caps(7, bold=True))
        titulo.setStyleSheet("color: rgba(255,255,255,0.72); background: transparent; border: none;")
        v.addWidget(titulo)
        fila = QHBoxLayout()
        fila.setSpacing(3)
        self.botones: dict[str, QPushButton] = {}
        for clave, texto in (("alta", "▲ Alta"), ("normal", "Normal"), ("baja", "▼ Baja")):
            b = QPushButton(texto)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setFont(T.font_caps(8, bold=True))
            b.setStyleSheet(self._css(clave))
            b.clicked.connect(lambda _c=False, k=clave: self._elegir(k))
            fila.addWidget(b, 1)
            self.botones[clave] = b
        v.addLayout(fila)
        self.nota = QLabel()
        self.nota.setFont(T.font_ui(7))
        self.nota.setWordWrap(True)
        v.addWidget(self.nota)
        self._marcar(valor)
        self._decir(PRIO_NOTA[valor], "rgba(255,255,255,0.7)")
        if is_readonly():
            for b in self.botones.values():
                b.setEnabled(False)
            self._decir("Modo solo lectura: la prioridad no se puede cambiar.", T.TEXT_MUTED)

    @staticmethod
    def _css(clave: str) -> str:
        fondo, tinta, borde = {"alta": (T.PRIO_ALTA, T.PRIO_ALTA_TINTA, T.PRIO_ALTA),
                               "normal": ("rgba(255,255,255,0.2)", "#ffffff", "rgba(255,255,255,0.45)"),
                               "baja": ("#5A6070", "#ffffff", T.PRIO_BAJA)}[clave]
        return (f"QPushButton {{ color: rgba(255,255,255,0.72); background: rgba(255,255,255,0.05);"
                f" border: 1px solid rgba(255,255,255,0.16); }}"
                f"QPushButton:hover {{ border-color: {T.PRIO_ALTA}; }}"
                f"QPushButton:checked {{ color: {tinta}; background: {fondo}; border-color: {borde}; }}")

    def _marcar(self, valor: str) -> None:
        self.valor = valor
        for clave, b in self.botones.items():
            b.setChecked(clave == valor)

    def _decir(self, texto: str, color: str) -> None:
        self.nota.setText(texto)
        self.nota.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _elegir(self, clave: str) -> None:
        # El click de Qt ya tildó el segmento: se deshace y se marca recién si la escritura salió.
        self._marcar(self.valor)
        if clave == self.valor:
            return
        import sqlite3
        try:
            res = self._editor.guardar(self._id, clave, self._nombre)
        except (sqlite3.Error, ValueError) as e:
            self._decir(f"No se guardó: {e}", AMBAR_AVISO)
            return
        if not res.escribio:
            self._decir(f"No se guardó: {res.motivo_no_escribio}", AMBAR_AVISO)
            return
        self._marcar(clave)
        self._decir(f"● Sugerencias de discos recalculadas. {PRIO_NOTA[clave]}", T.PRIO_ALTA)
        self.cambiada.emit(clave)


class Portada(_Hero):
    """La portada ancha: arte, identidad abajo a la izquierda y la prioridad arriba a la derecha."""

    def __init__(self, ficha: FichaPJ, acento: str, db_path=None):
        super().__init__(ficha, acento)
        # El selector va encima del arte, fuera del layout: apilado con la identidad no entra en
        # los 200 px del hero (el nombre salía cortado).
        self.selector_prioridad = _SelectorPrioridad(ficha.id, ficha.nombre, ficha.prioridad, db_path, self)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 14, 14, 18)
        raiz.addStretch()
        raiz.addWidget(self._identidad(ficha, acento))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.selector_prioridad.adjustSize()
        self.selector_prioridad.move(self.width() - 14 - _SelectorPrioridad.ANCHO, 14)

    @staticmethod
    def _identidad(f: FichaPJ, acento: str) -> QWidget:
        ident = QWidget()
        ident.setStyleSheet("background: transparent;")
        h = QHBoxLayout(ident)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        avatar = QLabel()
        avatar.setFixedSize(96, 96)
        avatar.setStyleSheet(f"background: {T.BG_BASE}; border: 2px solid {acento}; border-radius: 16px;")
        pm = _pixmap(f.avatar)
        if pm is not None:
            avatar.setPixmap(_redondeado(pm, 92, 14))
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignBottom)
        v = QVBoxLayout()
        v.setSpacing(4)
        fila_fac = QHBoxLayout()
        fila_fac.setSpacing(8)
        pm = _pixmap(f.faccion_logo)
        if pm is not None:
            logo = QLabel()
            logo.setStyleSheet("background: transparent; border: none;")
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
        for texto, macizo in ((f.elemento or "—", False), (f.rol or "—", False),
                              (f"M{f.mindscape}" if f.mindscape is not None else "M?", True)):
            c = _lbl(texto.upper(), T.font_ui(9, bold=True), T.BG_BASE if macizo else acento)
            c.setStyleSheet(
                f"color: {T.BG_BASE if macizo else acento}; padding: 3px 10px;"
                f" background: {acento if macizo else 'rgba(0,0,0,0.5)'}; border: 1px solid {acento};")
            chips.addWidget(c)
        chips.addStretch()
        v.addLayout(chips)
        h.addLayout(v, 1)
        return ident


class HoyEnElJuego(QWidget):
    """Lo leído del juego: stats (con arma, bonus y despertar debajo) | hexágono con sus sets."""

    def __init__(self, ficha: FichaPJ, acento: str):
        super().__init__()
        self.ficha, self.acento = ficha, acento
        self._stats: dict[str, QLabel] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 12, 12)
        v.setSpacing(8)
        v.addWidget(_caps("Hoy en el juego", acento))
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addLayout(self._col_stats_y_arma(), 1)
        cols.addWidget(self._col_build(), 0)
        v.addLayout(cols, 1)

    def _col_stats_y_arma(self) -> QVBoxLayout:
        f, acento = self.ficha, self.acento
        v = QVBoxLayout()
        v.setSpacing(4)
        v.addWidget(_caps("Stats combate", acento))
        crudos = f.stats_crudos
        for (etiqueta, texto), (_e, col) in zip(f.stats, stats_de_rol(f.rol), strict=True):
            g = _Gauge(etiqueta, texto, crudos.get(col), _ESCALA_BARRA.get(col, 1), acento)
            self._stats[etiqueta] = g.valor
            v.addWidget(g)
        v.addSpacing(6)
        v.addWidget(_caps("W-Engine", acento))
        caja = QFrame()
        caja.setObjectName("caja_arma")
        caja.setStyleSheet(f"QFrame#caja_arma {{ border: 1px solid {acento}; background: rgba(255,255,255,0.03); }}")
        h = QHBoxLayout(caja)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        if f.arma is None:
            h.addWidget(_lbl("sin arma equipada", T.font_ui(10), T.TEXT_MUTED))
        else:
            ico = QLabel()
            ico.setFixedSize(44, 44)
            ico.setStyleSheet("border: none; background: transparent;")
            pm = _pixmap(f.arma.icono)
            if pm is not None:
                ico.setPixmap(pm.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            h.addWidget(ico)
            tv = QVBoxLayout()
            tv.setSpacing(3)
            tv.addWidget(_lbl(f.arma.nombre, T.font_display(11, bold=True), T.TEXT_PRIMARY))
            ref = f.arma.refinamiento
            nivel = f"Nv {f.arma.nivel}" if f.arma.nivel is not None else "Nv sin leer"
            tv.addWidget(_lbl(f"{nivel}  ·  P{ref}" if ref else f"{nivel}  ·  P sin leer",
                              T.font_mono(9), acento))
            h.addLayout(tv, 1)
        v.addWidget(caja)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        bono = QVBoxLayout()
        bono.setSpacing(2)
        bono.addWidget(_caps("Bonus elemental", T.TEXT_MUTED))
        bono.addWidget(_lbl(f.bono, T.font_ui(9, bold=True), acento) if f.bono
                       else _lbl("sin leer", T.font_ui(9), T.TEXT_MUTED))
        fila.addLayout(bono, 1)
        desp = QVBoxLayout()
        desp.setSpacing(2)
        desp.addWidget(_caps("Despertar", T.TEXT_MUTED))
        if f.despertar is None:
            desp.addWidget(_lbl("sin registro", T.font_ui(9), T.TEXT_MUTED))
        else:
            texto = f"Nivel {f.despertar}/6"
            if f.despertar_nombre:
                texto += f" · {f.despertar_nombre}"
            desp.addWidget(_lbl(texto, T.font_ui(9), T.TEXT_SECONDARY, wrap=True))
        fila.addLayout(desp, 1)
        v.addLayout(fila)
        v.addStretch()
        return v

    def _col_build(self) -> QWidget:
        f = self.ficha
        w = QWidget()
        w.setFixedWidth(250)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(_caps("Build · 6 slots", self.acento))
        hexa = BuildHexagon(lado=210)
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

    def textos_de_stats(self) -> dict[str, str]:
        return {k: lbl.text() for k, lbl in self._stats.items()}

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
- **prioridad** (mig 42, handoff `design_v3_prioridad_de_buildeo`) → sólo alta y baja; normal no se
  pinta (es la mayoría, como el nivel 60). Alta = barra superior lima + pestaña ▲; baja = sólo la
  pestaña ▼ en pizarra, sin brillo: "apartado", no alerta. La pestaña ocupa la esquina superior
  izquierda, así que el logo de facción se corre.

Lo web-only del diseño (chamfers por `clip-path`, glows compuestos) no se porta.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.asset_resolver import agent_avatar_path, faction_logo_path
from app.ui import tokens as T
from app.ui.roster.datos import CeldaPJ

AMBAR = "#F0AA3C"       # "le faltan datos" — mismo ámbar que el editor de roster
VIOLETA = "#B06FF0"     # atuendo — el violeta del editor
NARANJA_INF = "#FF8A3D" # rango ∞


#: Pestaña de prioridad (diseño: `left 3, top 0`, 17×14) y barra de alta (3 px), a escala 1.
_TAB_X, _TAB_W, _TAB_H, _BARRA_H = 3, 17, 14, 3
#: Lo que se corre el logo de facción cuando hay pestaña: el contenido arranca en x = 6 (margen) y
#: la fila separa 4 px, así que el logo cae en 6 + hueco + 4 — tiene que quedar a la derecha de la
#: pestaña (3 + 17) con 2 px de aire.
_HUECO_PRIO = _TAB_X + _TAB_W + 2 - 6 - 4


def pintar_marca_prioridad(p: QPainter, prioridad: str, ancho: float, s: float = 1.0,
                           barra: bool = True) -> None:
    """La marca de prioridad, anclada arriba a la izquierda de un rectángulo de `ancho`. La usan la
    celda y la leyenda (una sola figura). Normal no se pinta."""
    if prioridad not in ("alta", "baja"):
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    alta = prioridad == "alta"
    if alta and barra:
        p.fillRect(QRectF(0, 0, ancho, _BARRA_H * s), QColor(T.PRIO_ALTA))
        # Halo. Con alfa por `setAlpha` y NO sumando "40" al string: Qt lee "#C4F03A40" como
        # #AARRGGBB (alfa C4, color F03A40) y pintaba una línea ROJA bajo la barra (visto en la
        # primera captura).
        halo = QColor(T.PRIO_ALTA)
        halo.setAlpha(0x40)
        p.fillRect(QRectF(0, _BARRA_H * s, ancho, 2 * s), halo)
    tab = QRectF(_TAB_X * s, 0, _TAB_W * s, _TAB_H * s)
    if alta:
        p.fillRect(tab, QColor(T.PRIO_ALTA))
    else:
        p.fillRect(tab, QColor(T.PRIO_BAJA_FONDO))
        p.setPen(QPen(QColor(T.PRIO_BAJA), 1))          # sin borde superior
        p.drawLine(tab.topLeft(), tab.bottomLeft())
        p.drawLine(tab.bottomLeft(), tab.bottomRight())
        p.drawLine(tab.bottomRight(), tab.topRight())
    lado = max(2.0, round(_TAB_H * s * 0.3))
    cx, cy, h = tab.center().x(), tab.center().y(), lado * 1.2
    tri = QPainterPath()
    if alta:
        tri.moveTo(QPointF(cx - lado, cy + h / 2))
        tri.lineTo(QPointF(cx + lado, cy + h / 2))
        tri.lineTo(QPointF(cx, cy - h / 2))
    else:
        tri.moveTo(QPointF(cx - lado, cy - h / 2))
        tri.lineTo(QPointF(cx + lado, cy - h / 2))
        tri.lineTo(QPointF(cx, cy + h / 2))
    tri.closeSubpath()
    p.fillPath(tri, QColor(T.PRIO_ALTA_TINTA if alta else T.PRIO_BAJA_TINTA))
    p.restore()


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
            halo = QColor(NARANJA_INF)   # alfa por `setAlpha`: "#FF8A3D66" es #AARRGGBB (magenta)
            halo.setAlpha(0x66)
            p.setPen(QPen(halo, 3))
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


class _BotoneraPrioridad(QWidget):
    """Modo edición (handoff design_v3): tres segmentos ▲ · – · ▼ con destino explícito, un click
    y listo. Descartados por el diseño: el ciclo normal→alta→baja (para llegar a baja pasa por alta
    y recalcula dos veces) y la selección múltiple (no ahorra clicks para ~15 PJs)."""

    elegida = Signal(str)
    _SEGMENTOS = (("alta", "▲"), ("normal", "–"), ("baja", "▼"))

    def __init__(self, valor: str):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self.botones: dict[str, QPushButton] = {}
        for clave, glifo in self._SEGMENTOS:
            b = QPushButton(glifo)
            b.setCheckable(True)
            b.setFixedHeight(15)
            b.setFont(T.font_ui(7))
            b.setToolTip({"alta": "Prioridad alta", "normal": "Prioridad normal",
                          "baja": "Prioridad baja"}[clave])
            b.setStyleSheet(self._css(clave))
            b.clicked.connect(lambda _c=False, k=clave: self._click(k))
            h.addWidget(b, 1)
            self.botones[clave] = b
        self.set_valor(valor)

    @staticmethod
    def _css(clave: str) -> str:
        fondo, tinta = {"alta": (T.PRIO_ALTA, T.PRIO_ALTA_TINTA),
                        "normal": ("rgba(255,255,255,0.2)", T.TEXT_PRIMARY),
                        "baja": ("#5A6070", "#EEF0F5")}[clave]
        borde = {"alta": T.PRIO_ALTA, "normal": "rgba(255,255,255,0.35)", "baja": T.PRIO_BAJA}[clave]
        return (f"QPushButton {{ color: {T.TEXT_MUTED}; background: rgba(255,255,255,0.04);"
                f" border: 1px solid {T.BORDER_SUBTLE}; padding: 0; }}"
                f"QPushButton:hover {{ color: {T.PRIO_ALTA}; border-color: {T.PRIO_ALTA}; }}"
                f"QPushButton:checked {{ color: {tinta}; background: {fondo}; border-color: {borde}; }}")

    def set_valor(self, valor: str) -> None:
        self.valor = valor
        for clave, b in self.botones.items():
            b.setChecked(clave == valor)

    def _click(self, clave: str) -> None:
        # El click de Qt ya tildó el segmento; se deshace: lo marca la vista recién cuando la
        # escritura salió (si falla o la app está en solo lectura, la celda no puede mostrar un
        # valor que no quedó guardado).
        self.set_valor(self.valor)
        self.elegida.emit(clave)


class CeldaRoster(QFrame):
    """Una celda clickeable. `clicked(agente_id)`; en modo edición, `prioridad_elegida(id, valor)`
    y el click NO pide la ficha."""

    clicked = Signal(int)
    prioridad_elegida = Signal(int, str)

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

        # fila 1: [hueco de la pestaña de prioridad] facción · rango
        fila1 = QHBoxLayout()
        fila1.setSpacing(4)
        self.prioridad = celda.prioridad if celda.prioridad in ("alta", "baja") else None
        self._hueco_prio = QWidget()
        self._hueco_prio.setFixedSize(_HUECO_PRIO if self.prioridad else 0, 1)
        self._hueco_prio.setStyleSheet("background: transparent; border: none;")
        fila1.addWidget(self._hueco_prio)
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
        # Modo edición de prioridades: la botonera REEMPLAZA nivel y discos mientras dura el modo.
        self.botonera = _BotoneraPrioridad(celda.prioridad)
        self.botonera.elegida.connect(lambda valor: self.prioridad_elegida.emit(self.celda.id, valor))
        self.botonera.hide()
        fila4.addWidget(self.botonera, 1)
        v.addLayout(fila4)
        self.editando = False
        self._guardado = _lbl("GUARDADO", T.font_caps(6, bold=True), T.PRIO_ALTA_TINTA)
        self._guardado.setParent(self)
        self._guardado.setStyleSheet(f"color: {T.PRIO_ALTA_TINTA}; background: {T.PRIO_ALTA};"
                                     " border: none; padding: 0 4px;")
        self._guardado.hide()
        self._css_base = self.styleSheet()

        self._escala_contenido = 1.0
        #: (label, tamaño base en pt) — lo que crece cuando la celda crece.
        self._fuentes = [(self._nombre, 8), (self._detalle, 6 if celda.variante_de else 7),
                         (self._nivel, 7)]
        ayudas = []
        if self.prioridad:
            ayudas.append(f"Prioridad de buildeo {self.prioridad}.")
        if celda.sin_thresholds:
            ayudas.append("Le faltan datos: sin umbrales (agent_thresholds) — onboarding a medias.")
        if ayudas:
            self.setToolTip("\n".join(ayudas))

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
        self._ajustar_hueco()

    def escala_contenido(self) -> float:
        return self._escala_contenido

    # --- prioridad de buildeo -------------------------------------------------------------------

    def _ajustar_hueco(self) -> None:
        """Lo que se corre el logo de facción para no quedar bajo la pestaña. La pestaña (y su aire)
        crece con la escala, pero el margen (6) y el espaciado (4) no: (3 + 17 + 2)·s − 10, que a
        escala 1 da `_HUECO_PRIO`. Sin prioridad, 0."""
        ancho = round((_TAB_X + _TAB_W + 2) * self._escala_contenido) - 10 if self.prioridad else 0
        self._hueco_prio.setFixedSize(ancho, 1)

    def set_modo_edicion(self, on: bool) -> None:
        """La botonera reemplaza nivel y discos; el borde en hover pasa a lima y el click deja de
        pedir la ficha."""
        self.editando = on
        self._nivel.setVisible(not on)
        self._discos.setVisible(not on)
        self.botonera.setVisible(on)
        self.setCursor(Qt.CursorShape.ArrowCursor if on else Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._css_base + (
            f"QFrame#celda_roster:hover {{ border: 1px solid {T.PRIO_ALTA}; }}" if on else ""))
        if not on:
            self._guardado.hide()

    def set_prioridad(self, prioridad: str) -> None:
        """Actualiza la celda en el lugar (sin rearmar la grilla: se perderían los filtros)."""
        self.celda = replace(self.celda, prioridad=prioridad)
        self.prioridad = prioridad if prioridad in ("alta", "baja") else None
        self._ajustar_hueco()
        self.botonera.set_valor(prioridad)
        self.update()

    def marcar_guardado(self, ms: int = 2000) -> None:
        """Anillo lima + "GUARDADO" sobre la botonera, un rato. Sin toast: es un ajuste del
        usuario, no algo que pasó en el juego."""
        self.setStyleSheet(self._css_base + f"QFrame#celda_roster {{ border: 1px solid {T.PRIO_ALTA}; }}")
        self._guardado.adjustSize()
        self._guardado.move((self.width() - self._guardado.width()) // 2,
                            self.height() - self._guardado.height() - 21)
        self._guardado.show()
        self._guardado.raise_()
        QTimer.singleShot(ms, self._fin_guardado)

    def _fin_guardado(self) -> None:
        try:
            self._guardado.hide()
            self.set_modo_edicion(self.editando)
        except RuntimeError:
            pass        # la celda se destruyó (refrescar) antes de que venciera el timer

    # --- introspección para tests -----------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        return [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]

    # --- eventos --------------------------------------------------------------------------------

    def mouseReleaseEvent(self, ev):
        if (not self.editando and ev.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(ev.position().toPoint())):
            self.clicked.emit(self.celda.id)
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.prioridad:
            p = QPainter(self)
            pintar_marca_prioridad(p, self.prioridad, self.width(), self._escala_contenido)
            p.end()
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
        relleno = QColor(AMBAR)          # alfa por `setAlpha`: "#F0AA3C40" es #AARRGGBB (rojo)
        relleno.setAlpha(0x40)
        p.fillPath(tri, relleno)
        p.setPen(QPen(QColor(AMBAR), 1.5))
        for k in range(-lado, lado * 2, 4):
            p.drawLine(QPointF(w - lado + k, 0), QPointF(w + k, lado))
        p.end()

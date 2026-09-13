"""El build de un PJ dibujado como en el juego: seis discos alrededor de su cara.

⚠️ **El orden de los slots es el del JUEGO, no el del mockup.** `BuildHex` en panel.jsx reparte los
seis a partir de las 12 en punto y en sentido horario, que es como lo haría cualquiera. ZZZ no:

    Slot 1 (arriba-izq)    Slot 6 (arriba-der)
    Slot 2 (izquierda)     Slot 5 (derecha)
    Slot 3 (abajo-izq)     Slot 4 (abajo-der)

La columna izquierda baja 1→2→3 y la derecha baja 6→5→4. Si se copiaba el mockup, el disco del
slot 4 se iluminaba donde el ojo de Daniel busca el slot 2 — el mismo error que el juego no tiene
con Genshin, que usa el zig-zag.

La geometría (`posiciones_slots`) es una función pura con tests; el `paintEvent` sólo dibuja.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.ui import tokens as T

#: Ángulo de cada slot, en grados, con el eje y hacia ABAJO (coordenadas de pantalla).
#: Es un hexágono de "lados verticales": dos vértices a los costados y cuatro en diagonal.
SLOT_ANGULOS: dict[int, float] = {1: -120.0, 2: 180.0, 3: 120.0, 4: 60.0, 5: 0.0, 6: -60.0}


def posiciones_slots(cx: float, cy: float, radio: float) -> dict[int, tuple[float, float]]:
    """Centro de cada slot 1..6 para un hexágono centrado en (cx, cy)."""
    out = {}
    for slot, grados in SLOT_ANGULOS.items():
        a = math.radians(grados)
        out[slot] = (cx + radio * math.cos(a), cy + radio * math.sin(a))
    return out


def _pixmap(path: str | None, lado: int) -> QPixmap | None:
    if not path or not Path(path).exists():
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation)


class BuildHexagon(QWidget):
    """`set_build(slots, destacado, centro)`: slots = {n: {"logo": path|None, "nivel": int|None}}.

    Un slot ausente del dict se dibuja como hueco punteado con su número: un PJ con cinco discos
    tiene un hueco, no un crash ni un disco inventado.
    """

    def __init__(self, lado: int = 250, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(lado, lado)
        self._slots: dict[int, dict] = {}
        self._destacado: int | None = None
        self._centro: str | None = None
        # Los pixmaps se cargan una vez por build y no en cada repintado.
        self._cache: dict[str, QPixmap | None] = {}

    # --- API ----------------------------------------------------------------------------------

    def set_build(self, slots: dict[int, dict], destacado: int | None, centro: str | None) -> None:
        self._slots = dict(slots or {})
        self._destacado = destacado
        self._centro = centro
        self._cache.clear()
        self.update()

    def slots(self) -> dict[int, dict]:
        return dict(self._slots)

    def destacado(self) -> int | None:
        return self._destacado

    # --- pintado ------------------------------------------------------------------------------

    def _px(self, path: str | None, lado: int) -> QPixmap | None:
        clave = f"{path}|{lado}"
        if clave not in self._cache:
            self._cache[clave] = _pixmap(path, lado)
        return self._cache[clave]

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        lado = self.width()
        cx = cy = lado / 2
        radio = lado * 0.36
        slot_d = lado * 0.22
        pos = posiciones_slots(cx, cy, radio)

        # contorno tenue del hexágono
        p.setPen(QPen(T.color("#ffffff", 0.06), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        orden = [1, 6, 5, 4, 3, 2]
        path = QPainterPath(QPointF(*pos[orden[0]]))
        for s in orden[1:]:
            path.lineTo(QPointF(*pos[s]))
        path.closeSubpath()
        p.drawPath(path)

        # cara del PJ en el centro
        centro_d = lado * 0.32
        rc = QRectF(cx - centro_d / 2, cy - centro_d / 2, centro_d, centro_d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.BG_BASE))
        p.drawEllipse(rc)
        cara = self._px(self._centro, int(centro_d))
        if cara is not None:
            clip = QPainterPath()
            clip.addEllipse(rc)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(rc.toRect(), cara)
            p.restore()
        p.setPen(QPen(QColor(T.YELLOW), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rc)

        for slot, (x, y) in pos.items():
            self._pintar_slot(p, slot, x, y, slot_d)
        p.end()

    def _pintar_slot(self, p: QPainter, slot: int, x: float, y: float, d: float) -> None:
        r = QRectF(x - d / 2, y - d / 2, d, d)
        datos = self._slots.get(slot)
        hi = slot == self._destacado

        if datos is None:
            p.setPen(QPen(QColor(T.BORDER_MID), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(T.BG_BASE))
            p.drawEllipse(r)
            p.setPen(QColor(T.TEXT_DIM))
            p.setFont(T.font_mono(7))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"0{slot}")
            return

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.BG_BASE))
        p.drawEllipse(r)
        logo = self._px(datos.get("logo"), int(d * 0.72))
        if logo is not None:
            lr = QRectF(x - d * 0.36, y - d * 0.36, d * 0.72, d * 0.72)
            p.drawPixmap(lr.toRect(), logo)

        if hi:
            # halo del disco que se está mirando
            p.setPen(QPen(T.color(T.YELLOW, 0.35), 6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)
        p.setPen(QPen(QColor(T.YELLOW if hi else T.BORDER_MID), 2.5 if hi else 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)

        nivel = datos.get("nivel")
        if nivel is not None:
            texto = f"L{nivel}"
            f = T.font_mono(7)
            p.setFont(f)
            ancho = p.fontMetrics().horizontalAdvance(texto) + 8
            pill = QRectF(x - ancho / 2, r.bottom() - 6, ancho, 13)
            p.setPen(QPen(QColor(T.YELLOW if hi else T.BORDER_MID), 1))
            p.setBrush(QColor(T.BG_BASE))
            p.drawRect(pill)
            p.setPen(QColor(T.YELLOW if hi else T.TEXT_SECONDARY))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, texto)

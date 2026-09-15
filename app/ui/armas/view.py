"""La pantalla Armas — porta `EnginesScreen` de `Pestana Armas - W-Engines.html` (Claude Design).

La jerarquía de los 4 trabajos del diseño, y cómo quedó cada uno:

| trabajo | en el diseño | acá |
|---|---|---|
| 1 · inventario | la grilla | ✅ una celda por arma física, sin scroll |
| 2 · auditoría | banda ámbar | ✅ PJs sin arma · sin usar · sin ícono |
| 3 · progreso | misma banda | ✅ nivel < 60 · P < 5, **separados** de nivel/P sin leer |
| 4 · comparador | modo aparte | ⏳ otra fase (decisión de Daniel, 2026-09-15) |

| banda | alto | |
|---|--:|---|
| header | 56 | título + conteos |
| filtros | 76 | `BandaFiltrosArmas` |
| cuerpo | resto | la grilla, o las tarjetas de los PJs sin arma |
| leyenda | 32 | qué significa cada marca |

Fuera del diseño: la barra de pestañas (el sidebar ya la cumple), los botones Exportar y Comparar,
el "agrupar por", y todos los datos de `engines-data.jsx` — se dibujaron con 5 armas leídas de 33,
y hoy la DB tiene las 56 completas.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.ui import grilla
from app.ui import tokens as T
from app.ui.armas.celda import AMBAR, CELDA_H, CELDA_W, CeldaArma, color_rareza
from app.ui.armas.datos import conteos, filtrar, leer_armas, ordenar, pjs_sin_arma
from app.ui.armas.filtros import BandaFiltrosArmas
from app.ui.live.item_card import TENENCIA_TEXTO

log = logging.getLogger(__name__)

GAP = 7


def _lbl(texto: str, font, color: str, wrap: bool = False) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setWordWrap(wrap)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class _Cuerpo(QWidget):
    """Posiciona las celdas a mano en cada resize, como el Roster. Sin layout y sin scroll."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._celdas: list[CeldaArma] = []
        self.aviso = _lbl("", T.font_ui(9), AMBAR)
        self.aviso.setParent(self)
        self.aviso.hide()

    def set_celdas(self, celdas: list[CeldaArma]) -> None:
        self._celdas = celdas
        for c in celdas:
            c.setParent(self)
        self.reubicar()

    def reubicar(self) -> None:
        visibles = [c for c in self._celdas if not c.isHidden()]
        g = grilla.calcular(len(visibles), self.width(), self.height(), base_w=CELDA_W,
                            base_h=CELDA_H, gap=GAP)
        usado = g.columnas * g.celda_w + (g.columnas - 1) * g.gap
        x0 = max(0, (self.width() - usado) // 2)
        for i, c in enumerate(visibles):
            fila, col = divmod(i, g.columnas)
            c.setGeometry(x0 + col * (g.celda_w + g.gap), fila * (g.celda_h + g.gap),
                          g.celda_w, g.celda_h)
            c.set_escala(g.escala)
        if not g.cabe and visibles:
            self.aviso.setText("Las armas no entran a este tamaño: agrandá la ventana o filtrá.")
            self.aviso.adjustSize()
            self.aviso.move(0, max(0, self.height() - self.aviso.height()))
            self.aviso.show()
            self.aviso.raise_()
        else:
            self.aviso.hide()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.reubicar()


class _TarjetaPJ(QPushButton):
    """Un PJ sin arma equipada (modo auditoría). Click → su ficha."""

    def __init__(self, pj: dict):
        super().__init__()
        self.pj = pj
        self.setObjectName("tarjeta_pj")
        self.setFixedSize(232, 78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        acento = T.color_elemento(pj.get("elemento"))
        self.setStyleSheet(
            f"QPushButton#tarjeta_pj {{ background: {T.BG_PANEL}; border: 1px solid {AMBAR}88;"
            f" border-left: 3px solid {acento}; text-align: left; }}"
            f"QPushButton#tarjeta_pj:hover {{ border-color: {AMBAR}; }}")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(10)
        avatar = QLabel()
        avatar.setFixedSize(44, 44)
        avatar.setStyleSheet(f"border: 1px solid {acento}; border-radius: 22px; background: {T.BG_BASE};")
        if pj.get("avatar") and Path(pj["avatar"]).exists():
            pm = QPixmap(pj["avatar"]).scaled(42, 42, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                              Qt.TransformationMode.SmoothTransformation)
            avatar.setPixmap(pm)
        h.addWidget(avatar)
        v = QVBoxLayout()
        v.setSpacing(1)
        self.nombre = _lbl(pj["nombre"], T.font_display(11, bold=True), T.TEXT_PRIMARY)
        v.addWidget(self.nombre)
        nivel = f"Nv {pj['nivel']}" if pj.get("nivel") is not None else "Nv sin leer"
        v.addWidget(_lbl(f"{pj.get('elemento') or '—'} · {pj.get('rango') or '—'} · {nivel}",
                         T.font_caps(7), T.TEXT_MUTED))
        if pj.get("variante_de"):
            marca = f"ATUENDO · {pj['variante_de']}"
        elif pj.get("sin_thresholds"):
            marca = "LE FALTAN DATOS"
        else:
            marca = "SIN ARMA EQUIPADA"
        v.addWidget(_lbl(marca, T.font_caps(7, bold=True), AMBAR))
        h.addLayout(v, 1)
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class ArmasView(QWidget):
    arma_elegida = Signal(int)
    pj_pedido = Signal(int)

    def __init__(self, con: sqlite3.Connection | None, parent: QWidget | None = None):
        super().__init__(parent)
        self._con = con
        self._celdas: list[CeldaArma] = []
        self._pjs: list[dict] = []
        self._modo = "grilla"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(56)
        header.setObjectName("armas_header")
        header.setStyleSheet(f"QFrame#armas_header {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(14)
        hl.addWidget(_lbl("Armas", T.font_display(16, bold=True), T.TEXT_PRIMARY))
        hl.addWidget(_lbl("W-ENGINES", T.font_caps(8), T.TEXT_MUTED))
        self._conteos = _lbl("", T.font_mono(9), T.TEXT_SECONDARY)
        hl.addWidget(self._conteos)
        self._faltan = _lbl("", T.font_mono(9), AMBAR)
        hl.addWidget(self._faltan)
        hl.addStretch()
        root.addWidget(header)

        self._slot_filtros = QVBoxLayout()
        self._slot_filtros.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._slot_filtros)
        self.filtros: BandaFiltrosArmas | None = None

        cont = QWidget()
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(14, 10, 14, 10)
        self.cuerpo = _Cuerpo()
        cl.addWidget(self.cuerpo, 1)
        self._panel_pjs = QWidget()
        self._panel_pjs.hide()
        cl.addWidget(self._panel_pjs, 1)
        root.addWidget(cont, 1)

        root.addWidget(self._leyenda())
        self.refrescar()

    def _leyenda(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(32)
        f.setObjectName("armas_leyenda")
        f.setStyleSheet(f"QFrame#armas_leyenda {{ border-top: 1px solid {T.BORDER_SUBTLE}; background: {T.BG_DEEP}; }}")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(18)
        for texto, color, ayuda in (
            (f"▌{TENENCIA_TEXTO['equipada'][0]} · con su PJ", TENENCIA_TEXTO["equipada"][1], "Franja de abajo: quién la tiene equipada."),
            (TENENCIA_TEXTO["libre"][0] + " · sin dueño", TENENCIA_TEXTO["libre"][1], "Nadie la tiene equipada."),
            ("★★★☆☆ refinamiento · mínimo P1", T.YELLOW, "Sin lectura va texto: cinco vacías serían P0, que no existe."),
            ("×n copias del modelo", T.YELLOW_SOFT, "Hay n armas físicas de este mismo modelo."),
            ("◤ falta ícono o especialidad", AMBAR, "Dato del catálogo que todavía no está."),
            ("▌S / A", color_rareza("S"), "Franja izquierda: la rareza."),
        ):
            l = _lbl(texto, T.font_ui(8), color)
            l.setToolTip(ayuda)
            h.addWidget(l)
        h.addStretch()
        f.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return f

    # --- datos --------------------------------------------------------------------------------------

    def refrescar(self) -> None:
        filas = []
        self._pjs = []
        if self._con is not None:
            try:
                filas = ordenar(leer_armas(self._con))
                self._pjs = pjs_sin_arma(self._con)
            except sqlite3.Error:
                log.exception("[armas] no se pudo leer el inventario")
                self._conteos.setText("error al leer la DB")

        k = conteos(filas)
        self._conteos.setText(
            f"{_plural(k['armas'], 'arma', 'armas')} · {_plural(k['modelos'], 'modelo', 'modelos')} · "
            f"{_plural(k['equipadas'], 'equipada', 'equipadas')} · {_plural(k['libres'], 'libre', 'libres')}")
        faltan = []
        if self._pjs:
            faltan.append(_plural(len(self._pjs), "PJ sin arma", "PJs sin arma"))
        if k["sin_icono"]:
            faltan.append(f"{k['sin_icono']} sin ícono")
        self._faltan.setText(" · ".join(faltan))

        for c in self._celdas:
            c.deleteLater()
        self._celdas = []
        for fila in filas:
            c = CeldaArma(fila)
            c.clicked.connect(self._elegir)
            c.dueno_pedido.connect(self.pj_pedido.emit)
            self._celdas.append(c)

        if self.filtros is not None:
            self._slot_filtros.removeWidget(self.filtros)
            self.filtros.deleteLater()
        self.filtros = BandaFiltrosArmas(filas, len(self._pjs))
        self.filtros.cambiaron.connect(self._aplicar_filtros)
        self._slot_filtros.addWidget(self.filtros)

        self._armar_panel_pjs()
        self.cuerpo.set_celdas(self._celdas)
        self._aplicar_filtros()

    def _armar_panel_pjs(self) -> None:
        viejo = self._panel_pjs.layout()
        if viejo is not None:
            QWidget().setLayout(viejo)          # suelta el layout anterior y sus hijos
        v = QVBoxLayout(self._panel_pjs)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        aviso = QFrame()
        aviso.setObjectName("aviso_pjs")
        aviso.setStyleSheet(f"QFrame#aviso_pjs {{ background: rgba(240,170,60,0.08);"
                            f" border: 1px solid {AMBAR}66; border-left: 3px solid {AMBAR}; }}")
        av = QVBoxLayout(aviso)
        av.setContentsMargins(12, 8, 12, 8)
        av.addWidget(_lbl(f"LOS {len(self._pjs)} PJs SIN W-ENGINE EQUIPADO — DATO DEL ROSTER",
                          T.font_caps(9, bold=True), AMBAR))
        av.addWidget(_lbl("Ninguno tiene un arma equipada en el inventario. Click en una tarjeta abre "
                          "su ficha.", T.font_ui(9), T.TEXT_SECONDARY, wrap=True))
        v.addWidget(aviso)
        rejilla = QGridLayout()
        rejilla.setSpacing(10)
        self._tarjetas: list[_TarjetaPJ] = []
        for i, pj in enumerate(self._pjs):
            t = _TarjetaPJ(pj)
            t.clicked.connect(lambda _c=False, pid=pj["id"]: self.pj_pedido.emit(pid))
            self._tarjetas.append(t)
            rejilla.addWidget(t, i // 4, i % 4)
        v.addLayout(rejilla)
        v.addStretch()

    def _aplicar_filtros(self) -> None:
        sel = self.filtros.seleccion()
        auditoria = set(sel.get("auditoria", set()))
        self._modo = "pjs" if "pjs_sin_arma" in auditoria else "grilla"
        auditoria.discard("pjs_sin_arma")
        if auditoria:
            sel["auditoria"] = auditoria
        else:
            sel.pop("auditoria", None)

        if self._modo == "pjs":
            for c in self._celdas:
                c.setVisible(False)
            self.cuerpo.hide()
            self._panel_pjs.show()
            return
        self._panel_pjs.hide()
        self.cuerpo.show()
        pasan = {f.id for f in filtrar([c.fila for c in self._celdas], sel)}
        for c in self._celdas:
            c.setVisible(c.fila.id in pasan)
        self.cuerpo.reubicar()

    def _elegir(self, inv_id: int) -> None:
        for c in self._celdas:
            c.set_seleccion(c.fila.id == inv_id)
        self.arma_elegida.emit(inv_id)

    # --- introspección para tests -----------------------------------------------------------------

    def celdas(self) -> list[CeldaArma]:
        return list(self._celdas)

    def modo(self) -> str:
        return self._modo

    def texto_header(self) -> str:
        return f"{self._conteos.text()}  {self._faltan.text()}"

    def textos_de_pjs(self) -> list[str]:
        return [t.nombre.text() for t in getattr(self, "_tarjetas", [])]

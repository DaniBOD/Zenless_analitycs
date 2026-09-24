"""La pantalla Roster — Parte B del diseño v1, la plantilla de "pestaña de catálogo".

Cuatro bandas de alto fijo; **el cuerpo nunca scrollea**:

| banda | alto | |
|---|--:|---|
| header | 56 | título, los conteos como números separados, "Declarar roster…" |
| filtros | 104 | `BandaFiltros` |
| cuerpo | resto | la grilla ENTERA, redimensionada con `datos.calcular_grilla` |
| leyenda | 32 | qué significa cada marca — obligatoria: sin ella son adorno |

La banda de 42 px de pestañas del diseño no se porta: el sidebar del shell ya cumple esa función.

La vista no abre el modal: emite `ficha_pedida(agente_id)` y lo abre la ventana, que es la dueña
de los diálogos. Así se testea sin modal y el modal sin roster.
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.core.roster_declaration import no_poseidos_declarados
from app.ui import tokens as T
from app.ui.roster.celda import AMBAR, NARANJA_INF, VIOLETA, CeldaRoster, pintar_marca_prioridad
from app.ui.roster.datos import (
    calcular_grilla, conteos_header, conteos_prioridad, filtrar, leer_roster, ordenar,
)
from app.ui.roster.filtros import BandaFiltros

log = logging.getLogger(__name__)

HEADER_H = 56
LEYENDA_H = 32


def _lbl(texto: str, font, color: str) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


def _no_obtenidos(con: sqlite3.Connection) -> set[str]:
    """Última declaración, leída por la MISMA conexión de la vista (y no por la ruta de la DB)."""
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "roster_declarations" not in tablas:
            return set()
        ts = con.execute("SELECT MAX(ts) FROM roster_declarations").fetchone()[0]
        if not ts:
            return set()
        return {r[0] for r in con.execute(
            "SELECT nombre FROM roster_declarations WHERE ts = ? AND poseido = 0", (ts,))}
    except sqlite3.Error:
        log.exception("[roster] no se pudo leer la declaración")
        return set()


class _MuestraPrioridad(QWidget):
    """La marca de prioridad en miniatura para la leyenda: la MISMA figura que la celda
    (`pintar_marca_prioridad`), sobre un rectángulo de celda de 16×12."""

    def __init__(self, prioridad: str):
        super().__init__()
        self.prioridad = prioridad
        self.setFixedSize(16, 12)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setPen(QColor(T.BORDER_MID))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        pintar_marca_prioridad(p, self.prioridad, self.width(), s=0.55)
        p.end()


class _Cuerpo(QWidget):
    """Posiciona las celdas a mano en cada resize. Sin layout y sin scroll, a propósito."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._celdas: list[CeldaRoster] = []
        self.aviso = _lbl("", T.font_ui(9), AMBAR)
        self.aviso.setParent(self)
        self.aviso.hide()

    def set_celdas(self, celdas: list[CeldaRoster]) -> None:
        self._celdas = celdas
        for c in celdas:
            c.setParent(self)
        self.reubicar()

    def reubicar(self) -> None:
        visibles = [c for c in self._celdas if not c.isHidden()]
        g = calcular_grilla(len(visibles), self.width(), self.height())
        usado = g.columnas * g.celda_w + (g.columnas - 1) * g.gap
        x0 = max(0, (self.width() - usado) // 2)
        for i, c in enumerate(visibles):
            fila, col = divmod(i, g.columnas)
            c.setGeometry(x0 + col * (g.celda_w + g.gap), fila * (g.celda_h + g.gap),
                          g.celda_w, g.celda_h)
            c.set_escala(g.escala)
        if not g.cabe and visibles:
            # No se agrega scroll (regla del diseño): se dice que no entra.
            self.aviso.setText("El roster no entra a este tamaño: agrandá la ventana o filtrá.")
            self.aviso.adjustSize()
            self.aviso.move(0, max(0, self.height() - self.aviso.height()))
            self.aviso.show()
            self.aviso.raise_()
        else:
            self.aviso.hide()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.reubicar()


class RosterView(QWidget):
    ficha_pedida = Signal(int)

    def __init__(self, con: sqlite3.Connection | None, parent: QWidget | None = None):
        super().__init__(parent)
        self._con = con
        self._celdas: list[CeldaRoster] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QFrame()
        header.setFixedHeight(HEADER_H)
        header.setObjectName("roster_header")
        header.setStyleSheet(f"QFrame#roster_header {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(14)
        hl.addWidget(_lbl("Roster", T.font_display(16, bold=True), T.TEXT_PRIMARY))
        self._conteos = _lbl("", T.font_mono(9), T.TEXT_SECONDARY)
        hl.addWidget(self._conteos)
        self._sin_umbrales = _lbl("", T.font_mono(9), AMBAR)
        hl.addWidget(self._sin_umbrales)
        hl.addStretch()
        self.btn_declarar = QPushButton("Declarar roster…")
        self.btn_declarar.setToolTip(
            "Decí qué personajes tenés. El sistema no puede enumerar solo a los que NO tenés:\n"
            "en el menú salen en gris y el reconocedor los confunde con uno propio.")
        self.btn_declarar.clicked.connect(self._abrir_declaracion)
        hl.addWidget(self.btn_declarar)
        root.addWidget(header)

        self._slot_filtros = QVBoxLayout()
        self._slot_filtros.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._slot_filtros)
        self.filtros: BandaFiltros | None = None

        cont = QWidget()
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(12, 10, 12, 10)
        self.cuerpo = _Cuerpo()
        cl.addWidget(self.cuerpo)
        root.addWidget(cont, 1)

        root.addWidget(self._leyenda())
        self.refrescar()

    # --- construcción -----------------------------------------------------------------------------

    def _leyenda(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(LEYENDA_H)
        f.setObjectName("roster_leyenda")
        f.setStyleSheet(f"QFrame#roster_leyenda {{ border-top: 1px solid {T.BORDER_SUBTLE};"
                        f" background: {T.BG_DEEP}; }}")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(18)
        for color, texto, ayuda in (
            (AMBAR, "◤ le faltan datos", "Esquina rayada ámbar: sin umbrales (agent_thresholds), onboarding a medias."),
            (NARANJA_INF, "⬬ rango ∞", "Cápsula maciza con halo: rango ∞. S y A son un círculo hueco."),
            (VIOLETA, "┆ atuendo", "Borde punteado violeta: variante de atuendo, con build propio."),
            (T.TEXT_MUTED, "sin leer", "Nivel no capturado todavía: se lee en los atributos del PJ en el juego."),
            (AMBAR, "Nv ≠ 60", "El nivel se tiñe sólo cuando no es 60."),
            (T.YELLOW, "▪ discos (+n)", "Seis casilleros de discos equipados; lo que pasa de 6 va como +n."),
        ):
            l = _lbl(texto, T.font_ui(8), color)
            l.setToolTip(ayuda)
            h.addWidget(l)
        # Prioridad de buildeo: sólo si hay alguna declarada (`refrescar` las muestra u oculta).
        self._leyenda_prio: dict[str, QWidget] = {}
        for prio, texto, color, ayuda in (
            ("alta", "prioridad alta", T.PRIO_ALTA,
             "Barra lima + pestaña ▲: recibe discos primero y nadie de menor prioridad se los saca."),
            ("baja", "prioridad baja", T.PRIO_BAJA_TEXTO,
             "Pestaña ▼ pizarra: cede discos a PJs de prioridad mayor. Es una decisión, no un error."),
        ):
            item = QWidget()
            ih = QHBoxLayout(item)
            ih.setContentsMargins(0, 0, 0, 0)
            ih.setSpacing(5)
            ih.addWidget(_MuestraPrioridad(prio))
            l = _lbl(texto, T.font_ui(8), color)
            ih.addWidget(l)
            item.setToolTip(ayuda)
            item.hide()
            self._leyenda_prio[prio] = item
            h.addWidget(item)
        h.addStretch()
        # La leyenda nunca impone ancho: si no entra, se recorta a la derecha (tiene tooltips).
        f.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return f

    def refrescar(self) -> None:
        """Relee la DB y rearma celdas, filtros y conteos. Barato: cuatro consultas."""
        celdas_datos = []
        no_obt: set[str] = set()
        if self._con is not None:
            try:
                celdas_datos = ordenar(leer_roster(self._con))
                no_obt = _no_obtenidos(self._con)
            except sqlite3.Error:
                log.exception("[roster] no se pudo leer la DB")
                self._conteos.setText("error al leer la DB")

        k = conteos_header(celdas_datos, no_obt)
        self._conteos.setText(
            f"{k['filas']} filas  −{k['atuendos']} atuendo  = {k['distintos']} distintos"
            f"  +{k['no_obtenidos']} no obtenidos  = {k['conocidos']} conocidos")
        self._sin_umbrales.setText(f"{k['sin_thresholds']} sin umbrales" if k["sin_thresholds"] else "")
        prio = conteos_prioridad(celdas_datos)
        hay_prioridades = bool(prio["alta"] or prio["baja"])
        for item in self._leyenda_prio.values():
            item.setVisible(hay_prioridades)

        for c in self._celdas:
            c.deleteLater()
        self._celdas = []
        for d in celdas_datos:
            c = CeldaRoster(d)
            c.clicked.connect(self.ficha_pedida.emit)
            self._celdas.append(c)

        if self.filtros is not None:
            self._slot_filtros.removeWidget(self.filtros)
            self.filtros.deleteLater()
        self.filtros = BandaFiltros(celdas_datos)
        self.filtros.cambiaron.connect(self._aplicar_filtros)
        self._slot_filtros.addWidget(self.filtros)

        self.cuerpo.set_celdas(self._celdas)
        self._aplicar_filtros()

    def _aplicar_filtros(self) -> None:
        pasan = {c.id for c in filtrar([x.celda for x in self._celdas], self.filtros.seleccion())}
        for c in self._celdas:
            c.setVisible(c.celda.id in pasan)
        self.cuerpo.reubicar()

    def _abrir_declaracion(self) -> None:
        from app.ui.roster_declaration_dialog import RosterDeclarationDialog
        dlg = RosterDeclarationDialog(parent=self)
        if dlg.exec() and dlg.resultado and dlg.resultado.escribio:
            self.refrescar()

    # --- introspección para tests -----------------------------------------------------------------

    def celdas(self) -> list[CeldaRoster]:
        return list(self._celdas)

    def texto_header(self) -> str:
        return f"{self._conteos.text()}  {self._sin_umbrales.text()}"

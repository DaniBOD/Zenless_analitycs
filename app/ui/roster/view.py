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
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.core.prioridad import EditorPrioridades
from app.core.roster_declaration import no_poseidos_declarados
from app.db.connection import is_readonly
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

    def __init__(self, con: sqlite3.Connection | None, parent: QWidget | None = None,
                 db_path: Path | str | None = None):
        """`con` es la conexión de LECTURA de la UI. Las prioridades se escriben aparte, con
        `EditorPrioridades` (su propia conexión, RNF-01), sobre `db_path` (None = la DB activa)."""
        super().__init__(parent)
        self._con = con
        self._db_path = db_path
        self._celdas: list[CeldaRoster] = []
        self.editando = False
        self._editor: EditorPrioridades | None = None
        # Sin foco la vista no recibe el Esc del modo edición (un QWidget no toma foco por defecto).
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QFrame()
        self._header = header
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
        self.btn_prioridades = QPushButton("▲▼ Editar prioridades")
        self.btn_prioridades.clicked.connect(self.entrar_edicion)
        if is_readonly():
            self.btn_prioridades.setEnabled(False)
            self.btn_prioridades.setToolTip("Modo solo lectura: las prioridades no se pueden guardar.")
        else:
            self.btn_prioridades.setToolTip(
                "Marcá a quién querés mejorar. La prioridad ordena las sugerencias de discos y\n"
                "bloquea sacarle un disco a un PJ para dárselo a otro de menor prioridad.")
        hl.addWidget(self.btn_prioridades)
        self._nuevo = _lbl("NUEVO", T.font_caps(6, bold=True), T.PRIO_ALTA_TINTA)
        self._nuevo.setStyleSheet(f"color: {T.PRIO_ALTA_TINTA}; background: {T.PRIO_ALTA};"
                                  " border: none; padding: 1px 4px;")
        # Alto fijo y centrado: suelto, el label tomaba el alto entero del header (56 px) y la
        # etiqueta se veía como un bloque lima vertical (primera captura).
        self._nuevo.setFixedHeight(16)
        hl.addWidget(self._nuevo, 0, Qt.AlignmentFlag.AlignVCenter)
        self.btn_declarar = QPushButton("Declarar roster…")
        self.btn_declarar.setToolTip(
            "Decí qué personajes tenés. El sistema no puede enumerar solo a los que NO tenés:\n"
            "en el menú salen en gris y el reconocedor los confunde con uno propio.")
        self.btn_declarar.clicked.connect(self._abrir_declaracion)
        hl.addWidget(self.btn_declarar)
        root.addWidget(header)
        root.addWidget(self._header_edicion())

        # Esc sale del modo edición (el diseño: "salís con Listo o Esc").
        self._esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._esc.activated.connect(self.salir_edicion)

        self._slot_filtros = QVBoxLayout()
        self._slot_filtros.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._slot_filtros)
        self.filtros: BandaFiltros | None = None

        cont = QWidget()
        cont.setObjectName("roster_cuerpo")
        self._cont = cont
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(12, 10, 12, 10)
        self.cuerpo = _Cuerpo()
        cl.addWidget(self.cuerpo)
        root.addWidget(cont, 1)

        root.addWidget(self._leyenda())
        self.refrescar()

    # --- construcción -----------------------------------------------------------------------------

    def _header_edicion(self) -> QFrame:
        """Reemplaza al header mientras dura el modo edición (handoff design_v3): tiene que ser
        obvio EN QUÉ MODO estás y CÓMO salir."""
        f = QFrame()
        f.setFixedHeight(HEADER_H)
        f.setObjectName("roster_header_edicion")
        f.setStyleSheet(f"QFrame#roster_header_edicion {{ background: rgba(196,240,58,0.07);"
                        f" border-bottom: 1px solid {T.PRIO_ALTA}; }}")
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(_lbl("Editando prioridades", T.font_display(14, bold=True), T.PRIO_ALTA))
        col.addWidget(_lbl("CADA CELDA: ▲ ALTA · – NORMAL · ▼ BAJA — SE GUARDA AL MOMENTO · "
                           "EL CLICK NO ABRE LA FICHA", T.font_caps(6), T.TEXT_SECONDARY))
        h.addLayout(col)
        self._conteos_prio = _lbl("", T.font_mono(9), T.TEXT_PRIMARY)
        h.addWidget(self._conteos_prio)
        h.addStretch()
        self._estado_prio = _lbl("", T.font_caps(7), T.TEXT_SECONDARY)
        h.addWidget(self._estado_prio)
        self.btn_listo = QPushButton("Listo  ·  Esc")
        self.btn_listo.setStyleSheet(
            f"QPushButton {{ color: {T.PRIO_ALTA_TINTA}; background: {T.PRIO_ALTA}; border: none;"
            " padding: 5px 13px; font-weight: bold; }")
        self.btn_listo.clicked.connect(self.salir_edicion)
        h.addWidget(self.btn_listo)
        f.hide()
        self._header_edit = f
        return f

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
        # Nota de la derecha: el estado vacío invita, el modo edición dice cómo salir.
        self._nota = _lbl("", T.font_caps(6), T.TEXT_MUTED)
        h.addWidget(self._nota)
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

        for c in self._celdas:
            c.deleteLater()
        self._celdas = []
        for d in celdas_datos:
            c = CeldaRoster(d)
            c.clicked.connect(self.ficha_pedida.emit)
            c.prioridad_elegida.connect(self._guardar_prioridad)
            c.set_modo_edicion(self.editando)
            self._celdas.append(c)

        if self.filtros is not None:
            self._slot_filtros.removeWidget(self.filtros)
            self.filtros.deleteLater()
        self.filtros = BandaFiltros(celdas_datos)
        self.filtros.cambiaron.connect(self._aplicar_filtros)
        self.filtros.marcar_pedido.connect(self.entrar_edicion)
        self.filtros.btn_marcar.setEnabled(self.btn_prioridades.isEnabled())
        self._slot_filtros.addWidget(self.filtros)

        self.cuerpo.set_celdas(self._celdas)
        self._actualizar_prioridad_ui()
        self._aplicar_filtros()

    # --- prioridad de buildeo -------------------------------------------------------------------

    def entrar_edicion(self) -> None:
        if self.editando or not self.btn_prioridades.isEnabled():
            return
        self.editando = True
        self._editor = EditorPrioridades(self._db_path)   # una sesión = un backup (RNF-01)
        self._estado_prio.setText("")
        self._header.hide()
        self._header_edit.show()
        self._cont.setStyleSheet("QWidget#roster_cuerpo { background: rgba(196,240,58,0.02);"
                                 " border: 1px solid rgba(196,240,58,0.27); }")
        for c in self._celdas:
            c.set_modo_edicion(True)
        self._actualizar_prioridad_ui()
        self.setFocus()

    def salir_edicion(self) -> None:
        if not self.editando:
            return
        self.editando = False
        self._editor = None
        self._header_edit.hide()
        self._header.show()
        self._cont.setStyleSheet("")
        for c in self._celdas:
            c.set_modo_edicion(False)
        self._actualizar_prioridad_ui()

    def _guardar_prioridad(self, agente_id: int, prioridad: str) -> None:
        celda = next((c for c in self._celdas if c.celda.id == agente_id), None)
        if celda is None or self._editor is None:
            return
        try:
            res = self._editor.guardar(agente_id, prioridad, celda.celda.nombre)
        except (sqlite3.Error, ValueError) as e:
            log.exception("[roster] no se pudo guardar la prioridad de %s", celda.celda.nombre)
            self._mostrar_estado(f"NO SE GUARDÓ: {e}", AMBAR)
            return
        if not res.escribio:
            self._mostrar_estado(f"NO SE GUARDÓ: {res.motivo_no_escribio}", AMBAR)
            return
        celda.set_prioridad(prioridad)
        celda.marcar_guardado()
        self._mostrar_estado(
            f"● SUGERENCIAS DE DISCOS RECALCULADAS · {datetime.now():%H:%M:%S}", T.PRIO_ALTA)  # noqa: DTZ005
        self._actualizar_prioridad_ui()
        self._aplicar_filtros()          # un PJ puede salir del filtro de prioridad activo

    def _mostrar_estado(self, texto: str, color: str) -> None:
        self._estado_prio.setText(texto)
        self._estado_prio.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _actualizar_prioridad_ui(self) -> None:
        """Todo lo que depende de los conteos de prioridad, en el lugar."""
        prio = conteos_prioridad([c.celda for c in self._celdas])
        vacio = not (prio["alta"] or prio["baja"])
        for item in self._leyenda_prio.values():
            item.setVisible(not vacio)
        self._nuevo.setVisible(vacio and self.btn_prioridades.isEnabled())
        if self.filtros is not None:
            self.filtros.actualizar_prioridad(prio)
        self._conteos_prio.setText(f"▲ {prio['alta']} alta   {prio['normal']} normal   ▼ {prio['baja']} baja")
        if self.editando:
            self._nota.setText("MODO EDICIÓN · EL CLICK NO ABRE LA FICHA · SALÍS CON LISTO O ESC")
        elif vacio and self._celdas:
            self._nota.setText("EL MOTOR DE DISCOS NO SABE A QUIÉN QUERÉS MEJORAR — "
                               f"HOY LOS {len(self._celdas)} ESTÁN EN NORMAL")
        else:
            self._nota.setText("")

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

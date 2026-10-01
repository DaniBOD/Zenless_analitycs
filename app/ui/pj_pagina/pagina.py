"""La página del PJ (SPEC 2026-09-28): ocupa el área de contenido en lugar del modal.

| banda | qué |
|---|---|
| "← {origen}" | vuelve a la vista de donde se vino (Roster, Armas o Discos); Escape también |
| portada | arte, identidad y la prioridad de buildeo (portada de `hoy.py`) |
| izquierda | HOY EN EL JUEGO: lo que mostraba el modal (`hoy.HoyEnElJuego`) |
| derecha | BUILD DECLARADA: sets, principales, secundarios y fijos que USA el motor, cada bloque con su ✎ y sus avisos debajo; al pie "↺ Volver todo a la guía" |

La página no consulta la DB: recibe `leer()`, que devuelve una `FichaPagina`. Escribe sólo con
`EditorFichaPJ`, una sesión por página (un backup por página, no por click: RNF-01).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.coherencia import AVISO, ETIQUETA_STAT, _n
from app.core.ficha_pj import NIVELES
from app.db.connection import is_readonly
from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina, avisos_por_bloque
from app.ui.pj_pagina.hoy import HoyEnElJuego, Portada, _caps, _lbl

log = logging.getLogger(__name__)

ORIGEN_BUILD = {
    "declarado": "declarado por vos",
    "equipado": "el 4pc que tiene equipado (el 2pc, el equipado o el recomendado de la guía)",
    "guia_fuera": "el primero de la guía: lo equipado no está en la guía",
    "guia_sin_4pc": "el primero de la guía: no tiene un 4pc completo",
}
ORIGEN_FIJO = {"kit": "del kit", "set": "del set", "tuyo": "tuyo"}
#: Los bloques de la build declarada, en orden: (clave, título).
BLOQUES_BUILD = (("sets", "Sets"), ("principales", "Principales"),
                 ("secundarios", "Secundarios"), ("fijos", "Stats fijos"))


class PjPagina(QWidget):
    #: bloque → clase de su ventana flotante, `cls(pagina)`. Un ✎ sin ventana queda deshabilitado.
    VENTANAS: dict[str, type] = {}

    volver_pedido = Signal()
    #: (agente_id, prioridad) al guardar una prioridad: la ventana se lo pasa al Roster.
    prioridad_cambiada = Signal(int, str)

    def __init__(self, leer: Callable[[], FichaPagina], *, editor=None, db_path=None,
                 volver_texto: str = "Roster", confirmar: Callable[[], bool] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._leer = leer
        self._db_path = db_path
        self._editor = editor
        self._confirmar = confirmar or self._confirmar_con_dialogo
        self.datos = leer()
        self.ficha = self.datos.hoy
        self.acento = T.color_elemento(self.ficha.elemento)
        self.boton_editar: dict[str, QPushButton] = {}
        self.btn_todo_guia: QPushButton | None = None
        self.mensaje: QLabel | None = None

        self.setObjectName("pj_pagina")
        self.setStyleSheet(f"QWidget#pj_pagina {{ background: {T.BG_PANEL}; }}")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        barra = QHBoxLayout()
        barra.setContentsMargins(12, 6, 12, 6)
        self.btn_volver = QPushButton(f"← {volver_texto}")
        self.btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_volver.setFont(T.font_caps(8, bold=True))
        self.btn_volver.setStyleSheet(
            f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent; border: none; padding: 4px 6px; }}"
            f"QPushButton:hover {{ color: {self.acento}; }}")
        self.btn_volver.clicked.connect(self.volver_pedido.emit)
        barra.addWidget(self.btn_volver)
        barra.addStretch()
        raiz.addLayout(barra)

        self.portada = Portada(self.ficha, self.acento, db_path)
        self.selector_prioridad = self.portada.selector_prioridad
        self.selector_prioridad.cambiada.connect(lambda p: self.prioridad_cambiada.emit(self.ficha.id, p))
        raiz.addWidget(self.portada)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        self.hoy = HoyEnElJuego(self.ficha, self.acento)
        cuerpo.addWidget(self.hoy, 3)
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {T.BORDER_SUBTLE}; border: none;")
        cuerpo.addWidget(sep)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._scroll.setWidget(self._columna_build())
        cuerpo.addWidget(self._scroll, 2)
        raiz.addLayout(cuerpo, 1)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.volver_pedido.emit)

    # --- la build declarada -------------------------------------------------------------------

    def refrescar(self) -> None:
        """Vuelve a leer la DB y reconstruye la build declarada (lo de hoy no cambia al declarar)."""
        self.datos = self._leer()
        self.boton_editar = {}
        viejo = self._scroll.takeWidget()
        if viejo is not None:
            viejo.deleteLater()
        self._scroll.setWidget(self._columna_build())

    def _columna_build(self) -> QWidget:
        w = QWidget()
        w.setObjectName("columna_build")
        w.setStyleSheet(f"QWidget#columna_build {{ background: {T.BG_PANEL}; }}")
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(10)
        f = self.datos.foto
        titulo = QHBoxLayout()
        titulo.addWidget(_caps("Build declarada", self.acento))
        titulo.addStretch()
        v.addLayout(titulo)
        if f is None:
            v.addWidget(_lbl("No se pudo leer la build declarada: el detalle quedó en el log.",
                             T.font_ui(9), T.WARNING, wrap=True))
            v.addStretch()
            return w
        n_aviso = sum(1 for a in f.avisos if a.severidad == AVISO)
        n_info = len(f.avisos) - n_aviso
        conteo = " · ".join(x for x in (f"⚠ {n_aviso}" if n_aviso else "", f"ℹ {n_info}" if n_info else "") if x)
        if conteo:
            titulo.addWidget(_lbl(conteo, T.font_ui(9, bold=True), T.WARNING if n_aviso else T.TEXT_SECONDARY))
        por_bloque = avisos_por_bloque(f.avisos)
        for a in por_bloque["otros"]:
            v.addWidget(self._aviso(a))
        lineas = {"sets": self._lineas_sets(), "principales": self._lineas_principales(),
                  "secundarios": self._lineas_secundarios(), "fijos": self._lineas_fijos()}
        for clave, nombre in BLOQUES_BUILD:
            v.addWidget(self._bloque(clave, nombre, lineas[clave], por_bloque[clave]))
        v.addStretch()
        self.btn_todo_guia = QPushButton("↺ Volver todo a la guía")
        self.btn_todo_guia.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_todo_guia.setStyleSheet(self._css_boton())
        self.btn_todo_guia.clicked.connect(self._todo_a_la_guia)
        if is_readonly():
            self.btn_todo_guia.setEnabled(False)
            self.btn_todo_guia.setToolTip("Modo sólo lectura: no se guarda nada.")
        self.mensaje = _lbl("", T.font_ui(8), T.WARNING, wrap=True)
        pie = QHBoxLayout()
        pie.addWidget(self.btn_todo_guia)
        pie.addStretch()
        v.addLayout(pie)
        v.addWidget(self.mensaje)
        return w

    def _bloque(self, clave: str, titulo: str, lineas: list[tuple[str, bool]], avisos: list) -> QFrame:
        caja = QFrame()
        caja.setObjectName(f"bloque_{clave}")
        caja.setStyleSheet(f"QFrame#bloque_{clave} {{ border: 1px solid {T.BORDER_SUBTLE};"
                           f" background: rgba(255,255,255,0.02); }}")
        v = QVBoxLayout(caja)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)
        cab = QHBoxLayout()
        cab.addWidget(_caps(titulo, T.TEXT_MUTED))
        cab.addStretch()
        b = QPushButton("✎ Editar")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(self._css_boton())
        b.clicked.connect(lambda _c=False, k=clave: self.abrir(k))
        b.setEnabled(clave in self.VENTANAS)
        self.boton_editar[clave] = b
        cab.addWidget(b)
        v.addLayout(cab)
        for texto, tuyo in lineas:
            v.addWidget(_lbl(texto, T.font_ui(9, bold=tuyo), T.TEXT_PRIMARY if tuyo else T.TEXT_SECONDARY,
                             wrap=True))
        for a in avisos:
            v.addWidget(self._aviso(a))
        return caja

    @staticmethod
    def _aviso(a) -> QWidget:
        es_aviso = a.severidad == AVISO
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 2, 0, 0)
        h.setSpacing(6)
        h.addWidget(_lbl("⚠" if es_aviso else "ℹ", T.font_ui(9, bold=True),
                         T.WARNING if es_aviso else T.TEXT_MUTED), 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(_lbl(a.texto, T.font_ui(8), T.TEXT_PRIMARY if es_aviso else T.TEXT_SECONDARY, wrap=True), 1)
        return w

    def _nombre_set(self, set_id: int | None) -> str:
        if set_id is None:
            return "sin 2pc"
        s = self.datos.sets.get(set_id)
        return s.nombre if s else f"set {set_id}"

    def _lineas_sets(self) -> list[tuple[str, bool]]:
        f = self.datos.foto
        if f.set_4p_id is None:
            return [("Sin 4pc: ni declarado, ni equipado completo, ni en la guía.", False)]
        return [(f"4pc {self._nombre_set(f.set_4p_id)} · 2pc {self._nombre_set(f.set_2p_id)}",
                 f.origen_build == "declarado"),
                (ORIGEN_BUILD.get(f.origen_build, "sin build"), False)]

    def _lineas_principales(self) -> list[tuple[str, bool]]:
        f = self.datos.foto
        out = []
        for slot in (4, 5, 6):
            valores = f.principales.get(slot) or ()
            tuyo = slot in f.eleccion.principales
            out.append((f"Slot {slot}: {' / '.join(valores) or 'sin guía'}" + (" · tuyo" if tuyo else ""), tuyo))
        return out

    def _lineas_secundarios(self) -> list[tuple[str, bool]]:
        f = self.datos.foto
        if f.guia.vacia and not f.eleccion.niveles:
            return [("Sin guía todavía: se puede declarar igual.", False)]
        out = []
        for nivel in (1, 2, 3, 4, 0):
            subs = sorted(s for s, n in f.niveles.items() if n == nivel)
            if subs:
                tuyos = [s for s in subs if s in f.eleccion.niveles]
                out.append((f"{NIVELES[nivel]}: " + ", ".join(s + (" (tuyo)" if s in tuyos else "") for s in subs),
                            bool(tuyos)))
        return out

    def _lineas_fijos(self) -> list[tuple[str, bool]]:
        if not self.datos.fijos:
            return [("Sin stats fijos.", False)]
        out = []
        for fj in self.datos.fijos:
            etiqueta = ETIQUETA_STAT.get(fj.stat, fj.stat)
            if fj.objetivo is None:
                out.append((f"{etiqueta}: desactivado (guía: {_n(fj.de_la_guia)})", True))
                continue
            origen = ORIGEN_FIJO.get(fj.origen, fj.origen)
            if fj.origen == "tuyo" and fj.de_la_guia is not None:
                origen += f" (guía: {_n(fj.de_la_guia)})"
            if fj.actual is None:
                estado, actual = "sin leer", "?"
            elif fj.actual >= fj.objetivo:
                estado, actual = "cumplido", _n(fj.actual)
            else:
                estado, actual = f"faltan {_n(round(fj.objetivo - fj.actual, 2))} · el motor lo busca", _n(fj.actual)
            out.append((f"{etiqueta}: {actual} de {_n(fj.objetivo)} · {origen} · {estado}", fj.origen == "tuyo"))
        return out

    # --- acciones -----------------------------------------------------------------------------

    def ventana(self, clave: str):
        """La ventana flotante de un bloque, armada y conectada, sin mostrar (los tests la usan así)."""
        v = self.VENTANAS[clave](self)
        v.cambio.connect(self.refrescar)
        return v

    def abrir(self, clave: str) -> None:
        """✎ de un bloque: su ventana flotante, modal. Cada cambio refresca la página."""
        if clave in self.VENTANAS:
            self.ventana(clave).exec()

    @property
    def editor(self):
        if self._editor is None:
            from app.core.ficha_pj import EditorFichaPJ
            self._editor = EditorFichaPJ(self._db_path)
        return self._editor

    def _todo_a_la_guia(self) -> None:
        if not self._confirmar():
            return
        try:
            res = self.editor.volver_a_la_guia(self.ficha.id)
        except (sqlite3.Error, ValueError) as e:
            log.exception("[pj_pagina] no se pudo volver todo a la guía (PJ %s)", self.ficha.id)
            self.mensaje.setText(f"No se guardó: {e}. Backup: {getattr(self.editor, 'backup', None)}")
            return
        if not res.escribio:
            self.mensaje.setText(f"No se guardó: {res.motivo_no_escribio}")
            return
        self.refrescar()

    def _confirmar_con_dialogo(self) -> bool:
        r = QMessageBox.question(
            self, "Volver todo a la guía",
            f"¿Borrar todas tus elecciones de {self.ficha.nombre} (sets, principales, secundarios y "
            "fijos) y volver a la guía?")
        return r == QMessageBox.StandardButton.Yes

    def _css_boton(self) -> str:
        return (f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: transparent;"
                f" border: 1px solid {T.BORDER_MID}; padding: 3px 10px; }}"
                f"QPushButton:hover {{ color: {self.acento}; border-color: {self.acento}; }}")

    # --- introspección para tests ---------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        return [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]

    def textos_de_stats(self) -> dict[str, str]:
        return self.hoy.textos_de_stats()



# Las ventanas flotantes no importan esta página (la reciben): se registran acá, al final.
from app.ui.pj_pagina.ventana_fijos import VentanaFijos  # noqa: E402
from app.ui.pj_pagina.ventana_principales import VentanaPrincipales  # noqa: E402
from app.ui.pj_pagina.ventana_secundarios import VentanaSecundarios  # noqa: E402
from app.ui.pj_pagina.ventana_sets import VentanaSets  # noqa: E402

PjPagina.VENTANAS.update(secundarios=VentanaSecundarios, sets=VentanaSets, principales=VentanaPrincipales, fijos=VentanaFijos)

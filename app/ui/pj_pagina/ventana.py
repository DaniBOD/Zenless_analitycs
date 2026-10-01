"""La ventana flotante de la página del PJ (SPEC 2026-09-28, parte 2) — lo común a las cuatro.

- Sin marco, borde del color del elemento, modal, centrada sobre la ventana.
- Cada elección se guarda EN EL MOMENTO con `EditorFichaPJ` (el de la página: un backup por página)
  y la ventana se vuelve a dibujar LEYENDO LA DB: se ve lo guardado, no lo intentado.
- Sólo lectura: una franja lo dice y los controles quedan deshabilitados.
- Si no se guarda, se dice en la ventana (con el backup si hubo excepción). Nunca un except mudo.

Cada ventana concreta implementa `armar(cuerpo, datos)` y `a_la_guia()`.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.db.connection import is_readonly
from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina, avisos_por_bloque
from app.ui.pj_pagina.hoy import _caps, _lbl

log = logging.getLogger(__name__)


class VentanaFlotante(QDialog):
    #: Se emite cada vez que algo se guardó (la página se refresca).
    cambio = Signal()
    #: Título ("SETS · ANBY") y bloque de avisos que muestra.
    TITULO = ""
    BLOQUE = ""
    ANCHO = 680

    def __init__(self, pagina):
        super().__init__(pagina)
        self.pagina = pagina
        self.agente_id = pagina.ficha.id
        self.acento = pagina.acento
        self.datos: FichaPagina | None = None
        self.cuerpo: QWidget | None = None
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedWidth(self.ANCHO)

        marco = QFrame(self)
        marco.setObjectName("ventana_ficha")
        marco.setStyleSheet(f"QFrame#ventana_ficha {{ background: {T.BG_PANEL}; border: 2px solid {self.acento}; }}")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(marco)
        v = QVBoxLayout(marco)
        v.setContentsMargins(18, 12, 18, 14)
        v.setSpacing(10)

        cab = QHBoxLayout()
        cab.addWidget(_caps(f"{self.TITULO} · {pagina.ficha.nombre}".upper(), self.acento))
        cab.addStretch()
        cerrar = QPushButton("×")
        cerrar.setFixedSize(24, 24)
        cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        cerrar.setStyleSheet(f"QPushButton {{ color: {T.TEXT_PRIMARY}; background: transparent;"
                             f" border: 1px solid {T.BORDER_MID}; }}"
                             f"QPushButton:hover {{ background: {self.acento}; color: {T.BG_BASE}; }}")
        cerrar.clicked.connect(self.accept)
        cab.addWidget(cerrar)
        v.addLayout(cab)

        self.franja_solo_lectura: QLabel | None = None
        if is_readonly():
            self.franja_solo_lectura = _lbl("Modo sólo lectura: los cambios no se guardan.",
                                            T.font_ui(9, bold=True), T.WARNING)
            self.franja_solo_lectura.setStyleSheet(
                f"color: {T.WARNING}; background: rgba(255,107,71,0.08); border: 1px solid {T.WARNING};"
                " padding: 4px 8px;")
            v.addWidget(self.franja_solo_lectura)

        self._host = QVBoxLayout()
        self._host.setSpacing(0)
        v.addLayout(self._host, 1)
        self.mensaje = _lbl("", T.font_ui(8), T.WARNING, wrap=True)
        v.addWidget(self.mensaje)

        pie = QHBoxLayout()
        self.btn_guia = QPushButton("↺ Esta parte a la guía")
        self.btn_listo = QPushButton("Listo")
        for b in (self.btn_guia, self.btn_listo):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(pagina._css_boton())
        self.btn_guia.clicked.connect(self.a_la_guia)
        self.btn_listo.clicked.connect(self.accept)
        pie.addWidget(self.btn_guia)
        pie.addStretch()
        pie.addWidget(self.btn_listo)
        v.addLayout(pie)
        if is_readonly():
            self.btn_guia.setEnabled(False)

        self.redibujar()

    # --- lo que implementa cada ventana -------------------------------------------------------

    def armar(self, cuerpo: QVBoxLayout, datos: FichaPagina) -> None:
        raise NotImplementedError

    def a_la_guia(self) -> None:
        raise NotImplementedError

    # --- lo común -----------------------------------------------------------------------------

    @property
    def editor(self):
        return self.pagina.editor

    def redibujar(self) -> None:
        """Vuelve a leer la DB y reconstruye el cuerpo."""
        self.datos = self.pagina._leer()
        if self.cuerpo is not None:
            self._host.removeWidget(self.cuerpo)
            self.cuerpo.deleteLater()
        self.cuerpo = QWidget()
        lay = QVBoxLayout(self.cuerpo)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if self.datos.foto is None:
            lay.addWidget(_lbl("No se pudo leer la build declarada: el detalle quedó en el log.",
                               T.font_ui(9), T.WARNING, wrap=True))
        else:
            self.armar(lay, self.datos)
            for a in avisos_por_bloque(self.datos.foto.avisos)[self.BLOQUE]:
                lay.addWidget(self.pagina._aviso(a))
        self._host.addWidget(self.cuerpo)
        if is_readonly():
            self.cuerpo.setEnabled(False)

    def guardar(self, accion: Callable[[], object]) -> bool:
        """Corre una escritura del editor. True si se guardó (y entonces redibuja y avisa)."""
        try:
            res = accion()
        except (sqlite3.Error, ValueError) as e:
            log.exception("[pj_pagina] no se guardó desde la ventana %s (PJ %s)", self.TITULO, self.agente_id)
            self._decir(f"No se guardó: {e}. Backup: {getattr(self.editor, 'backup', None)}")
            return False
        if res is None:                     # nada que hacer (p. ej. "a la guía" sin ajustes)
            return False
        if not res.escribio:
            self._decir(f"No se guardó: {res.motivo_no_escribio}")
            return False
        self._decir("")
        self.redibujar()
        self.cambio.emit()
        return True

    def _decir(self, texto: str) -> None:
        self.mensaje.setText(texto)

    def showEvent(self, ev):
        super().showEvent(ev)
        ventana = self.pagina.window()
        if ventana is not None and ventana is not self:
            centro = ventana.mapToGlobal(ventana.rect().center())
            self.move(centro.x() - self.width() // 2, centro.y() - self.height() // 2)

    def textos_visibles(self) -> list[str]:
        return [l.text() for l in self.findChildren(QLabel) if l.text() and not l.isHidden()]

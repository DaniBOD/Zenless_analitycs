"""La ventana de los secundarios (SPEC 2026-09-28, parte 2.3).

Cinco filas (Imprescindible / Muy bueno / Bueno / Sirve / No sirve) con los 10 secundarios como
fichas. Click en una ficha → menú con los 5 niveles y "↺ Como la guía". Borde sólido del acento si
lo movió el usuario, tenue si sigue la guía. Guarda con `EditorFichaPJ.nivel_substat`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QVBoxLayout

from app.core.ficha_pj import NIVELES
from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina
from app.ui.pj_pagina.hoy import _lbl
from app.ui.pj_pagina.ventana import VentanaFlotante

ORDEN_NIVELES = (1, 2, 3, 4, 0)


class VentanaSecundarios(VentanaFlotante):
    TITULO = "Secundarios"
    BLOQUE = "secundarios"

    def armar(self, cuerpo: QVBoxLayout, datos: FichaPagina) -> None:
        f = datos.foto
        self.fichas: dict[str, QPushButton] = {}
        self.fila_de: dict[str, int] = {}
        cuerpo.addWidget(_lbl("Click en un secundario para cambiarle el nivel. El borde sólido es tuyo;"
                              " el tenue sigue la guía.", T.font_ui(8), T.TEXT_MUTED, wrap=True))
        for nivel in ORDEN_NIVELES:
            fila = QHBoxLayout()
            fila.setSpacing(6)
            etiqueta = _lbl(NIVELES[nivel], T.font_caps(8, bold=True), T.TEXT_SECONDARY)
            etiqueta.setFixedWidth(110)
            fila.addWidget(etiqueta)
            subs = sorted(s for s, n in f.niveles.items() if n == nivel)
            if not subs:
                fila.addWidget(_lbl("—", T.font_ui(9), T.TEXT_MUTED))
            for s in subs:
                tuyo = s in f.eleccion.niveles
                b = QPushButton(s)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFont(T.font_ui(8, bold=tuyo))
                b.setStyleSheet(self.css_ficha(tuyo))
                guia = f.guia.niveles.get(s)
                b.setToolTip(f"Guía: {NIVELES.get(guia, 'No sirve') if guia is not None else 'No sirve'}")
                b.clicked.connect(lambda _c=False, sub=s, boton=b: self.menu_de(sub).exec(
                    boton.mapToGlobal(boton.rect().bottomLeft())))
                fila.addWidget(b)
                self.fichas[s] = b
                self.fila_de[s] = nivel
            fila.addStretch()
            cuerpo.addLayout(fila)

    def css_ficha(self, tuyo: bool) -> str:
        borde = f"2px solid {self.acento}" if tuyo else f"1px dashed {T.BORDER_MID}"
        tinta = T.TEXT_PRIMARY if tuyo else T.TEXT_SECONDARY
        return (f"QPushButton {{ color: {tinta}; background: rgba(255,255,255,0.03); border: {borde};"
                f" padding: 3px 8px; }} QPushButton:hover {{ border-color: {self.acento}; }}")

    def menu_de(self, substat: str) -> QMenu:
        menu = QMenu(self)
        actual = self.fila_de.get(substat)
        for nivel in ORDEN_NIVELES:
            a = QAction(NIVELES[nivel], menu)
            a.setCheckable(True)
            a.setChecked(nivel == actual)
            a.triggered.connect(lambda _c=False, n=nivel: self.elegir_nivel(substat, n))
            menu.addAction(a)
        menu.addSeparator()
        guia = QAction("↺ Como la guía", menu)
        guia.triggered.connect(lambda _c=False: self.elegir_nivel(substat, None))
        menu.addAction(guia)
        return menu

    def elegir_nivel(self, substat: str, nivel: int | None) -> bool:
        return self.guardar(lambda: self.editor.nivel_substat(self.agente_id, substat, nivel))

    def a_la_guia(self) -> None:
        tuyos = list(self.datos.foto.eleccion.niveles) if self.datos and self.datos.foto else []
        if not tuyos:
            return
        self.guardar(lambda: [self.editor.nivel_substat(self.agente_id, s, None) for s in tuyos][-1])

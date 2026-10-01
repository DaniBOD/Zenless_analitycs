"""La ventana de los sets (SPEC 2026-09-28, parte 2.1).

- 4 piezas: "Automático" (el equipado si está en la guía; si no, el primero de la guía), los 4pc de
  la guía en su orden y "Otros sets" (fuera de la guía).
- 2 piezas: los renglones de la guía para el 4pc vigente, EN ORDEN (un renglón puede traer dos sets
  equivalentes; el recomendado va marcado) y "Otros sets". El set del 4pc no se ofrece.
- Cambiar el 4pc lleva el 2pc al recomendado del renglón 1 de la guía (si la guía no tiene, sin 2pc).

Guarda con `EditorFichaPJ.build`. El vigente (el que usa el motor) va marcado con el acento.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina
from app.ui.pj_pagina.hoy import _caps, _lbl
from app.ui.pj_pagina.ventana import VentanaFlotante

NOTA_R24 = ("El orden importa: si al PJ le falta un stat fijo, el motor puede proponer cambiar el 2pc "
            "por el siguiente renglón de esta lista (de a dos discos, nunca tocando el 4pc).")


class VentanaSets(VentanaFlotante):
    TITULO = "Sets"
    BLOQUE = "sets"
    ANCHO = 760

    def armar(self, cuerpo: QVBoxLayout, datos: FichaPagina) -> None:
        f = datos.foto
        self.botones_4pc: dict[int | None, QPushButton] = {}
        self.botones_2pc: dict[int, QPushButton] = {}
        cols = QHBoxLayout()
        cols.setSpacing(18)

        c4 = QVBoxLayout()
        c4.setSpacing(4)
        c4.addWidget(_caps("4 piezas", self.acento))
        self._boton(c4, self.botones_4pc, None, "Automático", f.eleccion.set_4p_id is None, self.elegir_4pc,
                    "El equipado si está en la guía; si no, el primero de la guía.")
        for i, s in enumerate(f.guia.sets_4pc, 1):
            self._boton(c4, self.botones_4pc, s, f"{i} · {self._nombre(s)}", f.set_4p_id == s, self.elegir_4pc)
        otros_4 = [s for s in self._por_nombre() if s not in f.guia.sets_4pc]
        c4.addWidget(self._otros(otros_4, self.botones_4pc, f.set_4p_id, self.elegir_4pc))
        cols.addLayout(c4, 1)

        c2 = QVBoxLayout()
        c2.setSpacing(4)
        c2.addWidget(_caps("2 piezas", self.acento))
        s4 = f.set_4p_id
        if s4 is None:
            c2.addWidget(_lbl("Elegí primero el 4pc.", T.font_ui(9), T.TEXT_MUTED))
        else:
            renglones = datos.renglones.get(s4, [])
            en_guia = {s for r in renglones for s in r.sets}
            for r in renglones:
                fila = QHBoxLayout()
                fila.setSpacing(4)
                fila.addWidget(_lbl(f"{r.grupo} ·", T.font_mono(9), T.TEXT_MUTED))
                for s in r.sets:
                    texto = self._nombre(s) + (" (recomendado)" if s == r.recomendado else "")
                    self._boton(fila, self.botones_2pc, s, texto, f.set_2p_id == s, self.elegir_2pc)
                fila.addStretch()
                c2.addLayout(fila)
            if renglones:
                c2.addWidget(_lbl(NOTA_R24, T.font_ui(8), T.TEXT_MUTED, wrap=True))
            else:
                c2.addWidget(_lbl("La guía no trae 2pc para este 4pc.", T.font_ui(8), T.TEXT_MUTED, wrap=True))
            otros_2 = [s for s in self._por_nombre() if s not in en_guia and s != s4]
            c2.addWidget(self._otros(otros_2, self.botones_2pc, f.set_2p_id, self.elegir_2pc))
        cols.addLayout(c2, 1)
        cuerpo.addLayout(cols)

    # --- piezas -------------------------------------------------------------------------------

    def _nombre(self, s: int) -> str:
        info = self.datos.sets.get(s)
        return info.nombre if info else f"set {s}"

    def _por_nombre(self) -> list[int]:
        return sorted(self.datos.sets, key=lambda s: self.datos.sets[s].nombre)

    def _otros(self, ids: list[int], registro: dict, vigente, accion) -> QWidget:
        caja = QWidget()
        v = QVBoxLayout(caja)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(4)
        v.addWidget(_caps("Otros sets · fuera de la guía", T.TEXT_MUTED))
        lista = QWidget()
        # El viewport de un QScrollArea no hereda el fondo: sin esto, la lista sale blanca.
        lista.setObjectName("lista_sets")
        lista.setStyleSheet(f"QWidget#lista_sets {{ background: {T.BG_PANEL}; }}")
        lv = QVBoxLayout(lista)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(3)
        for s in ids:
            self._boton(lv, registro, s, self._nombre(s), vigente == s, accion, "Fuera de la guía.")
        lv.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(170)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {T.BORDER_SUBTLE}; background: transparent; }}")
        scroll.setWidget(lista)
        v.addWidget(scroll)
        return caja

    def _boton(self, layout, registro: dict, clave, texto: str, marcado: bool, accion, tip: str = "") -> None:
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(T.font_ui(8, bold=marcado))
        borde = f"2px solid {self.acento}" if marcado else f"1px solid {T.BORDER_MID}"
        b.setStyleSheet(f"QPushButton {{ color: {T.TEXT_PRIMARY if marcado else T.TEXT_SECONDARY};"
                        f" background: rgba(255,255,255,0.03); border: {borde}; padding: 3px 8px;"
                        f" text-align: left; }} QPushButton:hover {{ border-color: {self.acento}; }}")
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(lambda _c=False, k=clave: accion(k))
        layout.addWidget(b)
        registro[clave] = b

    # --- acciones -----------------------------------------------------------------------------

    def elegir_4pc(self, set_id: int | None) -> bool:
        if set_id is None:
            return self.guardar(lambda: self.editor.build(self.agente_id, None))
        renglones = self.datos.renglones.get(set_id, [])
        dos = (renglones[0].recomendado or renglones[0].sets[0]) if renglones else None
        return self.guardar(lambda: self.editor.build(self.agente_id, set_id, dos))

    def elegir_2pc(self, set_id: int) -> bool:
        s4 = self.datos.foto.set_4p_id
        if s4 is None:
            self._decir("Elegí primero el 4pc.")
            return False
        return self.guardar(lambda: self.editor.build(self.agente_id, s4, set_id))

    def a_la_guia(self) -> None:
        if self.datos and self.datos.foto and self.datos.foto.eleccion.set_4p_id is not None:
            self.guardar(lambda: self.editor.build(self.agente_id, None))

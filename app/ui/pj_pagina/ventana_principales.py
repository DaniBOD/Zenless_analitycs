"""La ventana de los principales de los slots 4, 5 y 6 (SPEC 2026-09-28, parte 2.2).

Por slot, los principales que el juego permite (en el 5, sólo el bono del elemento del PJ) como
botones que se prenden y se apagan: se pueden elegir varios. Los de la guía llevan "· guía".
Apagar el último, o dejar exactamente lo de la guía, vuelve el slot a la guía (sin fila): el
editor no acepta una lista vacía. Guarda con `EditorFichaPJ.principales`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout

from app.core.ficha_pj import principales_validos
from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina
from app.ui.pj_pagina.hoy import _caps, _lbl
from app.ui.pj_pagina.ventana import VentanaFlotante

SLOTS = (4, 5, 6)


class VentanaPrincipales(VentanaFlotante):
    TITULO = "Principales"
    BLOQUE = "principales"
    ANCHO = 720

    def armar(self, cuerpo: QVBoxLayout, datos: FichaPagina) -> None:
        f = datos.foto
        self.botones: dict[tuple[int, str], QPushButton] = {}
        cuerpo.addWidget(_lbl("Prendé los principales que te sirven en cada slot (pueden ser varios).",
                              T.font_ui(8), T.TEXT_MUTED, wrap=True))
        cols = QHBoxLayout()
        cols.setSpacing(14)
        for slot in SLOTS:
            col = QVBoxLayout()
            col.setSpacing(4)
            tuyo = slot in f.eleccion.principales
            col.addWidget(_caps(f"Slot {slot}" + (" · tuyo" if tuyo else ""), self.acento if tuyo else T.TEXT_MUTED))
            vigentes = set(f.principales.get(slot) or ())
            de_la_guia = set(f.guia.principales.get(slot, ()))
            for stat in principales_validos(slot, datos.elemento):
                prendido = stat in vigentes
                b = QPushButton(stat + (" · guía" if stat in de_la_guia else ""))
                b.setCheckable(True)
                b.setChecked(prendido)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFont(T.font_ui(8, bold=prendido))
                b.setStyleSheet(
                    f"QPushButton {{ color: {T.TEXT_SECONDARY}; background: rgba(255,255,255,0.03);"
                    f" border: 1px solid {T.BORDER_MID}; padding: 3px 8px; text-align: left; }}"
                    f"QPushButton:checked {{ color: {T.TEXT_PRIMARY}; border: 2px solid {self.acento}; }}")
                b.clicked.connect(lambda _c=False, s=slot, st=stat: self.alternar(s, st))
                col.addWidget(b)
                self.botones[(slot, stat)] = b
            guia = QPushButton("↺ como la guía")
            guia.setStyleSheet(self.pagina._css_boton())
            guia.setEnabled(tuyo)
            guia.clicked.connect(lambda _c=False, s=slot: self.slot_a_la_guia(s))
            col.addWidget(guia)
            col.addStretch()
            cols.addLayout(col, 1)
        cuerpo.addLayout(cols)

    def alternar(self, slot: int, stat: str) -> bool:
        f = self.datos.foto
        nuevo = set(f.principales.get(slot) or ())
        nuevo.symmetric_difference_update({stat})
        if not nuevo or nuevo == set(f.guia.principales.get(slot, ())):
            if slot in f.eleccion.principales:
                return self.slot_a_la_guia(slot)
            # Ya sigue la guía: nada que escribir. Se redibuja (Qt ya destildó el botón).
            self.redibujar()
            self._decir("" if nuevo else "Un slot no puede quedar sin principales: sigue la guía.")
            return False
        return self.guardar(lambda: self.editor.principales(self.agente_id, slot, sorted(nuevo)))

    def slot_a_la_guia(self, slot: int) -> bool:
        return self.guardar(lambda: self.editor.principales(self.agente_id, slot, None))

    def a_la_guia(self) -> None:
        tuyos = list(self.datos.foto.eleccion.principales) if self.datos and self.datos.foto else []
        if tuyos:
            self.guardar(lambda: [self.editor.principales(self.agente_id, s, None) for s in tuyos][-1])

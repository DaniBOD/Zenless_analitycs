"""La ventana de los stats fijos (SPEC 2026-09-28, parte 2.4).

Un renglón por fijo:
- el stat;
- su origen (del kit, del set, tuyo con "(guía: 90)");
- el objetivo editable, que guarda al terminar de editar y sólo si cambió;
- lo leído del juego y cuánto falta;
- el estado ("el motor lo busca" / "cumplido" / "sin leer");
- "desactivar" (uno de la guía) y "↺" (vuelve a la guía; en uno desactivado, "reactivar").

"+ Agregar fijo": un stat que todavía no tenga objetivo. Guarda con `EditorFichaPJ.fijo`,
`desactivar_fijo` y `fijo_de_la_guia`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QPushButton, QVBoxLayout

from app.core.coherencia import ETIQUETA_STAT, _n
from app.ui import tokens as T
from app.ui.pj_pagina.datos import FichaPagina
from app.ui.pj_pagina.hoy import _caps, _lbl
from app.ui.pj_pagina.ventana import VentanaFlotante

ORIGEN = {"kit": "del kit", "set": "del set", "tuyo": "tuyo"}
#: Los stats que acepta `ajustes_usuario_fijos` (su CHECK), en el orden de la ficha.
STATS_FIJOS = tuple(ETIQUETA_STAT)


def _spin(valor: float | None) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(2)
    s.setRange(0.01, 100000.0)
    s.setFixedWidth(96)
    if valor is not None:
        s.setValue(valor)
    return s


class VentanaFijos(VentanaFlotante):
    TITULO = "Stats fijos"
    BLOQUE = "fijos"
    ANCHO = 820

    def armar(self, cuerpo: QVBoxLayout, datos: FichaPagina) -> None:
        self.spins: dict[str, QDoubleSpinBox] = {}
        self.renglones: dict[str, str] = {}
        self.botones: dict[tuple[str, str], QPushButton] = {}
        cuerpo.addWidget(_lbl("El valor que un stat tiene que alcanzar para que una pasiva o el 4pc rinda"
                              " completo. Mientras falte, el motor lo busca.", T.font_ui(8), T.TEXT_MUTED, wrap=True))
        if not datos.fijos:
            cuerpo.addWidget(_lbl("Sin stats fijos.", T.font_ui(9), T.TEXT_SECONDARY))
        for fj in datos.fijos:
            fila = QHBoxLayout()
            fila.setSpacing(8)
            etiqueta = _lbl(ETIQUETA_STAT.get(fj.stat, fj.stat), T.font_ui(9, bold=True), T.TEXT_PRIMARY)
            etiqueta.setFixedWidth(150)
            fila.addWidget(etiqueta)
            origen = ORIGEN.get(fj.origen, fj.origen)
            if fj.origen == "tuyo" and fj.de_la_guia is not None:
                origen += f" (guía: {_n(fj.de_la_guia)})"
            o = _lbl(origen, T.font_ui(8), T.TEXT_SECONDARY)
            o.setFixedWidth(130)
            fila.addWidget(o)
            if fj.objetivo is None:
                texto = f"desactivado (guía: {_n(fj.de_la_guia)})"
                fila.addWidget(_lbl(texto, T.font_ui(9), T.TEXT_MUTED), 1)
                self.renglones[fj.stat] = texto
                self._boton(fila, fj.stat, "reactivar", lambda _c=False, s=fj.stat: self.a_la_guia_fijo(s))
            else:
                spin = _spin(fj.objetivo)
                spin.editingFinished.connect(lambda s=fj.stat, w=spin, o=fj.objetivo: (
                    self.cambiar(s, w.value()) if round(w.value(), 2) != round(o, 2) else None))
                fila.addWidget(spin)
                self.spins[fj.stat] = spin
                if fj.actual is None:
                    estado = "sin leer"
                elif fj.actual >= fj.objetivo:
                    estado = f"tiene {_n(fj.actual)} · cumplido"
                else:
                    estado = f"tiene {_n(fj.actual)} · faltan {_n(round(fj.objetivo - fj.actual, 2))} · el motor lo busca"
                fila.addWidget(_lbl(estado, T.font_ui(8), T.TEXT_PRIMARY if "busca" in estado else T.TEXT_SECONDARY), 1)
                self.renglones[fj.stat] = estado
                if fj.de_la_guia is not None:
                    self._boton(fila, fj.stat, "desactivar", lambda _c=False, s=fj.stat: self.desactivar(s))
                if fj.origen == "tuyo":
                    self._boton(fila, fj.stat, "↺", lambda _c=False, s=fj.stat: self.a_la_guia_fijo(s))
            cuerpo.addLayout(fila)

        nuevos = [s for s in STATS_FIJOS if s not in {fj.stat for fj in datos.fijos}]
        agregar = QHBoxLayout()
        agregar.setSpacing(8)
        agregar.addWidget(_caps("+ Agregar fijo", T.TEXT_MUTED))
        self.combo_nuevo = QComboBox()
        for s in nuevos:
            self.combo_nuevo.addItem(ETIQUETA_STAT[s], s)
        self.spin_nuevo = _spin(None)
        b = QPushButton("Agregar")
        b.setStyleSheet(self.pagina._css_boton())
        b.setEnabled(bool(nuevos))
        b.clicked.connect(lambda _c=False: self.agregar(self.combo_nuevo.currentData(), self.spin_nuevo.value()))
        self.btn_agregar = b
        agregar.addWidget(self.combo_nuevo)
        agregar.addWidget(self.spin_nuevo)
        agregar.addWidget(b)
        agregar.addStretch()
        cuerpo.addLayout(agregar)

    def _boton(self, fila: QHBoxLayout, stat: str, texto: str, accion) -> None:
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(self.pagina._css_boton())
        b.clicked.connect(accion)
        fila.addWidget(b)
        self.botones[(stat, texto)] = b

    # --- acciones -----------------------------------------------------------------------------

    def cambiar(self, stat: str, objetivo: float) -> bool:
        if objetivo is None or objetivo <= 0:
            self._decir("El objetivo tiene que ser mayor que 0.")
            return False
        return self.guardar(lambda: self.editor.fijo(self.agente_id, stat, float(objetivo)))

    def agregar(self, stat: str | None, objetivo: float) -> bool:
        if stat is None:
            return False
        return self.cambiar(stat, objetivo)

    def desactivar(self, stat: str) -> bool:
        return self.guardar(lambda: self.editor.desactivar_fijo(self.agente_id, stat))

    def a_la_guia_fijo(self, stat: str) -> bool:
        return self.guardar(lambda: self.editor.fijo_de_la_guia(self.agente_id, stat))

    def a_la_guia(self) -> None:
        tuyos = [fj.stat for fj in (self.datos.fijos if self.datos else ())
                 if fj.origen == "tuyo" or fj.objetivo is None]
        if tuyos:
            self.guardar(lambda: [self.editor.fijo_de_la_guia(self.agente_id, s) for s in tuyos][-1])

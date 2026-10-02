"""La sugerencia del motor en la vista en vivo (paso 8, SPEC 2026-10-01).

El controlador manda en cada payload de disco un bloque `sugerencia` ya resuelto (texto, tipo,
detalle, error). Acá sólo se pinta: la vista no consulta la DB.

- `color_de`: el color de la etiqueta, el mismo de la columna de Discos (`tokens.SUGERENCIA`). Lo
  usan la línea de la card y este recuadro: una sola definición.
- `RecuadroSugerencia`: el detalle en la región derecha (la misma función que el modal del disco,
  `detalle_sugerencia`, ya aplicada por el controlador).
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui import tokens as T


def color_de(sug: dict | None) -> str:
    if not sug:
        return T.TEXT_MUTED
    if sug.get("error"):
        return T.WARNING
    return T.SUGERENCIA.get(sug.get("tipo"), ("", T.TEXT_SECONDARY))[1] if sug.get("tipo") else T.TEXT_SECONDARY


def _lbl(texto: str, font, color: str, wrap: bool = False) -> QLabel:
    l = QLabel(texto)
    l.setFont(font)
    l.setWordWrap(wrap)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return l


class RecuadroSugerencia(QFrame):
    """El detalle de la sugerencia del disco que se ve. Oculto si el payload no trae `sugerencia`."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("recuadro_sugerencia")
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(16, 12, 16, 12)
        self._v.setSpacing(6)
        self.sugerencia: dict | None = None
        self.setVisible(False)

    def mostrar(self, sug: dict | None) -> None:
        self.sugerencia = sug
        while self._v.count():
            item = self._v.takeAt(0)
            w = item.widget()
            if w is not None:
                # Desenganchar YA: con sólo deleteLater el label viejo sigue vivo hasta el próximo
                # ciclo de eventos y se mezcla con el del disco nuevo.
                w.setParent(None)
                w.deleteLater()
        if not sug:
            self.setVisible(False)
            return
        color = color_de(sug)
        borde = color if sug.get("tipo") or sug.get("error") else T.BORDER_SUBTLE
        self.setStyleSheet(f"QFrame#recuadro_sugerencia {{ border: 1px solid {borde};"
                           f" background: rgba(255,255,255,0.02); }}")
        self._v.addWidget(_lbl("SUGERENCIA DEL MOTOR", T.font_caps(8, bold=True), T.TEXT_MUTED))
        self._v.addWidget(_lbl(sug.get("texto") or "Nada que hacer", T.font_display(14, bold=True), color,
                               wrap=True))
        for linea in sug.get("detalle") or []:
            self._v.addWidget(_lbl(linea, T.font_ui(9), T.TEXT_SECONDARY, wrap=True))
        if sug.get("tipo") in ("equipar", "mejorar", "mover"):
            self._v.addWidget(_lbl("Frente a lo que lleva hoy, sin cruzarla con las otras sugerencias "
                                   "(eso lo hace la pantalla Discos).", T.font_ui(8), T.TEXT_MUTED, wrap=True))
        self.setVisible(True)

    def textos_visibles(self) -> list[str]:
        return [l.text() for l in self.findChildren(QLabel) if l.text()]

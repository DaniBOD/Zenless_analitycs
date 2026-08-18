"""Diálogo para declarar el roster — la versión funcional, sin diseño fino todavía.

El diseño definitivo sale de Claude Design (brief en
`Documentacion/Interfaz/claude_design_upload/BRIEF_roster_y_confirmaciones_pasivas.md` §C). Esto es
lo mínimo que hace falta para que la declaración exista y se pueda usar.

Dos cosas que sí son decisiones y no provisorias:

- **Los confirmados van tildados y deshabilitados**, con el motivo en el tooltip. Un PJ con discos
  equipados es prueba de posesión: destildarlo sería declarar algo que la evidencia contradice.
- **En modo solo lectura el diálogo lo dice**, en vez de mostrar un "guardado" que no ocurrió. Un
  QA cuyo éxito es el silencio se reporta como fallo.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.roster_declaration import (
    PersonajeDeclarable,
    catalogo_declarable,
    declarar,
)

_COLUMNAS = 3
_AVATAR_PX = 28


class RosterDeclarationDialog(QDialog):
    """Selección múltiple sobre el catálogo de personajes conocidos."""

    def __init__(self, parent=None, catalogo: list[PersonajeDeclarable] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Declarar roster")
        self.setMinimumSize(760, 620)
        self._catalogo = catalogo if catalogo is not None else catalogo_declarable()
        self._checks: dict[str, QCheckBox] = {}
        self.resultado = None
        self._build()

    # --- construcción -------------------------------------------------------------------------

    def _build(self) -> None:
        v = QVBoxLayout(self)

        titulo = QLabel("¿Qué personajes tenés?")
        titulo.setStyleSheet("font-size: 15px; font-weight: bold;")
        v.addWidget(titulo)

        ayuda = QLabel(
            "El sistema no puede enumerar por su cuenta los personajes que NO tenés: en el menú "
            "salen en gris y el reconocedor los confunde con uno propio. Declaralo vos y el OCR "
            "pasa a verificar.\n"
            "Los que ya tienen discos o stats cargados vienen bloqueados: su build es prueba de "
            "que los tenés."
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color: #a8a8a8;")
        v.addWidget(ayuda)

        self._contador = QLabel()
        self._contador.setStyleSheet("font-weight: bold; padding: 4px 0;")
        v.addWidget(self._contador)

        linea = QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(linea)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        cuerpo = QWidget()
        grid = QGridLayout(cuerpo)
        grid.setContentsMargins(4, 4, 4, 4)

        for i, pj in enumerate(self._catalogo):
            grid.addWidget(self._fila(pj), i // _COLUMNAS, i % _COLUMNAS)
        grid.setRowStretch(grid.rowCount(), 1)

        scroll.setWidget(cuerpo)
        v.addWidget(scroll, 1)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Save).setText("Guardar declaración")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        v.addWidget(botones)

        self._refrescar_contador()

    def _fila(self, pj: PersonajeDeclarable) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        avatar = self._avatar(pj.nombre)
        if avatar is not None:
            h.addWidget(avatar)

        chk = QCheckBox(pj.nombre)
        chk.setChecked(pj.poseido_actual)
        if pj.bloqueado:
            chk.setEnabled(False)
            chk.setToolTip(f"No se puede destildar: {pj.motivo}")
        else:
            detalle = " · ".join(x for x in (pj.rango, pj.elemento, pj.rol) if x)
            chk.setToolTip(detalle or "Sin datos cargados todavía")
        chk.toggled.connect(self._refrescar_contador)
        self._checks[pj.nombre] = chk
        h.addWidget(chk, 1)
        return w

    def _avatar(self, nombre: str) -> QLabel | None:
        try:
            from app.core.asset_resolver import agent_avatar_path
            ruta = agent_avatar_path(nombre, variant="ico")
        except Exception:
            return None
        if not ruta or not ruta.exists():
            return None
        pix = QPixmap(str(ruta))
        if pix.isNull():
            return None
        lbl = QLabel()
        lbl.setPixmap(pix.scaled(_AVATAR_PX, _AVATAR_PX,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation))
        lbl.setFixedSize(_AVATAR_PX, _AVATAR_PX)
        return lbl

    # --- estado -------------------------------------------------------------------------------

    def seleccionados(self) -> set[str]:
        """Lo que se va a declarar.

        Los confirmados entran **siempre**, no porque su casilla esté tildada. `setEnabled(False)`
        frena el click del usuario pero no un `setChecked` programático, y la garantía que importa
        no es el estado del widget sino lo que termina escrito: un PJ con discos equipados no se
        puede declarar como no poseído por ningún camino.
        """
        bloqueados = {p.nombre for p in self._catalogo if p.bloqueado}
        return {n for n, c in self._checks.items() if c.isChecked()} | bloqueados

    def _refrescar_contador(self) -> None:
        n = len(self.seleccionados())
        total = len(self._checks)
        self._contador.setText(f"{n} declarados / {total} conocidos")

    # --- guardar ------------------------------------------------------------------------------

    def _guardar(self) -> None:
        res = declarar(self.seleccionados(), catalogo=self._catalogo)
        self.resultado = res

        if not res.escribio:
            QMessageBox.warning(
                self, "No se guardó",
                f"La declaración NO se escribió en la base.\n\nMotivo: {res.motivo_no_escribio}",
            )
            return

        detalle = [res.resumen()]
        if res.creados:
            detalle.append(
                "\nSe crearon filas mínimas (sin stats) para:\n  · " + "\n  · ".join(res.creados)
                + "\n\nHay que correrles el onboarding para completarlas.")
        if res.marcados:
            detalle.append(
                "\nQuedaron marcados como NO declarados (no se borró ninguno):\n  · "
                + "\n  · ".join(res.marcados))
        QMessageBox.information(self, "Declaración guardada", "\n".join(detalle))
        self.accept()

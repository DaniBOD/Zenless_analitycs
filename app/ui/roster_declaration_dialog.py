"""Editor de roster — Parte C del diseño v1.

Especificación: `Documentacion/Interfaz/mockups/design_v1_roster_y_pasivas/README.md` §1.
El original es React; acá se porta lo que **significa** algo (los tres estados, el bloqueo con su
motivo, los conteos, la leyenda) y se dejan los chamfers, los glows compuestos y las animaciones,
que Qt no reproduce y que forzados quedan peor.

Tres reglas que no son cosméticas:

- **Los confirmados no se pueden destildar**, y el bloqueo se hace cumplir en `seleccionados()`,
  no en el widget: `setEnabled(False)` frena el click del usuario, no el código.
- **El tooltip del bloqueo dice cómo salir** ("borrá su build en la pestaña Discos"). Un control
  deshabilitado sin salida se lee como un callejón.
- **En modo solo lectura el diálogo lo dice**, en vez de mostrar un guardado que no ocurrió.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.roster_declaration import (
    CONFIRMADO,
    DECLARADO,
    NO_OBTENIDO,
    PersonajeDeclarable,
    catalogo_declarable,
    declarar,
)

# Paleta del documento de diseño (`window.PV` + tokens.css).
ACCENT = "#B06FF0"      # confirmado — violeta
ACCENT_SOFT = "#DCC0FB"
AMBER = "#F0AA3C"       # declarado
GREY = "#6B6376"        # no obtenido
TEXT_PRIMARY = "#F4F1F7"
TEXT_SECONDARY = "#BFB8C9"
TEXT_MUTED = "#948CA0"
TEXT_DIM = "#736B80"
BG_DEEP = "#1C1A20"
BG_PANEL = "#2C2833"
BORDER_SUBTLE = "#413B4A"

TONO = {CONFIRMADO: ACCENT, DECLARADO: AMBER, NO_OBTENIDO: GREY}
ETIQUETA = {CONFIRMADO: "CONFIRMADO", DECLARADO: "DECLARADO", NO_OBTENIDO: "NO OBTENIDO"}
_ORDEN = {CONFIRMADO: 0, DECLARADO: 1, NO_OBTENIDO: 2}

COLUMNAS = 10
CELDA_W, CELDA_H = 122, 96
AVATAR_PX = 32


def _caps(txt: str, size: float, color: str, *, bold: bool = True) -> QLabel:
    lbl = QLabel(txt.upper())
    f = QFont("Saira Condensed" if bold else "Saira")
    f.setPointSizeF(size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color};")
    return lbl


class _Celda(QFrame):
    """La celda 122×96 del diseño: check + avatar + nombre + estado + motivo."""

    def __init__(self, pj: PersonajeDeclarable, parent=None):
        super().__init__(parent)
        self.pj = pj
        color = TONO.get(pj.estado, GREY)
        borde = "dashed" if pj.estado == NO_OBTENIDO else "solid"
        fondo = {
            CONFIRMADO: "rgba(176,111,240,0.08)",
            DECLARADO: "rgba(240,170,60,0.07)",
        }.get(pj.estado, "rgba(255,255,255,0.015)")
        self.setFixedSize(CELDA_W, CELDA_H)
        self.setStyleSheet(
            f"_Celda {{ background: {fondo}; border: 1px {borde} {color}; }}")

        v = QVBoxLayout(self)
        v.setContentsMargins(7, 6, 7, 5)
        v.setSpacing(2)

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        self.check = QCheckBox()
        self.check.setChecked(pj.poseido_actual)
        self.check.setStyleSheet(
            f"QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {color}; }}"
            f"QCheckBox::indicator:checked {{ background: {color}; }}"
            f"QCheckBox::indicator:unchecked {{ background: rgba(0,0,0,0.35); }}"
        )
        if pj.bloqueado:
            self.check.setEnabled(False)
            self.check.setText("🔒")
            self.check.setToolTip(pj.tooltip_bloqueo())
        fila.addWidget(self.check)
        fila.addStretch()
        avatar = self._avatar(pj)
        if avatar is not None:
            fila.addWidget(avatar)
        v.addLayout(fila)

        nombre = QLabel(pj.nombre)
        f = QFont("Saira Condensed")
        f.setPointSizeF(9.5)
        f.setBold(True)
        nombre.setFont(f)
        nombre.setWordWrap(True)
        nombre.setStyleSheet(
            f"color: {TEXT_MUTED if pj.estado == NO_OBTENIDO else TEXT_PRIMARY};")
        v.addWidget(nombre)

        if pj.variante_de:
            v.addWidget(_caps(f"atuendo · {pj.variante_de}", 6.0, ACCENT_SOFT))

        v.addStretch()
        v.addWidget(_caps(ETIQUETA.get(pj.estado, "?"), 6.0, color))

        if pj.grafia_en_conflicto:
            det = QLabel("grafía en conflicto")
            det.setStyleSheet(f"color: {AMBER}; font-size: 8px;")
            v.addWidget(det)
        elif pj.motivo:
            det = QLabel(pj.motivo)
            det.setWordWrap(True)
            det.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8px;")
            v.addWidget(det)

    @staticmethod
    def _avatar(pj: PersonajeDeclarable) -> QLabel | None:
        try:
            from app.core.asset_resolver import agent_avatar_path
            ruta = agent_avatar_path(pj.nombre, variant="ico")
        except Exception:
            return None
        if not ruta or not ruta.exists():
            return None
        pix = QPixmap(str(ruta))
        if pix.isNull():
            return None
        pix = pix.scaled(AVATAR_PX, AVATAR_PX, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        if not pj.en_agents:
            # El diseño los pone en grayscale + brightness(.6): "no lo tenés" tiene que leerse
            # antes que el nombre.
            img = pix.toImage().convertToFormat(pix.toImage().Format.Format_ARGB32)
            for y in range(img.height()):
                for x in range(img.width()):
                    c = QColor(img.pixelColor(x, y))
                    g = int(c.lightness() * 0.6)
                    img.setPixelColor(x, y, QColor(g, g, g, c.alpha()))
            pix = QPixmap.fromImage(img)
        lbl = QLabel()
        lbl.setPixmap(pix)
        lbl.setFixedSize(AVATAR_PX, AVATAR_PX)
        return lbl


class RosterDeclarationDialog(QDialog):
    """Editor de roster — Parte C del diseño v1."""

    def __init__(self, parent=None, catalogo: list[PersonajeDeclarable] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Editar roster")
        self.resize(1320, 820)
        self._catalogo = catalogo if catalogo is not None else catalogo_declarable()
        self._celdas: dict[str, _Celda] = {}
        self.resultado = None
        self.setStyleSheet(f"QDialog {{ background: {BG_DEEP}; }}")
        self._build()

    # --- construcción -------------------------------------------------------------------------

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._header())
        v.addWidget(self._barra_conteos())
        v.addWidget(self._cuerpo(), 1)
        v.addWidget(self._leyenda())
        self._refrescar_contador()

    def _header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_PANEL}; border-bottom: 1px solid {BORDER_SUBTLE};")
        h = QHBoxLayout(w)
        h.setContentsMargins(18, 11, 18, 11)
        h.setSpacing(14)

        titulo = QLabel("Editar roster")
        f = QFont("Saira Condensed")
        f.setPointSizeF(17)
        f.setBold(True)
        titulo.setFont(f)
        titulo.setStyleSheet(f"color: {TEXT_PRIMARY};")
        h.addWidget(titulo)
        h.addWidget(_caps("censo declarado", 7.5, TEXT_MUTED))

        bajada = QLabel(
            "Tildá los personajes que tenés. Esto le da al sistema el <b>denominador</b> que la "
            "observación no puede deducir. No inventa datos: los que falten arrancan el onboarding."
        )
        bajada.setWordWrap(True)
        bajada.setMaximumWidth(480)
        bajada.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border-left: 1px solid {BORDER_SUBTLE};"
            " padding-left: 14px;")
        h.addWidget(bajada)
        h.addStretch()

        cancelar = QPushButton("Cancelar")
        cancelar.setStyleSheet(
            f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent;"
            f" border: 1px solid {BORDER_SUBTLE}; padding: 6px 14px; }}")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar censo")
        guardar.setStyleSheet(
            f"QPushButton {{ color: #241A08; background: {ACCENT}; border: none;"
            " padding: 6px 16px; font-weight: bold; }}")
        guardar.clicked.connect(self._guardar)
        h.addWidget(cancelar)
        h.addWidget(guardar)
        return w

    def _barra_conteos(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_DEEP}; border-bottom: 1px solid {BORDER_SUBTLE};")
        h = QHBoxLayout(w)
        h.setContentsMargins(18, 8, 18, 8)
        h.setSpacing(10)
        h.addWidget(_caps("mostrar", 7.0, TEXT_DIM))
        for etiqueta, estado, color in (
            ("Todos", None, TEXT_SECONDARY),
            ("Confirmados por evidencia", CONFIRMADO, ACCENT),
            ("Declarados", DECLARADO, AMBER),
            ("No obtenidos", NO_OBTENIDO, GREY),
        ):
            n = (len(self._catalogo) if estado is None
                 else sum(1 for p in self._catalogo if p.estado == estado))
            chip = QLabel(f"  {etiqueta}  {n}  ")
            chip.setStyleSheet(
                f"color: {color}; font-size: 11px; border: 1px solid {BORDER_SUBTLE};"
                " padding: 3px 2px;")
            h.addWidget(chip)
        h.addStretch()
        self._contador = QLabel()
        self._contador.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        h.addWidget(self._contador)
        return w

    def _cuerpo(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {BG_DEEP};")
        cuerpo = QWidget()
        grid = QGridLayout(cuerpo)
        grid.setContentsMargins(18, 12, 18, 12)
        grid.setSpacing(6)

        # Orden del diseño: confirmado → declarado → no obtenido, y dentro alfabético.
        orden = sorted(self._catalogo,
                       key=lambda p: (_ORDEN.get(p.estado, 9), p.nombre.lower()))
        for i, pj in enumerate(orden):
            celda = _Celda(pj)
            celda.check.toggled.connect(self._refrescar_contador)
            self._celdas[pj.nombre] = celda
            grid.addWidget(celda, i // COLUMNAS, i % COLUMNAS)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(cuerpo)
        return scroll

    def _leyenda(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_DEEP}; border-top: 1px solid {BORDER_SUBTLE};")
        h = QHBoxLayout(w)
        h.setContentsMargins(18, 6, 18, 6)
        h.setSpacing(18)
        for color, txt in (
            (ACCENT, "confirmado por evidencia — check bloqueado"),
            (AMBER, "declarado — destildable"),
            (GREY, "no obtenido"),
        ):
            punto = QLabel("■")
            punto.setStyleSheet(f"color: {color}; font-size: 11px;")
            h.addWidget(punto)
            h.addWidget(_caps(txt, 6.5, TEXT_MUTED, bold=False))
        h.addStretch()
        h.addWidget(_caps(
            "la declaración es la tercera fuente de confirmación — no reemplaza a la evidencia",
            6.5, TEXT_DIM, bold=False))
        return w

    # --- estado -------------------------------------------------------------------------------

    @property
    def _checks(self) -> dict[str, QCheckBox]:
        """Compatibilidad con los tests y con quien inspeccione el diálogo."""
        return {n: c.check for n, c in self._celdas.items()}

    def seleccionados(self) -> set[str]:
        """Lo que se va a declarar.

        Los confirmados entran **siempre**, no porque su casilla esté tildada. `setEnabled(False)`
        frena el click del usuario pero no un `setChecked` programático, y la garantía que importa
        no es el estado del widget sino lo que termina escrito: un PJ con discos equipados no se
        puede declarar como no poseído por ningún camino.
        """
        bloqueados = {p.nombre for p in self._catalogo if p.bloqueado}
        return {n for n, c in self._celdas.items() if c.check.isChecked()} | bloqueados

    def _refrescar_contador(self) -> None:
        n = len(self.seleccionados())
        filas = sum(1 for p in self._catalogo if p.en_agents)
        self._contador.setText(f"{n} DECLARADOS · {filas} FILAS EN AGENTS")

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
                + "\n\nNo se inventó nada: hay que correrles el onboarding de 8 pasos.")
        if res.marcados:
            detalle.append(
                "\nQuedaron marcados como NO declarados (no se borró ninguno):\n  · "
                + "\n  · ".join(res.marcados)
                + "\n\nEs la señal más fuerte de una fila espuria, pero la arbitrás vos.")
        QMessageBox.information(self, "Censo guardado", "\n".join(detalle))
        self.accept()

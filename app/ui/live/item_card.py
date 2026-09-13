"""La card del último ítem leído — columna izquierda de la vista en vivo.

Recibe **un diccionario y se pinta**. No consulta la DB ni habla con el monitor: el build del PJ le
llega ya resuelto. Por eso se testea offscreen sin juego ni DB.

Cuatro formas, según lo que se VIO:

| entrada | forma |
|---|---|
| nada todavía | "esperando" |
| disco con dueño en pantalla | hexágono con el build de ese PJ + el disco |
| disco sin dueño (drop nuevo, libre, dueño incierto, badge sin leer) | el disco solo |
| W-Engine | ícono, los campos del arma y su dueño |

La tenencia se dice con palabras distintas para cada caso, y ninguna afirma más de lo que se sabe:
"sin identificar" no es "libre", y "no se pudo leer" no es ninguna de las dos.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui import tokens as T
from app.ui.live.hexagon import BuildHexagon

#: Cómo se dice cada tenencia. Una línea por caso, sin colapsar ninguno.
TENENCIA_TEXTO: dict[str, tuple[str, str]] = {
    "equipada": ("EQUIPADO",                 T.POSITIVE),
    "libre":    ("LIBRE",                    T.INFO),
    "nuevo":    ("NUEVO · RECIÉN OBTENIDO",  T.YELLOW),
    "incierto": ("CON DUEÑO · SIN IDENTIFICAR", T.TEXT_SECONDARY),
    "sin_leer": ("DUEÑO · NO SE PUDO LEER",  T.TEXT_MUTED),
}

_RAREZA_COLOR = {"S": T.YELLOW, "A": T.PURPLE, "B": T.INFO}


def _lbl(texto: str = "", font=None, color: str = T.TEXT_PRIMARY, wrap: bool = False) -> QLabel:
    l = QLabel(texto)
    if font is not None:
        l.setFont(font)
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    l.setWordWrap(wrap)
    return l


def _fmt_valor(valor, unidad) -> str:
    if valor is None:
        return ""
    return f"{valor:g}{'%' if unidad == '%' else ''}"


class _Fila(QFrame):
    """Una fila nombre ··· valor, como las del panel de atributos del juego."""

    def __init__(self, nombre: str, valor: str, destacada: bool = False):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: {T.YELLOW_TINT if destacada else 'transparent'};"
            f" border-bottom: 1px solid {T.BORDER_SUBTLE}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        self.nombre = _lbl(nombre, T.font_ui(10, bold=destacada),
                           T.TEXT_PRIMARY if destacada else T.TEXT_SECONDARY)
        self.valor = _lbl(valor, T.font_mono(10), T.YELLOW if destacada else T.TEXT_PRIMARY)
        lay.addWidget(self.nombre, 1)
        lay.addWidget(self.valor, 0)


def _seccion(titulo: str) -> QLabel:
    l = _lbl(titulo, T.font_caps(7, bold=True), T.TEXT_MUTED)
    l.setStyleSheet(
        f"color: {T.TEXT_MUTED}; background: {T.BG_DEEP}; padding: 6px 12px; border: none;"
    )
    return l


class ItemCard(QFrame):
    """`mostrar_disco(payload, build)` · `mostrar_arma(payload)` · `vaciar()`."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("item_card")
        self.setStyleSheet(
            f"QFrame#item_card {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER_SUBTLE};"
            f" border-radius: 4px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # cabecera: qué es + tenencia
        cab = QFrame()
        cab.setStyleSheet(f"QFrame {{ border-bottom: 1px solid {T.BORDER_SUBTLE}; }}")
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(12, 8, 12, 8)
        barra = QFrame()
        barra.setFixedSize(3, 14)
        barra.setStyleSheet(f"background: {T.YELLOW}; border: none;")
        self._tipo = _lbl("CAPTURA EN VIVO", T.font_caps(8, bold=True), T.TEXT_PRIMARY)
        self._tenencia = _lbl("", T.font_caps(7, bold=True), T.TEXT_MUTED)
        cl.addWidget(barra)
        cl.addWidget(self._tipo, 1)
        cl.addWidget(self._tenencia, 0)
        root.addWidget(cab)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self._pag_vacia = self._construir_vacia()
        self._pag_disco = QWidget()
        self._pag_arma = QWidget()
        for pag in (self._pag_vacia, self._pag_disco, self._pag_arma):
            self._stack.addWidget(pag)
        self._construir_disco()
        self._construir_arma()
        self.vaciar()

    # --- páginas ------------------------------------------------------------------------------

    def _construir_vacia(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        t = _lbl("Esperando una lectura", T.font_display(13), T.TEXT_MUTED)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = _lbl("Abrí un disco o un W-Engine en el juego.", T.font_ui(9), T.TEXT_DIM)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addStretch(1)
        return w

    def _construir_disco(self) -> None:
        lay = QVBoxLayout(self._pag_disco)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tope = QWidget()
        tl = QVBoxLayout(tope)
        tl.setContentsMargins(14, 12, 14, 6)
        tl.setSpacing(2)
        fila = QHBoxLayout()
        self._d_set = _lbl("", T.font_display(16, bold=True), T.YELLOW, wrap=True)
        self._d_rareza = _lbl("", T.font_display(11, bold=True), T.BG_BASE)
        self._d_rareza.setFixedSize(24, 24)
        self._d_rareza.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila.addWidget(self._d_set, 1)
        fila.addWidget(self._d_rareza, 0, Qt.AlignmentFlag.AlignTop)
        tl.addLayout(fila)
        self._d_meta = _lbl("", T.font_ui(9), T.TEXT_SECONDARY)
        tl.addWidget(self._d_meta)
        self._d_dueno = _lbl("", T.font_ui(10, bold=True), T.TEXT_PRIMARY)
        tl.addWidget(self._d_dueno)
        lay.addWidget(tope)

        self._hex = BuildHexagon(230)
        self._hex_cont = QWidget()
        hl = QHBoxLayout(self._hex_cont)
        # 18 abajo: la pastilla de nivel de los slots 3 y 4 cuelga bajo el hexágono y tocaba la sección.
        hl.setContentsMargins(0, 4, 0, 18)
        hl.addStretch(1)
        hl.addWidget(self._hex)
        hl.addStretch(1)
        lay.addWidget(self._hex_cont)

        lay.addWidget(_seccion("ATRIBUTO PRINCIPAL"))
        self._d_main = _Fila("", "", destacada=True)
        lay.addWidget(self._d_main)
        lay.addWidget(_seccion("ATRIBUTOS SECUNDARIOS"))
        self._d_subs_cont = QWidget()
        self._d_subs = QVBoxLayout(self._d_subs_cont)
        self._d_subs.setContentsMargins(0, 0, 0, 0)
        self._d_subs.setSpacing(0)
        lay.addWidget(self._d_subs_cont)
        lay.addStretch(1)

    def _construir_arma(self) -> None:
        lay = QVBoxLayout(self._pag_arma)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        arriba = QHBoxLayout()
        self._a_icono = QLabel()
        self._a_icono.setFixedSize(96, 96)
        self._a_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._a_icono.setStyleSheet(
            f"background: {T.BG_BASE}; border: 1px solid {T.BORDER_SUBTLE}; border-radius: 4px;"
            f" color: {T.TEXT_DIM};"
        )
        arriba.addWidget(self._a_icono)
        col = QVBoxLayout()
        col.setSpacing(4)
        self._a_nombre = _lbl("", T.font_display(15, bold=True), T.YELLOW, wrap=True)
        self._a_meta = _lbl("", T.font_ui(9), T.TEXT_SECONDARY)
        self._a_catalogo = _lbl("", T.font_ui(8), T.WARNING, wrap=True)
        col.addWidget(self._a_nombre)
        col.addWidget(self._a_meta)
        col.addWidget(self._a_catalogo)
        col.addStretch(1)
        arriba.addLayout(col, 1)
        lay.addLayout(arriba)
        lay.addWidget(_seccion("ESTADÍSTICA"))
        self._a_stat = _Fila("", "")
        lay.addWidget(self._a_stat)
        lay.addWidget(_seccion("DUEÑO"))
        self._a_dueno = _lbl("", T.font_ui(11, bold=True), T.TEXT_PRIMARY)
        self._a_dueno.setContentsMargins(12, 6, 12, 6)
        lay.addWidget(self._a_dueno)
        lay.addStretch(1)

    # --- API ----------------------------------------------------------------------------------

    def modo(self) -> str:
        """'vacio' | 'disco_con_dueno' | 'disco_sin_dueno' | 'arma' — lo que está a la vista."""
        return self._modo

    def vaciar(self) -> None:
        self._modo = "vacio"
        self._tipo.setText("CAPTURA EN VIVO")
        self._set_tenencia(None)
        self._stack.setCurrentWidget(self._pag_vacia)

    def _set_tenencia(self, clave: str | None) -> None:
        if clave is None:
            self._tenencia.setText("")
            return
        texto, color = TENENCIA_TEXTO.get(clave, TENENCIA_TEXTO["sin_leer"])
        self._tenencia.setText(texto)
        self._tenencia.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def _set_rareza(self, lbl: QLabel, rareza: str | None) -> None:
        if rareza not in _RAREZA_COLOR:
            lbl.setText("")
            lbl.setVisible(False)
            return
        lbl.setVisible(True)
        lbl.setText(rareza)
        lbl.setStyleSheet(
            f"color: {T.BG_BASE}; background: {_RAREZA_COLOR[rareza]}; border: none;"
            f" border-radius: 3px;"
        )

    def mostrar_disco(self, d: dict, build: dict[int, dict] | None = None) -> None:
        """`d` con la forma del payload de `disc_observed`. `build` = slots del dueño (o None)."""
        dueno = d.get("dueno")
        tenencia = d.get("tenencia") or "sin_leer"
        self._modo = "disco_con_dueno" if dueno else "disco_sin_dueno"
        self._tipo.setText("DISCO")
        self._set_tenencia(tenencia)

        slot = d.get("slot") or 0
        self._d_set.setText(f"{d.get('set') or '?'}  ({slot})" if slot else (d.get("set") or "?"))
        self._set_rareza(self._d_rareza, d.get("rareza"))
        nivel = d.get("nivel")
        partes = [f"Slot {slot}" if slot else "Slot ?",
                  f"Nivel {nivel}/15" if nivel is not None else "Nivel ?"]
        if d.get("set_tier") in (2, 4):
            partes.append(f"{d['set_tier']}pc activo")
        self._d_meta.setText(" · ".join(partes))
        self._d_dueno.setText(f"En {dueno}" if dueno else "")
        self._d_dueno.setVisible(bool(dueno))

        self._hex_cont.setVisible(bool(dueno))
        if dueno:
            self._hex.set_build(build or {}, destacado=slot or None, centro=d.get("dueno_avatar"))

        self._d_main.nombre.setText(d.get("main") or "?")
        self._d_main.valor.setText(_fmt_valor(d.get("main_valor"), d.get("main_unidad")))
        while self._d_subs.count():
            item = self._d_subs.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for sub in d.get("subs_detail") or []:
            self._d_subs.addWidget(_Fila(sub, ""))
        self._stack.setCurrentWidget(self._pag_disco)

    def mostrar_arma(self, a: dict) -> None:
        """`a` con la forma del payload de `weapon_seen`."""
        self._modo = "arma"
        self._tipo.setText("W-ENGINE")
        tenencia = a.get("tenencia") or "incierto"
        dueno = a.get("dueno")
        if dueno:
            tenencia = "equipada"
        self._set_tenencia(tenencia)

        self._a_nombre.setText(a.get("nombre") or "—")
        partes = []
        if a.get("rareza") in _RAREZA_COLOR:
            partes.append(f"Rango {a['rareza']}")
        nivel, nmax = a.get("nivel"), a.get("nivel_max")
        if nivel is not None:
            partes.append(f"Nivel {nivel}/{nmax}" if nmax else f"Nivel {nivel}")
        ref = a.get("refinamiento")
        partes.append(f"P{ref}" if ref else "P?")
        self._a_meta.setText(" · ".join(partes))
        self._a_catalogo.setText("" if a.get("en_catalogo", True)
                                 else "Fuera del catálogo: nombre tal cual lo leyó el OCR")
        self._a_catalogo.setVisible(not a.get("en_catalogo", True))

        stat = a.get("stat") or ""
        self._a_stat.nombre.setText(stat or "—")

        texto, _color = TENENCIA_TEXTO.get(tenencia, TENENCIA_TEXTO["incierto"])
        self._a_dueno.setText(dueno if dueno else texto.capitalize())

        icono = a.get("icono")
        pm = QPixmap(icono) if icono and Path(icono).exists() else None
        if pm is not None and not pm.isNull():
            self._a_icono.setPixmap(pm.scaled(88, 88, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        else:
            self._a_icono.clear()
            self._a_icono.setText("sin ícono")
        self._stack.setCurrentWidget(self._pag_arma)

    # --- lecturas para tests ------------------------------------------------------------------

    def textos_visibles(self) -> list[str]:
        """Los textos de la página a la vista (los labels no ocultos)."""
        pagina = self._stack.currentWidget()
        out = [self._tipo.text(), self._tenencia.text()]
        for l in pagina.findChildren(QLabel):
            if not l.isHidden() and l.text():
                out.append(l.text())
        return [t for t in out if t]

    def hexagono(self) -> BuildHexagon | None:
        return self._hex if self._modo == "disco_con_dueno" else None

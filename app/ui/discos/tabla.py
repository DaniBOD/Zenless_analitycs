"""El modelo de la tabla de discos — `QAbstractTableModel` sobre `FilaDisco`.

El filtro NO vive acá: la vista le pasa ya filtradas las filas (`datos.filtrar`). Así hay una sola
definición de qué pasa un filtro, compartida con los tests puros. El modelo sólo ordena y pinta.

Íconos en caché por set y por PJ, no por fila: 385 filas con su logo y su avatar son 385 lecturas
de disco si se cargan en `data()`.

La columna SUGERENCIA (SPEC 2026-09-27) va donde el mockup tenía SCORE. Sus datos llegan después
que las filas (se calculan en otro hilo): `set_sugerencias` los guarda y la vista recarga las filas.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QPixmap

from app.core.asset_resolver import agent_avatar_path, set_logo_path
from app.ui import tokens as T
from app.ui.discos.datos import FilaDisco, formatear_valor, subs_texto, texto_sugerencia
from app.ui.live.item_card import TENENCIA_TEXTO

#: Nivel de un disco que no está en 15: se tiñe, como el nivel ≠ 60 del Roster.
AMBAR_NIVEL = "#F0AA3C"
#: Lo que se muestra cuando el nivel NO se leyó (NULL). Un 0 diría que el disco está en Nivel 0,
#: que es un estado real y distinto — la misma separación que Armas hace con "sin leer".
NIVEL_SIN_LEER = "—"
ICONO = 18

COLUMNAS = ["#ID", "SET", "SL", "MAIN", "SUBS", "ROLLS", "NV", "SUGERENCIA", "ASIGNADO A", "ESTADO"]
C_ID, C_SET, C_SLOT, C_MAIN, C_SUBS, C_ROLLS, C_NV, C_SUG, C_DUENO, C_ESTADO = range(len(COLUMNAS))
#: Mientras el motor calcula (en otro hilo), la celda dice esto.
CALCULANDO = "…"


def _orden_sugerencia(sd) -> tuple:
    """Por tipo, en el orden de `TIPOS`; dentro del tipo, la de más mejora primero; sin nada, al final."""
    from app.core.sugerencias import TIPOS
    if sd is None or sd.propia is None:
        return (len(TIPOS) + (0 if sd is not None else 1), 0.0)
    s = sd.propia
    return (TIPOS.index(s["tipo"]) if s["tipo"] in TIPOS else len(TIPOS), -(s.get("delta") or 0.0))


def _clave_orden(col: int, sugerencias: dict):
    return {
        C_SUG: lambda f: _orden_sugerencia(sugerencias.get(f.id)),
        C_ID: lambda f: f.id,
        C_SET: lambda f: ((f.set or "").casefold(), f.slot),
        C_SLOT: lambda f: (f.slot, (f.set or "").casefold()),
        C_MAIN: lambda f: ((f.main or "").casefold(), f.main_valor or 0),
        C_SUBS: lambda f: len(f.subs),
        C_ROLLS: lambda f: f.rolls_total,
        C_NV: lambda f: (-1 if f.nivel is None else f.nivel, f.id),
        C_DUENO: lambda f: (f.dueno is None, (f.dueno or "").casefold()),
        C_ESTADO: lambda f: (f.libre, f.id),
    }[col]


class ModeloDiscos(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas: list[FilaDisco] = []
        self._orden: tuple[int, Qt.SortOrder] = (C_SET, Qt.SortOrder.AscendingOrder)
        self._iconos: dict[str, QPixmap | None] = {}
        #: {disc_id: SugerenciaDisco}; None = todavía no llegaron (se muestra CALCULANDO).
        self._sug: dict | None = None

    # --- datos ------------------------------------------------------------------------------------

    def set_sugerencias(self, sugerencias: dict | None) -> None:
        """Sólo guarda: quien llama carga las filas después (`set_filas`), y eso reordena y
        repinta. La vista lo hace siempre (`_aplicar_filtros`), porque el filtro de sugerencia
        también cambia con el resultado."""
        self._sug = sugerencias

    def sugerencia(self, row: int):
        return (self._sug or {}).get(self._filas[row].id)

    def set_filas(self, filas: list[FilaDisco]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self._ordenar()
        self.endResetModel()

    def fila(self, row: int) -> FilaDisco:
        return self._filas[row]

    def ids(self) -> list[int]:
        return [f.id for f in self._filas]

    # --- Qt ---------------------------------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNAS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[section]
        return None

    def _icono(self, clave: str, path) -> QPixmap | None:
        if clave not in self._iconos:
            pm = None
            if path is not None:
                p = QPixmap(str(path))
                if not p.isNull():
                    pm = p.scaled(ICONO, ICONO, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            self._iconos[clave] = pm
        return self._iconos[clave]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        f = self._filas[index.row()]
        col = index.column()
        if col == C_SUG:
            return self._data_sugerencia(f, role)
        if role == Qt.ItemDataRole.DisplayRole:
            return {
                C_ID: f"#{f.id:05d}",
                C_SET: f.set or "—",
                C_SLOT: str(f.slot),
                C_MAIN: f"{f.main or '—'} {formatear_valor(f.main_valor, f.main_unidad)}",
                C_SUBS: subs_texto(f),
                C_ROLLS: str(f.rolls_total),
                C_NV: NIVEL_SIN_LEER if f.nivel is None else str(f.nivel),
                C_DUENO: f.dueno or "—",
                C_ESTADO: TENENCIA_TEXTO["equipada" if f.equipado else "libre"][0],
            }[col]
        if role == Qt.ItemDataRole.ToolTipRole and col == C_SUBS:
            return subs_texto(f, sep="\n")
        if role == Qt.ItemDataRole.DecorationRole:
            if col == C_SET:
                return self._icono(f"set:{f.set_en}", set_logo_path(f.set_en))
            if col == C_DUENO and f.dueno:
                return self._icono(f"pj:{f.dueno}", agent_avatar_path(f.dueno, "ico"))
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == C_ESTADO:
                return QBrush(QColor(TENENCIA_TEXTO["equipada" if f.equipado else "libre"][1]))
            if col == C_NV and f.nivel is None:
                return QBrush(QColor(T.TEXT_DIM))        # sin leer ≠ nivel bajo
            if col == C_NV and f.nivel != 15:
                return QBrush(QColor(AMBAR_NIVEL))
            if col == C_ID:
                return QBrush(QColor(T.TEXT_MUTED))
            if col == C_DUENO and not f.dueno:
                return QBrush(QColor(T.TEXT_DIM))
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (C_SLOT, C_ROLLS, C_NV):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def _data_sugerencia(self, f: FilaDisco, role):
        from app.ui.tokens import SUGERENCIA
        if self._sug is None:
            return CALCULANDO if role == Qt.ItemDataRole.DisplayRole else None
        texto, tipo, conflicto, tip = texto_sugerencia(self._sug.get(f.id))
        if role == Qt.ItemDataRole.DisplayRole:
            return texto
        if role == Qt.ItemDataRole.ToolTipRole:
            return tip or None
        if role == Qt.ItemDataRole.ForegroundRole and tipo:
            # En conflicto o nombrado por otra sugerencia: el color del tipo, apagado.
            color = QColor(SUGERENCIA.get(tipo, ("", T.TEXT_SECONDARY))[1])
            if conflicto or texto.startswith("↳"):
                color.setAlpha(110)
            return QBrush(color)
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        self._orden = (column, order)
        self._ordenar()
        self.layoutChanged.emit()

    def _ordenar(self) -> None:
        col, order = self._orden
        self._filas.sort(key=_clave_orden(col, self._sug or {}), reverse=order == Qt.SortOrder.DescendingOrder)

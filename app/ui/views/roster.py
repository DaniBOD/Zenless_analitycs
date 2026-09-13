"""Vista Roster — la tabla de agentes + el diálogo de declaración, tal como estaba en main.py."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app.ui import tokens as T

log = logging.getLogger(__name__)


def build_roster_view() -> QWidget:
    """Tab del roster de agentes."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 12, 12, 12)

    title = QLabel("Roster")
    title.setObjectName("title")

    btn_declarar = QPushButton("Declarar roster…")
    btn_declarar.setToolTip(
        "Decí qué personajes tenés. El sistema no puede enumerar solo a los que NO tenés:\n"
        "en el menú salen en gris y el reconocedor los confunde con uno propio."
    )

    fila_sup = QHBoxLayout()
    fila_sup.addWidget(title)
    fila_sup.addStretch()
    fila_sup.addWidget(btn_declarar)
    layout.addLayout(fila_sup)

    table = QTableWidget()
    table.setColumnCount(8)
    table.setHorizontalHeaderLabels(["Nombre", "Rang.", "Nivel", "M", "Elemento", "Rol", "CR%", "CDmg%"])
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.verticalHeader().setVisible(False)

    def _abrir_declaracion():
        """Abre el diálogo y, si guardó, recarga la tabla: el roster puede haber ganado filas."""
        from app.ui.roster_declaration_dialog import RosterDeclarationDialog
        dlg = RosterDeclarationDialog(parent=w)
        if dlg.exec() and dlg.resultado and dlg.resultado.escribio:
            _fill_roster_table(table, title)

    btn_declarar.clicked.connect(_abrir_declaracion)

    _fill_roster_table(table, title)
    layout.addWidget(table)
    return w


def _fill_roster_table(table: QTableWidget, title: QLabel) -> None:
    """Puebla la tabla desde la DB. Separado de la construcción para poder REFRESCAR después de
    una declaración, que puede haber creado filas nuevas en `agents`."""
    table.setSortingEnabled(False)
    table.setRowCount(0)
    try:
        from app.db.connection import get_connection
        con = get_connection()
        rows = con.execute("""
            SELECT nombre, rango, nivel, mindscape, elemento, rol, prob_critico, dano_critico
            FROM agents ORDER BY rol, nombre
        """).fetchall()
        con.close()

        table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            for col_idx, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 4 and val:
                    item.setForeground(QColor(T.color_elemento(val)))
                if col_idx == 6 and val is not None:
                    try:
                        cr = float(val)
                        if cr >= 60:
                            item.setForeground(QColor(T.POSITIVE))
                        elif cr >= 40:
                            item.setForeground(QColor(T.YELLOW))
                        else:
                            item.setForeground(QColor(T.WARNING))
                    except (ValueError, TypeError):
                        pass
                table.setItem(row_idx, col_idx, item)
        title.setText(f"Roster — {len(rows)} agentes")
    except Exception as e:
        log.exception("[roster] no se pudo poblar la tabla")
        title.setText(f"Roster — error al leer la DB: {e}")
    finally:
        table.setSortingEnabled(True)

"""Vista Discos — la tabla del inventario, tal como estaba en main.py."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.ui import tokens as T


def build_discos_view() -> QWidget:
    """Tab de inventario de discos con datos reales."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 12, 12, 12)

    title = QLabel("Inventario de Discos")
    title.setObjectName("title")
    layout.addWidget(title)

    table = QTableWidget()
    table.setColumnCount(9)
    table.setHorizontalHeaderLabels(["ID", "Set", "Slot", "Main", "Sub1", "Sub2", "Sub3", "Nivel", "Score"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.verticalHeader().setVisible(False)

    try:
        from app.db.connection import get_connection
        con = get_connection()
        rows = con.execute("""
            SELECT id.id, ds.nombre, id.slot, id.main_stat, id.sub1, id.sub2, id.sub3,
                   id.nivel, id.score_evaluacion
            FROM inventory_discs id
            LEFT JOIN disc_sets ds ON ds.id = id.set_id
            WHERE id.descartado = 0 OR id.descartado IS NULL
            ORDER BY id.slot, ds.nombre
            LIMIT 200
        """).fetchall()
        con.close()

        table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            for col_idx, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 8 and val is not None:
                    try:
                        score = float(val)
                        if score >= 0.75:
                            item.setForeground(QColor(T.POSITIVE))
                        elif score >= 0.50:
                            item.setForeground(QColor(T.YELLOW))
                        else:
                            item.setForeground(QColor(T.TEXT_MUTED))
                    except (ValueError, TypeError):
                        pass
                table.setItem(row_idx, col_idx, item)

        subtitle = QLabel(f"Mostrando {len(rows)} discos · Scoring aún no ejecutado (Hito 2.3 pendiente)")
        subtitle.setObjectName("subtitle")
        layout.insertWidget(1, subtitle)
    except Exception as e:
        err_lbl = QLabel(f"Error cargando discos: {e}")
        err_lbl.setStyleSheet(f"color: {T.WARNING};")
        layout.addWidget(err_lbl)

    layout.addWidget(table)
    return w

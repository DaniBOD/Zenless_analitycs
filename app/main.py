"""
DaniBOD ZZZ Analytics — Entrypoint principal.
Fase 2 placeholder: ventana con tabs, tray icon y panel de scoring.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QMenu,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QTextEdit,
)

# ---------------------------------------------------------------------------
# Paleta oscura ZZZ
# ---------------------------------------------------------------------------
COLORS = {
    "bg_deep":    "#0d0d12",
    "bg_surface": "#13141f",
    "bg_card":    "#1a1b2e",
    "accent":     "#f7c948",   # amarillo ZZZ
    "accent2":    "#e86e3a",   # naranja
    "electric":   "#4a9eff",   # azul eléctrico
    "text_main":  "#e8e8f0",
    "text_sub":   "#8888aa",
    "border":     "#2a2b40",
    "ok":         "#4ade80",
    "warn":       "#fbbf24",
    "danger":     "#f87171",
}


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window,          COLORS["bg_deep"]),
        (QPalette.ColorRole.WindowText,      COLORS["text_main"]),
        (QPalette.ColorRole.Base,            COLORS["bg_surface"]),
        (QPalette.ColorRole.AlternateBase,   COLORS["bg_card"]),
        (QPalette.ColorRole.Text,            COLORS["text_main"]),
        (QPalette.ColorRole.Button,          COLORS["bg_card"]),
        (QPalette.ColorRole.ButtonText,      COLORS["text_main"]),
        (QPalette.ColorRole.Highlight,       COLORS["accent"]),
        (QPalette.ColorRole.HighlightedText, COLORS["bg_deep"]),
        (QPalette.ColorRole.ToolTipBase,     COLORS["bg_card"]),
        (QPalette.ColorRole.ToolTipText,     COLORS["text_main"]),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QMainWindow, QWidget {{
            background-color: {COLORS['bg_deep']};
            color: {COLORS['text_main']};
        }}
        QTabWidget::pane {{
            border: 1px solid {COLORS['border']};
            background: {COLORS['bg_surface']};
        }}
        QTabBar::tab {{
            background: {COLORS['bg_card']};
            color: {COLORS['text_sub']};
            padding: 8px 20px;
            border: 1px solid {COLORS['border']};
            border-bottom: none;
        }}
        QTabBar::tab:selected {{
            background: {COLORS['bg_surface']};
            color: {COLORS['accent']};
            border-top: 2px solid {COLORS['accent']};
        }}
        QTabBar::tab:hover {{
            color: {COLORS['text_main']};
        }}
        QTableWidget {{
            background: {COLORS['bg_surface']};
            gridline-color: {COLORS['border']};
            border: none;
        }}
        QTableWidget::item:selected {{
            background: {COLORS['accent']};
            color: {COLORS['bg_deep']};
        }}
        QHeaderView::section {{
            background: {COLORS['bg_card']};
            color: {COLORS['text_sub']};
            border: 1px solid {COLORS['border']};
            padding: 4px 8px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        QLabel#title {{
            color: {COLORS['accent']};
            font-size: 18px;
            font-weight: bold;
        }}
        QLabel#subtitle {{
            color: {COLORS['text_sub']};
            font-size: 12px;
        }}
        QTextEdit {{
            background: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            color: {COLORS['text_main']};
            font-family: Consolas, monospace;
            font-size: 12px;
        }}
        QStatusBar {{
            background: {COLORS['bg_card']};
            color: {COLORS['text_sub']};
            border-top: 1px solid {COLORS['border']};
        }}
        QFrame#card {{
            background: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
        }}
    """)


# ---------------------------------------------------------------------------
# Tabs de contenido (placeholders con datos reales de la DB)
# ---------------------------------------------------------------------------

def _make_placeholder(title: str, description: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl = QLabel(title)
    lbl.setObjectName("title")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    desc = QLabel(description)
    desc.setObjectName("subtitle")
    desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.addWidget(lbl)
    v.addWidget(desc)
    return w


def _build_status_tab() -> QWidget:
    """Tab de estado del sistema con info real de la DB."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setSpacing(12)
    layout.setContentsMargins(16, 16, 16, 16)

    title = QLabel("Estado del Sistema")
    title.setObjectName("title")
    layout.addWidget(title)

    try:
        from app.db.connection import get_connection
        con = get_connection()
        agents = con.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        discos = con.execute("SELECT COUNT(*) FROM inventory_discs WHERE descartado=0 OR descartado IS NULL").fetchone()[0]
        equipados = con.execute("SELECT COUNT(*) FROM inventory_discs WHERE equipado=1").fetchone()[0]
        scored = con.execute("SELECT COUNT(*) FROM inventory_discs WHERE score_evaluacion IS NOT NULL").fetchone()[0]
        evaluaciones = con.execute("SELECT COUNT(*) FROM inventory_disc_evaluations").fetchone()[0]
        sets = con.execute("SELECT COUNT(*) FROM disc_sets").fetchone()[0]
        armas = con.execute("SELECT COUNT(*) FROM inventory_weapons").fetchone()[0]
        con.close()
        db_ok = True
    except Exception as e:
        db_ok = False
        err = str(e)

    stats_frame = QFrame()
    stats_frame.setObjectName("card")
    stats_layout = QVBoxLayout(stats_frame)

    if db_ok:
        stats = [
            ("Agentes en roster", str(agents), COLORS["ok"]),
            ("Discos en inventario", str(discos), COLORS["accent"]),
            ("Discos equipados", str(equipados), COLORS["electric"]),
            ("Discos evaluados", f"{scored} / {discos}", COLORS["warn"] if scored < discos else COLORS["ok"]),
            ("Evaluaciones históricas", str(evaluaciones), COLORS["text_sub"]),
            ("Sets de discos", str(sets), COLORS["text_sub"]),
            ("Armas en inventario", str(armas), COLORS["text_sub"]),
        ]
    else:
        stats = [("ERROR DB", err, COLORS["danger"])]

    for label, value, color in stats:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLORS['text_sub']}; font-size: 13px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(lbl)
        row_layout.addWidget(val)
        stats_layout.addWidget(row)

    layout.addWidget(stats_frame)

    # Fase actual
    fase_frame = QFrame()
    fase_frame.setObjectName("card")
    fase_layout = QVBoxLayout(fase_frame)
    fase_label = QLabel("Fase actual: 2.0 — Saneamiento ETL")
    fase_label.setStyleSheet(f"color: {COLORS['accent']}; font-size: 13px; font-weight: bold;")
    hitos_text = QTextEdit()
    hitos_text.setReadOnly(True)
    hitos_text.setMaximumHeight(160)
    hitos_text.setPlainText(
        "✅  2.0.1  audit_inventory_discs.py — reporte generado\n"
        "✅  2.0.2  stats_vocab.py — 18/18 tests verdes\n"
        "🔄  2.0.3  Migración 06 (normalizar columnas) — pendiente\n"
        "🔄  2.0.4  restandarize_inventory_discs.py — pendiente\n"
        "🔄  2.0.5  seed_substat_preferences.py — pendiente\n"
        "🔄  2.1    Scaffold completo — en progreso\n"
        "🔄  2.2    Scoring engine — en progreso\n"
    )
    fase_layout.addWidget(fase_label)
    fase_layout.addWidget(hitos_text)
    layout.addWidget(fase_frame)
    layout.addStretch()
    return w


def _build_discos_tab() -> QWidget:
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
                            item.setForeground(QColor(COLORS["ok"]))
                        elif score >= 0.50:
                            item.setForeground(QColor(COLORS["warn"]))
                        else:
                            item.setForeground(QColor(COLORS["text_sub"]))
                    except (ValueError, TypeError):
                        pass
                table.setItem(row_idx, col_idx, item)

        subtitle = QLabel(f"Mostrando {len(rows)} discos · Scoring aún no ejecutado (Hito 2.3 pendiente)")
        subtitle.setObjectName("subtitle")
        layout.insertWidget(1, subtitle)
    except Exception as e:
        err_lbl = QLabel(f"Error cargando discos: {e}")
        err_lbl.setStyleSheet(f"color: {COLORS['danger']};")
        layout.addWidget(err_lbl)

    layout.addWidget(table)
    return w


def _build_roster_tab() -> QWidget:
    """Tab del roster de agentes."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 12, 12, 12)

    title = QLabel("Roster — 46 Agentes")
    title.setObjectName("title")
    layout.addWidget(title)

    table = QTableWidget()
    table.setColumnCount(8)
    table.setHorizontalHeaderLabels(["Nombre", "Rang.", "Nivel", "M", "Elemento", "Rol", "CR%", "CDmg%"])
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.verticalHeader().setVisible(False)

    try:
        from app.db.connection import get_connection
        con = get_connection()
        rows = con.execute("""
            SELECT nombre, rango, nivel, mindscape, elemento, rol, prob_critico, dano_critico
            FROM agents ORDER BY rol, nombre
        """).fetchall()
        con.close()

        table.setRowCount(len(rows))
        elem_colors = {
            "Eléctrico": "#4a9eff",
            "Hielo":     "#a8d8ea",
            "Fuego":     "#e86e3a",
            "Físico":    "#a0a0b0",
            "Éter":      "#c084fc",
        }
        for row_idx, r in enumerate(rows):
            for col_idx, val in enumerate(r):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 4 and val in elem_colors:
                    item.setForeground(QColor(elem_colors[val]))
                if col_idx == 6 and val is not None:
                    try:
                        cr = float(val)
                        if cr >= 60:
                            item.setForeground(QColor(COLORS["ok"]))
                        elif cr >= 40:
                            item.setForeground(QColor(COLORS["warn"]))
                        else:
                            item.setForeground(QColor(COLORS["danger"]))
                    except (ValueError, TypeError):
                        pass
                table.setItem(row_idx, col_idx, item)
    except Exception as e:
        err = QLabel(f"Error: {e}")
        err.setStyleSheet(f"color: {COLORS['danger']};")
        layout.addWidget(err)

    layout.addWidget(table)
    return w


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DaniBOD ZZZ Analytics  v0.1.0-dev")
        self.setMinimumSize(1320, 820)
        self._setup_ui()
        self._setup_tray()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background: {COLORS['bg_card']}; border-bottom: 2px solid {COLORS['accent']};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        logo = QLabel("⚡ DaniBOD ZZZ Analytics")
        logo.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 15px; font-weight: bold; letter-spacing: 1px;"
        )
        self._monitor_lbl = QLabel("● Monitor: OFF")
        self._monitor_lbl.setStyleSheet(f"color: {COLORS['text_sub']}; font-size: 12px;")
        hl.addWidget(logo)
        hl.addStretch()
        hl.addWidget(self._monitor_lbl)
        v.addWidget(header)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(_build_status_tab(),       "Estado")
        tabs.addTab(_make_placeholder(
            "Captura en Vivo",
            "Hito 2.4 — OCR + Detector pendiente\nEl monitor detectará discos al farmear."
        ), "Live")
        tabs.addTab(_build_discos_tab(),       "Discos")
        tabs.addTab(_build_roster_tab(),       "Roster")
        tabs.addTab(_make_placeholder(
            "Equipos",
            "Fase 3 — RF-12 (IA catalogadora) pendiente"
        ), "Equipos")
        tabs.addTab(_make_placeholder(
            "Lategame",
            "Fase 4 — RF-13 (F11 OCR + tier list bayesiana) pendiente"
        ), "Lategame")
        tabs.addTab(_make_placeholder(
            "Armas",
            "Fase 5 — RF-14 (W-Engines optimizer) pendiente"
        ), "Armas")
        tabs.addTab(_make_placeholder(
            "Histórico",
            "Historial de evaluaciones — disponible tras Hito 2.3"
        ), "Histórico")
        tabs.addTab(_make_placeholder(
            "Configuración",
            "Paths, thresholds, OCR backend, hotkeys"
        ), "Config")
        v.addWidget(tabs)

        # Status bar
        sb = QStatusBar()
        sb.showMessage("DaniBOD · UID 1000860143 · Fase 2 en progreso  |  F8 Captura · F9 Panel · F10 Pausa · F11 Lategame")
        self.setStatusBar(sb)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        # Icono inline si no existe el archivo
        ico_path = Path("app/resources/icon.ico")
        if ico_path.exists():
            self._tray.setIcon(QIcon(str(ico_path)))
        else:
            self._tray.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon
            ))

        tray_menu = QMenu()
        show_action = QAction("Mostrar panel", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("Salir (Ctrl+Shift+Z)", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "DaniBOD ZZZ Analytics",
            "Minimizado al tray. Doble-click para restaurar.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DaniBOD ZZZ Analytics")
    app.setQuitOnLastWindowClosed(False)
    apply_dark_palette(app)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""
DaniBOD ZZZ Analytics — Entrypoint principal.
Fase 2 placeholder: ventana con tabs, tray icon y panel de scoring.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _setup_file_logging() -> Path | None:
    """
    Configura un RotatingFileHandler en %LOCALAPPDATA%/DaniBOD_ZZZ_Analytics/app.log.

    Indispensable para el .exe --windowed (console=False) donde stderr no
    es visible. Todas las llamadas a log.info/log.exception del proyecto
    quedan persistentes y pueden inspeccionarse con:
        Get-Content "$env:LOCALAPPDATA\\DaniBOD_ZZZ_Analytics\\app.log" -Tail 50

    Si la configuración falla (carpeta read-only, permisos, etc.) el
    arranque continúa sin file logging — no es bloqueante.
    """
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        log_dir = Path(base) / "DaniBOD_ZZZ_Analytics"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Evitar duplicados si _setup_file_logging se llama dos veces
        for h in root_logger.handlers:
            if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file):
                return log_file

        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(fh)

        # Hito 2.8 (QA 2026-05-31): `import paddleocr` SUBE el nivel del root
        # logger a WARNING, lo que silenciaba todos nuestros INFO (heartbeats,
        # [stats], [completo], "Monitor arrancado"...) una vez activado Paddle.
        # Fijar el nivel del logger raíz del proyecto ("app") a INFO lo hace
        # INMUNE a que paddle toque el nivel del root: el level-check ocurre en
        # el logger de origen (app.*), y los records propagan a los handlers del
        # root sin re-filtrarse por el nivel del root.
        logging.getLogger("app").setLevel(logging.INFO)

        root_logger.info("Logging a archivo iniciado en %s", log_file)
        return log_file
    except Exception:
        # Sin file logging es peor pero arranque debe continuar
        return None

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
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
        _ico = Path(__file__).parent / "resources" / "icon.ico"
        if _ico.exists():
            self.setWindowIcon(QIcon(str(_ico)))
        self._setup_ui()
        self._setup_tray()

    def _setup_ui(self):
        from app.ui.live_panel import LivePanel
        from app.ui.controller import MonitorController
        from app.ui.toast import DiscToast, ToastData

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

        # ---- Componentes Live (controller + panel + toast) ----
        self._live_panel = LivePanel()
        self._controller = MonitorController(parent=self)
        self._toast = DiscToast()

        # Cableado controller → panel
        self._controller.monitor_started.connect(self._live_panel.on_monitor_started)
        self._controller.monitor_stopped.connect(self._live_panel.on_monitor_stopped)
        self._controller.pause_changed.connect(self._live_panel.on_pause_changed)
        self._controller.state_changed.connect(self._live_panel.on_state_changed)
        self._controller.disc_detected.connect(self._live_panel.on_disc_detected)
        self._controller.error_occurred.connect(self._live_panel.on_error)

        # Cableado controller → toast
        self._controller.disc_detected.connect(self._on_disc_show_toast)

        # Cableado controller.log_message → live_panel.append_log
        # (mensajes informativos: cambios de estado, capturas descartadas, etc)
        self._controller.log_message.connect(self._live_panel.append_log)

        # Cableado toast.clicked → abrir panel principal
        self._toast.clicked.connect(self._show_and_raise)

        # Auto-detect: el monitor arranca automáticamente cuando ZZZ corre.
        # El botón "Iniciar captura" sigue disponible como override manual.
        self._controller.auto_start_enabled.connect(
            lambda enabled: self._live_panel.append_log(
                "[auto] Watcher de ZZZ ACTIVO — el monitor arranca solo cuando detecta el juego."
                if enabled else "[auto] Watcher de ZZZ desactivado."
            )
        )
        # Habilitar auto-detect por default. Override de QA: `DANIBOD_NO_AUTOSTART=1`
        # arranca la app en reposo (watcher OFF) → la captura NO empieza sola aunque ZZZ
        # esté abierto; el usuario la activa a mano cuando quiere (botón "Iniciar captura").
        if os.environ.get("DANIBOD_NO_AUTOSTART"):
            self._live_panel.append_log(
                "[auto] Arranque en REPOSO (DANIBOD_NO_AUTOSTART=1) — la captura NO arranca sola. "
                "Usá 'Iniciar captura' cuando quieras empezar."
            )
        else:
            self._controller.set_auto_detect(True)

        # Cableado controller → header indicator
        self._controller.monitor_started.connect(lambda: self._set_header_monitor("ON",  COLORS["ok"]))
        self._controller.monitor_stopped.connect(lambda: self._set_header_monitor("OFF", COLORS["text_sub"]))
        self._controller.pause_changed.connect(
            lambda paused: self._set_header_monitor("PAUSADO" if paused else "ON",
                                                    COLORS["warn"] if paused else COLORS["ok"])
        )

        # Cableado panel → controller
        self._live_panel.start_monitor_requested.connect(self._controller.start)
        self._live_panel.stop_monitor_requested.connect(self._controller.stop)
        self._live_panel.pause_toggle_requested.connect(self._controller.toggle_pause)
        self._live_panel.test_capture_requested.connect(self._controller.force_scan)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(_build_status_tab(),       "Estado")
        tabs.addTab(self._live_panel,           "Live")
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
        ico_path = Path(__file__).parent / "resources" / "icon.ico"
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
            self._show_and_raise()

    def _show_and_raise(self):
        """Trae la ventana al frente (desde tray, click en toast, o
        segunda instancia que pide foco — ver single-instance en main())."""
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _set_header_monitor(self, label: str, color: str):
        self._monitor_lbl.setText(f"● Monitor: {label}")
        self._monitor_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _on_disc_show_toast(self, payload: dict):
        """Slot: convierte payload del controller a ToastData y muestra el toast."""
        from app.ui.toast import ToastData
        td = ToastData(
            variant=payload.get("variant", "reserva"),
            set_name=payload.get("set", "?"),
            slot=payload.get("slot", 0),
            rarity=payload.get("rarity", "S"),
            main_stat=payload.get("main", "?"),
            main_value=payload.get("main_value", ""),
            subs_summary=payload.get("subs", ""),
            target_agent=payload.get("target", "—"),
            target_mind=payload.get("mind", 0),
            target_avatar=payload.get("target_avatar"),
            set_logo=payload.get("set_logo"),
            score=payload.get("score", 0.0),
            urgency=payload.get("urgency", 0.7),
            threshold=payload.get("threshold", 0.75),
            timeout_secs=4.0,
        )
        self._toast.show_recommendation(td)

    def closeEvent(self, event):
        """
        X cierra la app completamente. Minimizar (botón `_`) NO pasa por
        este handler — usa changeEvent(WindowStateChange) y queda en la
        barra de tareas sin disparar cierre.

        Para volver al pattern "X minimiza al tray" usar el menú del tray
        opción 'Mostrar panel' tras cerrar, o ejecutar la app de nuevo.
        """
        self._tray.hide()
        event.accept()
        QApplication.quit()


# ---------------------------------------------------------------------------
# Single-instance (una sola sesión activa)
# ---------------------------------------------------------------------------

# Nombre del socket local. Único por usuario+app; si algún día corren dos
# cuentas de Windows en paralelo, cada sesión tiene su propio namespace de
# QLocalServer, así que no colisionan.
_SINGLE_INSTANCE_KEY = "DaniBOD_ZZZ_Analytics_SingleInstance"


def _try_signal_existing_instance() -> bool:
    """
    Intenta contactar a una instancia ya corriendo.

    Devuelve True si HABÍA otra instancia (le mandamos 'show' y esta debe
    abortar su arranque). Devuelve False si somos la primera instancia.
    """
    socket = QLocalSocket()
    socket.connectToServer(_SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(300):
        # Ya hay una instancia: pedirle que se muestre y salir.
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def _install_instance_server(window: "MainWindow") -> QLocalServer:
    """
    Crea el QLocalServer que escucha pedidos de 'foco' de instancias nuevas.
    Cuando llega una conexión, trae la ventana de esta instancia al frente.
    """
    # Limpiar un socket huérfano de un crash anterior antes de escuchar.
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(_SINGLE_INSTANCE_KEY)

    def _on_new_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            # No hace falta leer el payload: cualquier conexión = "traeme al frente".
            conn.readyRead.connect(lambda: conn.readAll())
            window._show_and_raise()
            conn.disconnectFromServer()

    server.newConnection.connect(_on_new_connection)
    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    _setup_file_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("DaniBOD ZZZ Analytics")
    app.setQuitOnLastWindowClosed(False)

    # --- Single-instance guard ---------------------------------------------
    # Si ya hay una sesión abierta, le pedimos que se muestre y abortamos:
    # nunca quedan dos ventanas/tray del sistema a la vez.
    # EXCEPCIÓN (RNF-06): un auto-restart del watchdog trae DANIBOD_RESTART=1. La instancia
    # vieja se está cerrando (ventana de ~1.2s) → si chequeáramos single-instance la veríamos
    # viva y abortaríamos, quedando CERO apps (bug observado 2026-06-13). Bypass en ese caso.
    if os.environ.pop("DANIBOD_RESTART", None):
        logging.getLogger("app").info(
            "Arranque por auto-restart (RNF-06): bypass del single-instance."
        )
    elif _try_signal_existing_instance():
        logging.getLogger("app").info(
            "Ya hay una instancia corriendo — se le pidió foco y esta sale."
        )
        return

    apply_dark_palette(app)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    # Mantener una referencia viva al server en el window para que no lo
    # recolecte el GC mientras la app vive.
    window._instance_server = _install_instance_server(window)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

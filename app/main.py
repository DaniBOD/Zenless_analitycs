"""
DaniBOD ZZZ Analytics — Entrypoint principal.
Ventana principal (shell de la interfaz, fase 1), tray icon y cableado del monitor.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _debug_logs() -> bool:
    """¿Mostrar también el razonamiento interno? (`DANIBOD_LOG_DEBUG`)

    El default es NO, y esa es la decisión de diseño: en INFO va **un evento, una línea**. El
    porqué de cada decisión vive en DEBUG y se enciende cuando hace falta depurar. Mismo criterio
    de env-gate que el resto de la instrumentación (`DANIBOD_ID_DIAG`, `DANIBOD_METRICS`).
    """
    return os.environ.get("DANIBOD_LOG_DEBUG", "").strip() not in ("", "0", "false", "no")


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

        # `DANIBOD_LOG_DEBUG=1` baja el piso a DEBUG. Ahí vive el RAZONAMIENTO del sistema —por qué
        # vetó un ancla, por qué no cosechó, por qué no persistió— que en INFO ahogaba al EVENTO.
        # Medido sobre el QA del 2026-08-15: 4 a 7 líneas por disco, de las cuales una sola decía
        # qué había pasado. Un censo de ~300 discos daba 1200-2100 líneas con la señal enterrada.
        nivel = logging.DEBUG if _debug_logs() else logging.INFO
        root_logger = logging.getLogger()
        root_logger.setLevel(nivel)

        # Evitar duplicados si _setup_file_logging se llama dos veces
        for h in root_logger.handlers:
            if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file):
                return log_file

        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(nivel)
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
        logging.getLogger("app").setLevel(nivel)

        root_logger.info("Logging a archivo iniciado en %s", log_file)
        return log_file
    except Exception:
        # Sin file logging es peor pero arranque debe continuar
        return None


# --------------------------------------------------------------------------------------- #
# Desvío a worker de OCR — ANTES de importar Qt, y no es un detalle de estilo.
#
# Empaquetado, el hijo que hace el OCR es ESTE MISMO `.exe` con un centinela de argv (no se puede
# lanzar "el módulo del worker" cuando todo vive dentro del bundle). Si el desvío estuviera después
# del import de Qt, cada worker levantaría PySide6 —decenas de MB y varios cientos de ms— para no
# usarlo; y si estuviera después de `main()`, levantaría la ventana.
#
# Va antes que nada, incluso antes del logging: el worker no escribe al log a propósito (dos
# procesos rotando `app.log` se pisan). Ver `app/core/ocr_worker.py`.
# --------------------------------------------------------------------------------------- #
from app.core import ocr_ipc as _ocr_ipc  # noqa: I001 — va SOLO y ANTES del bloque de Qt, a propósito

if _ocr_ipc.es_arranque_de_worker():
    from app.core.ocr_worker import ejecutar as _ejecutar_worker_ocr
    sys.exit(_ejecutar_worker_ocr())

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paleta — una sola autoridad: app/ui/tokens.py (los tokens del mockup de Claude Design)
# ---------------------------------------------------------------------------
# Hasta el 2026-09-12 este archivo tenía su PROPIA paleta (`COLORS`: fondo #0d0d12, amarillo
# #f7c948) además de la de `tokens.py` (#0a0a0a, #FFCB05). Dos respuestas a la misma pregunta (B1).

def apply_dark_palette(app: QApplication):
    from app.ui import tokens as T

    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window,          T.BG_BASE),
        (QPalette.ColorRole.WindowText,      T.TEXT_PRIMARY),
        (QPalette.ColorRole.Base,            T.BG_PANEL),
        (QPalette.ColorRole.AlternateBase,   T.BG_PANEL_HI),
        (QPalette.ColorRole.Text,            T.TEXT_PRIMARY),
        (QPalette.ColorRole.Button,          T.BG_PANEL_HI),
        (QPalette.ColorRole.ButtonText,      T.TEXT_PRIMARY),
        (QPalette.ColorRole.Highlight,       T.YELLOW),
        (QPalette.ColorRole.HighlightedText, T.BG_BASE),
        (QPalette.ColorRole.ToolTipBase,     T.BG_PANEL_HI),
        (QPalette.ColorRole.ToolTipText,     T.TEXT_PRIMARY),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    # Ojo: NO hay una regla `QWidget { background-color }` genérica, que la hoja vieja sí tenía.
    # Pintaba un fondo opaco en cada label y tapaba el gradiente del sidebar y el tinte del ítem
    # activo. El fondo de la ventana ya lo da la paleta; cada superficie del shell pinta el suyo.
    app.setStyleSheet(f"""
        QWidget {{ color: {T.TEXT_PRIMARY}; }}
        QTableWidget {{
            background: {T.BG_PANEL};
            alternate-background-color: {T.BG_PANEL_HI};
            gridline-color: {T.BORDER_SUBTLE};
            border: none;
        }}
        QTableWidget::item:selected {{ background: {T.YELLOW}; color: {T.BG_BASE}; }}
        QHeaderView::section {{
            background: {T.BG_PANEL_HI};
            color: {T.TEXT_MUTED};
            border: 1px solid {T.BORDER_SUBTLE};
            padding: 4px 8px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        QLabel#title {{ color: {T.YELLOW}; font-size: 18px; font-weight: bold; }}
        QLabel#subtitle {{ color: {T.TEXT_MUTED}; font-size: 12px; }}
        QFrame#card {{
            background: {T.BG_PANEL};
            border: 1px solid {T.BORDER_SUBTLE};
            border-radius: 8px;
        }}
        QToolTip {{
            background: {T.BG_PANEL_HI}; color: {T.TEXT_PRIMARY}; border: 1px solid {T.BORDER_MID};
        }}
        QScrollBar:vertical {{ background: {T.BG_DEEP}; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {T.BORDER_MID}; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """)


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
# Fase 1 de la interfaz (2026-09-12): la ventana ES el shell del mockup (barra de título propia,
# sidebar, stack de vistas, barra inferior) y la pestaña "Live" pasó a ser la vista en vivo. Las
# demás vistas se mudaron a `app/ui/views/` sin rediseñar. La pestaña "Estado" desapareció: su
# contenido es la barra inferior. Diseño en Dev_IA 2026-09-12_PLAN_Interfaz_la_pantalla_en_vivo.

from app.ui.shell.window import ShellWindow  # noqa: E402 — después del desvío del worker de OCR

VERSION = "v0.1.0-dev"


class MainWindow(ShellWindow):
    def __init__(self):
        from app.db.connection import get_db_path, is_readonly
        super().__init__(VERSION, db_path=get_db_path(), readonly=is_readonly())
        self.setWindowTitle(f"DaniBOD ZZZ Analytics  {VERSION}")
        _ico = Path(__file__).parent / "resources" / "icon.ico"
        if _ico.exists():
            self.setWindowIcon(QIcon(str(_ico)))
        self._setup_ui()
        self._setup_tray()

    def _setup_ui(self):
        from app.db.connection import get_connection
        from app.ui.controller import MonitorController
        from app.ui.live.build_provider import BuildProvider
        from app.ui.live.view import LiveView
        from app.ui.toast import DiscToast
        from app.ui.views.discos import build_discos_view
        from app.ui.views.placeholder import make_placeholder
        from app.ui.views.roster import build_roster_view

        # Conexión de LECTURA de la UI: el build del hexágono y los contadores del sidebar. Vive lo
        # que vive la ventana. Si la DB no abre, la app arranca igual: sin hexágono y sin contadores.
        self._ui_con = None
        try:
            self._ui_con = get_connection()
        except Exception:
            log.exception("[ui] sin conexión de lectura: la vista en vivo arranca sin builds")
        build_fn = BuildProvider(self._ui_con).build_de if self._ui_con else (lambda _n: {})

        self._live_view = LiveView(build_fn=build_fn)
        self._controller = MonitorController(parent=self)
        self._toast = DiscToast()
        c, vista, barra = self._controller, self._live_view, self.titlebar

        # Estado del monitor → la barra de título y la consola
        c.monitor_started.connect(vista.on_monitor_started)
        c.monitor_started.connect(barra.on_monitor_started)
        c.monitor_stopped.connect(vista.on_monitor_stopped)
        c.monitor_stopped.connect(barra.on_monitor_stopped)
        c.pause_changed.connect(vista.on_pause_changed)
        c.pause_changed.connect(barra.on_pause_changed)
        c.state_changed.connect(vista.on_state_changed)
        c.error_occurred.connect(vista.on_error)
        # Mensajes informativos (cambios de estado, capturas descartadas, etc.) → la consola
        c.log_message.connect(vista.append_log)

        # Lo que se leyó → la card. `disc_observed` es el disco con dueño en pantalla (S17/S9);
        # `disc_detected` es el drop, del que la vista descarta todo lo que sale del scoring.
        c.disc_observed.connect(vista.on_disc_observed)
        c.disc_detected.connect(vista.on_disc_detected)
        c.weapon_seen.connect(vista.on_weapon_seen)

        # Toasts (sin cambios)
        c.disc_detected.connect(self._on_disc_show_toast)
        c.disc_replaced.connect(self._on_disc_show_replacement_toast)
        c.disc_equipped.connect(self._on_disc_show_equipped_toast)
        c.discs_dismantled.connect(self._on_show_teardown_toast)
        c.weapon_seen.connect(self._on_show_weapon_toast)
        self._toast.clicked.connect(self._show_and_raise)

        # Contadores del sidebar: al arrancar y un rato después de cada evento que pudo escribir.
        # Con debounce: una tanda de censo son decenas de lecturas y cada una no merece 6 COUNTs.
        # Se conecta a un MÉTODO de esta ventana y no a una lambda: las señales llegan desde el
        # thread del monitor, y sólo con un receptor QObject Qt las encola al thread de la UI.
        self._refresco = QTimer(self)
        self._refresco.setSingleShot(True)
        self._refresco.setInterval(1500)
        self._refresco.timeout.connect(self._refrescar_contadores)
        for senal in (c.disc_observed, c.disc_detected, c.weapon_seen, c.discs_dismantled,
                      c.disc_replaced, c.disc_equipped):
            senal.connect(self._pedir_refresco)

        # Auto-detect: el monitor arranca solo cuando ZZZ corre. El botón de la consola sigue
        # disponible como override manual.
        c.auto_start_enabled.connect(self._on_auto_start)
        if os.environ.get("DANIBOD_NO_AUTOSTART"):
            vista.append_log(
                "[auto] Arranque en REPOSO (DANIBOD_NO_AUTOSTART=1) — la captura NO arranca sola. "
                "Usá 'Iniciar captura' cuando quieras empezar."
            )
        else:
            c.set_auto_detect(True)

        # Vista → controller
        vista.start_monitor_requested.connect(c.start)
        vista.stop_monitor_requested.connect(c.stop)
        vista.pause_toggle_requested.connect(c.toggle_pause)

        # Las 9 vistas del sidebar
        self.add_view("live", vista)
        self.add_view("historico", make_placeholder(
            "Histórico", "Historial de evaluaciones — disponible tras Hito 2.3"))
        self.add_view("lategame", make_placeholder(
            "Lategame", "Fase 4 — RF-13 (F11 OCR + tier list bayesiana) pendiente"))
        self.add_view("discos", build_discos_view())
        self.add_view("roster", build_roster_view())
        self.add_view("armas", make_placeholder(
            "Armas", "Fase 5 — RF-14 (W-Engines optimizer) pendiente"))
        self.add_view("equipos", make_placeholder(
            "Equipos", "Fase 3 — RF-12 (IA catalogadora) pendiente"))
        self.add_view("catalogos", make_placeholder(
            "Catálogos", "Sets, W-Engines y facciones — pendiente"))
        self.add_view("config", make_placeholder(
            "Configuración", "Paths, thresholds, OCR backend, hotkeys"))

        vista.append_log("[init] Monitor inactivo. 'Iniciar captura' o F9 para abrir el panel.")
        self._refrescar_contadores()

    def _on_auto_start(self, enabled: bool):
        self._live_view.append_log(
            "[auto] Watcher de ZZZ ACTIVO — el monitor arranca solo cuando detecta el juego."
            if enabled else "[auto] Watcher de ZZZ desactivado."
        )

    def _pedir_refresco(self, *_):
        self._refresco.start()

    def _refrescar_contadores(self):
        from app.ui.shell.contadores import leer_contadores
        if self._ui_con is None:
            return
        try:
            self.sidebar.set_counters(leer_contadores(self._ui_con))
        except Exception:
            log.exception("[ui] no se pudieron refrescar los contadores")
        self.statusbar_widget.refresh_db_size()


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

    def _on_disc_show_replacement_toast(self, payload: dict):
        """Slot: toast REEMPLAZADO (swap de disco entre PJs). El destino usa target_*, el origen
        from_*. Sin score ni countdown (confirmación pasiva)."""
        from app.ui.toast import ToastData
        td = ToastData(
            variant="reemplazado",
            set_name=payload.get("set", "?"),
            slot=payload.get("slot", 0),
            rarity=payload.get("rarity", "S"),
            set_logo=payload.get("set_logo"),
            from_agent=payload.get("from_agent", "—"),
            from_avatar=payload.get("from_avatar"),
            target_agent=payload.get("to_agent", "—"),
            target_avatar=payload.get("to_avatar"),
            timeout_secs=3.0,
        )
        self._toast.show_replacement(td)

    def _on_disc_show_equipped_toast(self, payload: dict):
        """Slot: toast AHORA EN (disco LIBRE equipado a un PJ). Mismo payload que el reemplazo —
        los campos `from_*` vienen vacíos a propósito: el disco no era de nadie."""
        from app.ui.toast import ToastData
        td = ToastData(
            variant="equipado",
            set_name=payload.get("set", "?"),
            slot=payload.get("slot", 0),
            rarity=payload.get("rarity", "S"),
            set_logo=payload.get("set_logo"),
            target_agent=payload.get("to_agent", "—"),
            target_avatar=payload.get("to_avatar"),
            timeout_secs=3.0,
        )
        self._toast.show_equipped(td)

    def _on_show_teardown_toast(self, payload: dict):
        """Slot: toast DESMONTADOS (tanda de desmontaje cerrada). UNO por tanda, no uno por disco.

        No hay un disco que mostrar — es un lote — así que el body pinta el conteo. El timeout es
        un poco más largo que en las otras confirmaciones porque el dato a leer son dos números."""
        from app.ui.toast import ToastData
        td = ToastData(variant="desmontado", set_name="—", slot=0, rarity="S", timeout_secs=4.0)
        td.teardown_total = int(payload.get("total") or 0)
        td.teardown_known = int(payload.get("con_datos") or 0)
        self._toast.show_teardown(td)

    def _on_show_weapon_toast(self, payload: dict):
        """Slot: toast de W-Engine (RF-15). Solo ante un CAMBIO, no por cada arma mirada.

        Un toast interrumpe, así que tiene que traer noticia. Abrir un engine para verlo no lo es
        —el usuario lo está mirando—, y un toast por lectura además tapa a los que sí importan.
        El panel en vivo sigue recibiendo cada observación: ahí es donde se busca el detalle.

        El nombre puede venir crudo del OCR (el catálogo tiene armas de menos); se muestra igual
        porque el usuario reconoce el arma que acaba de abrir. Nada de esto escribe la DB."""
        if not payload.get("cambio"):
            return
        from app.ui.toast import ToastData
        td = ToastData(variant="arma_vista", set_name="—", slot=0,
                       rarity=str(payload.get("rareza") or "?"), timeout_secs=4.0)
        td.weapon_name = str(payload.get("nombre") or "—")
        nivel, nivel_max = payload.get("nivel"), payload.get("nivel_max")
        td.weapon_level = f"{nivel}/{nivel_max}" if nivel is not None and nivel_max else ""
        td.weapon_refine = int(payload.get("refinamiento") or 0)
        td.weapon_stat = str(payload.get("stat") or "")
        # Redacción para el toast. "incierto" se muestra VACÍO a propósito: en una línea de tres
        # campos, "tenencia incierta" ocupa el mismo lugar que un dato y se lee como si lo fuera.
        dueno = payload.get("dueno")
        td.weapon_tenencia = {
            "equipada": f"la usa {dueno}" if dueno else "equipada",
            "otro_pj": f"la tiene {dueno}" if dueno else "la tiene otro PJ",
            "libre": "LIBRE",
        }.get(str(payload.get("tenencia") or ""), "")
        # El header nombra el EVENTO, no la pantalla. Se conservan el "✓ OBSERVADO" y el footer
        # "SOLO LECTURA": son los que separan a este toast de los de disco, que sí escriben la DB.
        td.label_override = {
            "equipada": "W-ENGINE EQUIPADO",
            "libre":    "W-ENGINE DESEQUIPADO",
            "otro_pj":  "W-ENGINE REASIGNADO",
        }.get(str(payload.get("tenencia") or ""), "")
        self._toast.show_weapon(td)

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

"""
MonitorController — orquesta monitor → recommender → toast/panel.

Mantiene refs a OCR, detector, repos y al Monitor. Convierte los callbacks
del monitor (que corren en su thread daemon) a signals Qt thread-safe que el
panel y el toast pueden conectar.

Maneja gracefully el caso "Tesseract no instalado" — emite error_occurred
con instrucciones de instalación en vez de crashear.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

log = logging.getLogger(__name__)


# Ubicaciones comunes del binario tesseract en Windows
_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def _find_tesseract() -> str | None:
    for c in _TESSERACT_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def _capture_only_focused() -> bool:
    """Lee [monitor].solo_capturar_si_enfocado de defaults.toml (fallback True).

    Override de QA: `DANIBOD_NO_FOCUS_GATE=1` desactiva el gate (sigue capturando aunque el
    juego no esté al frente) — útil para inspeccionar/loguear sin que el alt-tab pause la
    captura. No cambia el default anti-FP; es solo para la sesión de QA."""
    import os
    if os.environ.get("DANIBOD_NO_FOCUS_GATE"):
        return False
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        cfg_path = Path(__file__).parent.parent / "config" / "defaults.toml"
        with open(cfg_path, "rb") as f:
            cfg = tomllib.load(f)
        return bool(cfg.get("monitor", {}).get("solo_capturar_si_enfocado", True))
    except Exception:
        return True


class MonitorController(QObject):
    """
    Controlador único de captura. Crea/destruye el Monitor según start/stop,
    emite signals a la UI cuando hay eventos.
    """

    # Estado del monitor
    monitor_started = Signal()
    monitor_stopped = Signal()
    pause_changed = Signal(bool)             # True = paused
    state_changed = Signal(str, float)       # code (S1-S12), confidence

    # Eventos de captura
    disc_detected = Signal(dict)             # payload listo para LivePanel + Toast
    disc_replaced = Signal(dict)             # swap de disco entre PJs confirmado → toast REEMPLAZADO
    disc_equipped = Signal(dict)             # disco LIBRE equipado a un PJ → toast AHORA EN
    agent_stats_detected = Signal(dict)      # stats de agente desde S18
    error_occurred = Signal(str)
    # Mensaje informativo crudo para el log (estado, captura descartada, etc).
    log_message = Signal(str)

    # Auto-start: el monitor arranca cuando se detecta el proceso de ZZZ
    auto_start_enabled = Signal(bool)        # True cuando se habilita el auto-arranque

    # Watchdog RNF-06: el monitor (thread daemon) pide auto-restart del .exe ante RAM
    # crítica. La signal marshalla al main thread (relaunch + quit deben correr ahí).
    ram_critical = Signal()

    # Intervalo del watcher que detecta ZZZ corriendo (segundos)
    AUTO_DETECT_INTERVAL_S = 3

    def __init__(self, db_path: Path | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._db_path = db_path
        self._monitor = None
        self._con: sqlite3.Connection | None = None
        self._agent_repo = None
        self._archetype_repo = None
        self._disc_set_repo = None
        self._scoring_ctx = None
        self._disc_syncer = None
        self._owner_tiebreaker = None
        self._farm_session = None
        self._farm_node_catalog = None
        self._set_badge_matcher = None
        # Firma del último log de stats S18 emitido (edge-triggered): re-loguea solo
        # cuando el resultado cambia. Se resetea en _on_state_from_monitor.
        self._last_stats_sig: tuple | None = None

        # Watcher de proceso ZZZ — arranca/detiene el monitor automáticamente
        # según la presencia de la ventana del juego.
        self._auto_detect_timer = QTimer(self)
        self._auto_detect_timer.setInterval(self.AUTO_DETECT_INTERVAL_S * 1000)
        self._auto_detect_timer.timeout.connect(self._check_zzz_window)
        self._auto_detect_enabled = False
        self._was_window_present = False
        # Watchdog RNF-06: relanzar el .exe ante RAM crítica (una sola vez).
        self._restart_requested = False
        self.ram_critical.connect(self._handle_ram_critical)

    # ---- Public API ----------------------------------------------------------

    @Slot()
    def start(self):
        """Inicializa OCR, repos y arranca el monitor. Si algo falla, emite error_occurred."""
        if self._monitor is not None:
            return  # ya está corriendo

        try:
            self._init_dependencies()
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
            return
        except Exception as exc:
            log.exception("Init dependencies failed")
            self.error_occurred.emit(f"Error inesperado: {exc}")
            return

        # Tracking PRE→POST del modal de mejora (S10). Display-only (no escribe DB);
        # emite diagnósticos por el mismo sink que el resto del monitor.
        from app.core.sync_upgrade import UpgradeSyncer
        self._upgrade_syncer = UpgradeSyncer(
            ocr=self._ocr,
            on_diagnostic=self._on_diagnostic_from_monitor,
            set_repo=self._disc_set_repo,
        )

        from app.core.monitor import Monitor
        self._monitor = Monitor(
            ocr=self._ocr,
            detector=self._detector,
            on_disc=self._on_disc_from_monitor,
            on_state_change=self._on_state_from_monitor,
            on_disc_rejected=self._on_disc_rejected_from_monitor,
            on_agent_stats=self._on_agent_stats_from_monitor,
            on_diagnostic=self._on_diagnostic_from_monitor,
            on_replacement=self._on_replacement_from_monitor,
            on_agent_detail=self._on_agent_detail_from_monitor,
            set_repo=self._disc_set_repo,
            on_ram_critical=self.ram_critical.emit,   # watchdog RNF-06 → main thread
            owner_tiebreaker=self._owner_tiebreaker,  # desempate por contexto (look-alikes)
            farm_session=self._farm_session,          # gate de farmeo (contexto S13→S14→S2)
            farm_node_catalog=self._farm_node_catalog, # predicción de sets en S13
            set_badge_matcher=self._set_badge_matcher, # set por badge del disco en S2
            capture_only_focused=_capture_only_focused(),  # gate anti-FP por foco de ventana
            upgrade_syncer=self._upgrade_syncer,      # tracking PRE→POST modal upgrade (S10)
        )
        self._monitor.start()
        self.monitor_started.emit()

    @Slot()
    def stop(self):
        if self._monitor is None:
            return
        try:
            self._monitor.stop()
        except Exception:
            log.exception("Error stopping monitor")
        self._monitor = None
        if self._disc_syncer is not None:
            try:
                self._disc_syncer.close()
            except Exception:
                pass
            self._disc_syncer = None
        if self._con is not None:
            try:
                self._con.close()
            except Exception:
                pass
            self._con = None
        self.monitor_stopped.emit()

    @Slot()
    def _handle_ram_critical(self):
        """Auto-restart del .exe ante RAM crítica (watchdog RNF-06). Corre en el MAIN
        thread (la signal lo marshalla desde el monitor). Relanza un proceso fresco —
        hereda el entorno, así que conserva las env vars de qa_launch (DANIBOD_DB_PATH,
        BADGE_HARVEST, etc.) — y cierra el actual. La cosecha persiste (equip_map + npz)
        → sin pérdida. Dispara una sola vez por proceso."""
        if self._restart_requested:
            return
        self._restart_requested = True
        import os
        import sys
        from PySide6.QtCore import QProcess, QTimer
        from PySide6.QtWidgets import QApplication
        try:
            log.critical("Auto-restart por RAM (RNF-06): relanzando %s", sys.executable)
            # El hijo hereda el entorno → marcarlo para que bypasee el single-instance
            # (esta instancia sigue viva ~1.2s; sin esto el hijo se autocierra → 0 apps).
            os.environ["DANIBOD_RESTART"] = "1"
            # Reconstruir args: corrido desde FUENTE (`python -m app.main`) sys.argv[1:] va
            # VACÍO → relanzaba python pelado y la app NO volvía (parecía crash, QA 2026-06-19).
            # Detectar el `-m` por __main__.__spec__ y reponerlo. Frozen (.exe) → spec None →
            # sys.argv[1:] como antes.
            import __main__
            spec = getattr(__main__, "__spec__", None)
            if spec is not None and getattr(spec, "name", None):
                args = ["-m", spec.name] + sys.argv[1:]
            else:
                args = sys.argv[1:]
            ok = QProcess.startDetached(sys.executable, args)
            log.info("startDetached → %s", ok)
        except Exception:
            log.exception("Falló el relanzamiento del .exe; se cierra igual")
        # Pequeño respiro para que el proceso nuevo arranque y el toast/log se vean,
        # luego cerrar este. La cosecha ya está persistida en disco.
        QTimer.singleShot(1200, QApplication.quit)

    @Slot()
    def toggle_pause(self):
        if self._monitor is None:
            return
        paused = self._monitor.toggle_pause()
        self.pause_changed.emit(paused)

    @Slot()
    def force_scan(self):
        if self._monitor is None:
            # Si auto-detect está activo y la ventana de ZZZ está abierta, arrancar.
            if self._auto_detect_enabled:
                from app.core.capturer import find_zzz_window
                if find_zzz_window() is not None:
                    self.start()
                    if self._monitor is not None:
                        self._monitor.force_scan()
                    return
            self.error_occurred.emit("Iniciar captura primero (F8 sin monitor activo).")
            return
        try:
            self._monitor.force_scan()
        except Exception as exc:
            log.exception("force_scan failed")
            self.error_occurred.emit(f"force_scan: {exc}")

    # ---- Auto-detect (arranque automático cuando ZZZ está abierto) -------------

    @Slot(bool)
    def set_auto_detect(self, enabled: bool):
        """Habilita/deshabilita el watcher que arranca el monitor al detectar ZZZ."""
        self._auto_detect_enabled = enabled
        if enabled:
            self._was_window_present = False
            self._auto_detect_timer.start()
            self.auto_start_enabled.emit(True)
            # Disparar primera verificación inmediata
            self._check_zzz_window()
        else:
            self._auto_detect_timer.stop()
            self.auto_start_enabled.emit(False)

    def _check_zzz_window(self):
        """Cada 3s: ¿está abierta la ventana de ZZZ? Sync el estado del monitor."""
        try:
            from app.core.capturer import find_zzz_window
            window = find_zzz_window()
        except Exception:
            window = None

        present = window is not None
        if present and not self._was_window_present:
            # Ventana apareció — arrancar monitor si no está activo
            if self._monitor is None:
                log.info("ZZZ detectado, arrancando monitor automaticamente")
                self.start()
        elif not present and self._was_window_present:
            # Ventana desapareció — detener monitor
            if self._monitor is not None:
                log.info("ZZZ cerrado, deteniendo monitor")
                self.stop()
        self._was_window_present = present

    # ---- Init de dependencias --------------------------------------------------

    def _init_dependencies(self):
        # OCR — PaddleOCR es el backend PRIMARIO (Hito 2.8, 2026-05-31):
        # determinístico sobre S18 (11/11 stats en los 7 fixtures), resuelve
        # el no-determinismo de Tesseract. Tesseract queda como fallback solo
        # si PaddleOCR no está disponible en el entorno.
        self._ocr = None
        try:
            import paddleocr  # noqa: F401  — verifica disponibilidad antes de elegir
            from app.core.ocr_paddle import PaddleBackend
            self._ocr = PaddleBackend(lang="es")
            log.info("OCR backend: PaddleOCR (primario) — lang=es")
        except Exception as e:  # ImportError u otro fallo de entorno
            log.warning(
                "PaddleOCR no disponible (%s); cayendo a Tesseract fallback",
                e, exc_info=True,
            )
            tess = _find_tesseract()
            if tess is None:
                raise RuntimeError(
                    "Ni PaddleOCR ni Tesseract estan disponibles.\n"
                    "PaddleOCR es el backend esperado. Reinstalar con:\n"
                    "    pip install paddlepaddle==2.6.2 paddleocr==2.8.1\n"
                    "O instalar Tesseract: winget install UB-Mannheim.TesseractOCR"
                )
            from app.core.ocr_tesseract import TesseractBackend
            self._ocr = TesseractBackend(tesseract_cmd=tess)
            log.info("OCR backend: Tesseract (fallback) — %s", tess)

        # Detector
        from app.core.detector import ScreenDetector
        self._detector = ScreenDetector()
        if self._detector.loaded_count < 7:
            raise RuntimeError(
                f"Detector solo tiene {self._detector.loaded_count} templates. "
                f"Ejecutar: python tools/build_templates.py"
            )

        # DB + repos
        from app.db.connection import get_connection, get_db_path
        from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo
        from app.core.score_normalizer import ScoringContext
        # SOLO LECTURA (agents/archetypes/sets, datos de referencia): la UI (thread principal)
        # y el thread del monitor (recomendación al parsear un disco S3) comparten esta conexión.
        # check_same_thread=False la habilita cross-thread; SQLite serializa. Sin escrituras aquí
        # (las escrituras van por DiscSyncer, su propia conexión) → sin riesgo de corrupción.
        self._con = get_connection(self._db_path, check_same_thread=False)
        self._agent_repo = AgentRepo(self._con)
        self._archetype_repo = ArchetypeRepo(self._con)
        self._disc_set_repo = DiscSetRepo(self._con)
        self._scoring_ctx = ScoringContext()

        # Persistencia S17 (disco equipado): escribe disco + asignación (sin
        # scoring). Usa la MISMA DB resuelta que las lecturas (en el .exe vive en
        # %LOCALAPPDATA%, no la relativa al source). Backup de sesión RNF-01 una
        # sola vez antes de habilitar writes.
        from app.core.sync_equip import DiscSyncer
        from app.core.sync_agent_stats import AgentStatsSyncer
        resolved_db = self._db_path or get_db_path()
        self._backup_db_session(resolved_db)
        self._disc_syncer = DiscSyncer(db_path=Path(resolved_db))
        # Persistencia EN VIVO de stats base de agente (S18 → agents). Mismo patrón
        # que el disc syncer: write propio + guard readonly. Usa el backup de sesión
        # ya hecho arriba (RNF-01).
        self._agent_stats_syncer = AgentStatsSyncer(db_path=Path(resolved_db))
        # Desempate de dueño por contexto (build) para badges ambiguos por look-alike.
        # Reusa el resolutor de set del disc_syncer (fuzzy sin acentos + difflib) para no
        # duplicar la lógica. El monitor lo usa solo cuando el badge se abstiene por margen.
        from app.core.owner_tiebreak import OwnerTiebreaker
        self._owner_tiebreaker = OwnerTiebreaker(
            db_path=Path(resolved_db),
            resolve_set_id=self._disc_syncer._resolve_set_id,
        )
        # Gate de confianza por flujo de farmeo (S13→S14→S2→S3): distingue un farmeo de discos
        # de otros "resultados de desafío". Sin DB ni dependencias; solo observa transiciones.
        from app.core.farm_session import FarmSession
        # DANIBOD_FARM_STATE (solo QA, lo setea qa_launch.ps1): ruta del breadcrumb de la última
        # predicción S13. Persistir permite que un REINICIO de la app (tras aplicar un fix)
        # recargue el contexto de farmeo sin revisitar S13 (la predicción vive en memoria y se
        # perdía en cada relance). Sin la env-var (producción) → FarmSession sin persistencia.
        import os as _os
        _farm_state = _os.environ.get("DANIBOD_FARM_STATE") or None
        self._farm_session = FarmSession(state_path=_farm_state)
        if _farm_state and _os.environ.get("DANIBOD_RESTORE_FARM"):
            import time as _time
            _restored = self._farm_session.restore(_time.monotonic())
            if _restored:
                _node, _sets = _restored
                _names = " / ".join(en for _sid, en in _sets)
                log.info("[farmeo] contexto QA restaurado: nodo '%s' → %s", _node, _names)
            else:
                log.info("[farmeo] restore QA solicitado pero sin contexto previo que cargar")
        # Catálogo de nodos de farmeo (S13): título del nodo → 2 sets que dropea. Resuelve
        # nombre_en → set_id contra la DB (disc_sets). Display-only; una carga fallida NO
        # debe tumbar el arranque (feature opcional), solo se loguea.
        try:
            from app.core.farm_nodes import FarmNodeCatalog
            set_ids = {e.nombre_en: e.id for e in self._disc_set_repo.get_all() if e.nombre_en}
            self._farm_node_catalog = FarmNodeCatalog.from_resources(set_ids)
            if self._farm_node_catalog.unresolved:
                log.warning("farm_nodes: sets sin resolver → %s",
                            self._farm_node_catalog.unresolved)
        except Exception:
            log.exception("No se pudo cargar el catálogo de nodos de farmeo (S13)")
            self._farm_node_catalog = None
        # Matcher de set por badge del disco (S2): refs en memoria desde los package renders.
        # Display-only y opcional → una falla de carga no debe tumbar el arranque.
        try:
            from app.core.set_badge_matcher import SetBadgeMatcher
            self._set_badge_matcher = SetBadgeMatcher.from_package_badges()
        except Exception:
            log.exception("No se pudo cargar el matcher de badges de set (S2)")
            self._set_badge_matcher = None

    # ---- Callbacks desde el Monitor (thread daemon) ----------------------------

    def _on_state_from_monitor(self, state):
        # Signals son thread-safe en Qt (cross-thread auto-marshalled si hay event loop)
        from app.core.detector import describe_state, CAPTURE_DISC_STATES, UPGRADE_STATES, NON_CAPTURE_STATES
        # Edge: cualquier cambio de estado resetea la firma del log de stats S18, de
        # modo que re-entrar a Atributos base loguee el resultado 1 vez.
        self._last_stats_sig = None
        self.state_changed.emit(state.code, state.confidence)
        desc = describe_state(state.code)

        # Sufijo "slot N" si el estado tiene info de slot (S17, S9-con-seleccion)
        has_slot = getattr(state, "slot", None) is not None
        slot_suffix = f" · slot {state.slot}" if has_slot else ""

        if state.code == "S12":
            tmpl_hint = f" (mejor match parcial: {state.template_name}, conf={state.confidence:.2f})" if state.template_name else ""
            self.log_message.emit(f"[pantalla] no reconocida — posible menú/transición{tmpl_hint}")
        elif state.code in CAPTURE_DISC_STATES:
            self.log_message.emit(f"[pantalla] {state.code} — {desc}{slot_suffix} · CAPTURABLE (conf {state.confidence:.2f})")
        elif state.code in UPGRADE_STATES:
            self.log_message.emit(f"[pantalla] {state.code} — {desc} · UPGRADE sync (conf {state.confidence:.2f})")
        elif state.code in NON_CAPTURE_STATES:
            # Si hay slot detectado (S9-con-disco-seleccionado, S17), el disco
            # SÍ es visible aunque la pantalla siga siendo non-capture (todavia
            # no la captura el flujo principal — eso es parser_disc en S3/S6/S7).
            visibility = f" · disco slot {state.slot} seleccionado" if has_slot else " · sin disco visible"
            self.log_message.emit(f"[pantalla] {state.code} — {desc}{visibility} (conf {state.confidence:.2f})")
        else:
            self.log_message.emit(f"[pantalla] {state.code} — {desc}{slot_suffix} (conf {state.confidence:.2f})")

    def _on_agent_detail_from_monitor(self, state, agent_name, identified, source=None):
        """
        Logging PERSISTENTE de S8 (Equipamiento) y S19 (Habilidades).
        Se invoca en cada ciclo de cadencia (~1.5 s) mientras se está en esas
        pantallas, igual que la extracción continua de S18. Muestra el PJ:
        identificado por herencia de Atributos base (anchor) o por el matcher de
        avatar (switch directo). Si no logra identificarlo, lo avisa sin mentir.
        """
        # El menú de personajes (S15) reusa este callback solo para mostrar el PJ, pero NO es
        # la pantalla de Equipamiento: el monitor ya loguea "[S15] Menú de personajes reconocido".
        # Emitimos una única línea con etiqueta correcta y salimos (evita el confuso
        # "S15 — Equipamiento reconocida" y el origen mal atribuido "heredado de Atributos base").
        if source == "menu":
            if identified and agent_name:
                self.log_message.emit(f"[reconocido] {agent_name} (del menú de personajes)")
            return
        label = "Habilidades" if state.code == "S19" else "Equipamiento"
        if identified and agent_name:
            if source == "avatar":
                origen = "por avatar"
            elif source == "sostenido":
                origen = "sostenido del último reconocido"
            else:
                origen = "heredado de Atributos base"
            self.log_message.emit(f"[reconocido] {agent_name} ({origen})")
            self.log_message.emit(f"[pantalla] {state.code} — {label} reconocida")
        else:
            self.log_message.emit(
                f"[pantalla] {state.code} — {label} reconocida · "
                f"PJ sin identificar (esperá a que la barra de personajes esté visible)"
            )

    def _on_disc_rejected_from_monitor(self, disc, state, reason: str):
        """Disco parseado pero descartado por baja confianza u otro motivo."""
        notas_str = ", ".join(disc.notas) if disc.notas else "sin notas"
        msg = (
            f"[descartado] {reason}. "
            f"set_raw={disc.set_name_raw!r} slot={disc.slot} "
            f"main_raw={disc.main_stat_raw!r} | notas: {notas_str}"
        )
        self.log_message.emit(msg)

    def _on_diagnostic_from_monitor(self, msg: str):
        """Mensajes de diagnóstico del loop (heartbeat, ventana no encontrada, etc)."""
        self.log_message.emit(f"[diag] {msg}")

    def _on_agent_stats_from_monitor(self, stats, state):
        """Stats de agente extraídos desde S18 (Atributos base).

        Emite TRES líneas al LivePanel:
          [reconocido] S18 perfil agente: <nombre> (conf X.XX)
          [stats] Nv=N PV=X ATK=X ... ER=X
          [completo] / [parcial] estado de la extracción

        Los 11 atributos base están siempre presentes (None se muestra como '-').
        El último mensaje indica si la extracción es completa o si faltan
        campos a re-intentar con F8 (el aggregator los completará).

        Madurez role-aware:
          - Roles Disruptivos requieren `fuerza_bruta` (no `tasa_perforacion`).
          - Resto de roles (Ataque, Aturdimiento, Anomalía, Defensa, Soporte)
            requieren `tasa_perforacion` (no `fuerza_bruta`).
          - Si el rol no se identificó todavía, asumimos NO-disruptivo (caso
            mayoritario en el roster).
        """
        from dataclasses import asdict

        # Helper: formato consistente para valor o '-' si es None
        def _v(x):
            return "-" if x is None else x

        def _pct(x):
            return "-" if x is None else f"{x * 100:.1f}%"

        # ---- Determinar stats requeridos según rol ----
        rol_norm = (stats.rol or "").lower()
        is_disruptivo = "disruptiv" in rol_norm
        # Los dos slots inferiores son role-specific y mutuamente excluyentes:
        #   Disruptivos:  Fuerza Bruta (FB)        + Acumulación Adrenalina (AD)
        #   Resto:        Tasa de Perforación (TP) + Recuperación de Energía (ER)
        required_keys = [
            "nivel", "pv", "ataque", "defensa", "impacto",
            "prob_crit", "dano_crit",
            "tasa_anomalia", "maestria_anomalia",
        ]
        if is_disruptivo:
            required_keys += ["fuerza_bruta", "acumulacion_adrenalina"]
        else:
            required_keys += ["tasa_perforacion", "recuperacion_energia"]

        # Mapeo a etiquetas legibles para mostrar al usuario
        _LABELS = {
            "nivel": "Nv", "pv": "PV", "ataque": "ATK", "defensa": "DEF",
            "impacto": "IMP", "prob_crit": "CR", "dano_crit": "CD",
            "tasa_anomalia": "TA", "maestria_anomalia": "MA",
            "tasa_perforacion": "TP", "fuerza_bruta": "FB",
            "recuperacion_energia": "ER", "acumulacion_adrenalina": "AD",
        }
        missing = [k for k in required_keys if getattr(stats, k) is None]
        missing_labels = [_LABELS.get(k, k) for k in missing]

        # El panel de stats es un binding de datos: se actualiza siempre.
        payload = asdict(stats)
        payload["state_code"] = state.code
        self.agent_stats_detected.emit(payload)

        # Logging EDGE-triggered: emitir el log (archivo + 3 líneas UI) solo cuando
        # el RESULTADO cambia. La firma incluye los 11 stats + missing → un parcial
        # que luego se completa cambia la firma y re-loguea (requisito explícito).
        # `conf` se excluye (fluctúa). Se resetea al cambiar de estado
        # (_on_state_from_monitor) → re-entrar a S18 loguea 1 vez.
        stats_sig = (
            stats.agente_nombre, stats.nivel, stats.pv, stats.ataque, stats.defensa,
            stats.impacto, stats.prob_crit, stats.dano_crit, stats.tasa_anomalia,
            stats.maestria_anomalia, stats.tasa_perforacion, stats.fuerza_bruta,
            stats.recuperacion_energia, stats.acumulacion_adrenalina, tuple(missing),
        )
        if stats_sig == self._last_stats_sig:
            return
        self._last_stats_sig = stats_sig

        # Persistencia EN VIVO → agents (RF-04). Corre solo cuando el resultado
        # cambió (post-dedup de firma) y fuera de readonly. El syncer abstiene si la
        # identidad no resuelve y hace update PARCIAL solo de los campos que cambiaron.
        try:
            self._agent_stats_syncer.sync(stats)
        except Exception:
            log.exception("Error en sync en vivo de stats de agente")

        log.info(
            "Stats agente %s (%s/%s): Nv=%s PV=%s ATK=%s DEF=%s IMP=%s "
            "CR=%s CD=%s TA=%s MA=%s TP=%s FB=%s ER=%s AD=%s conf=%.2f missing=%s",
            stats.agente_nombre or "?",
            stats.rol or "?", stats.elemento or "?",
            _v(stats.nivel), _v(stats.pv), _v(stats.ataque), _v(stats.defensa),
            _v(stats.impacto),
            _pct(stats.prob_crit), _pct(stats.dano_crit),
            _v(stats.tasa_anomalia), _v(stats.maestria_anomalia),
            _pct(stats.tasa_perforacion), _v(stats.fuerza_bruta),
            _v(stats.recuperacion_energia), _v(stats.acumulacion_adrenalina),
            stats.confianza_global,
            missing_labels,
        )

        # Línea 1: pantalla reconocida + nombre + rol + elemento (de pantalla)
        nombre = stats.agente_nombre or "agente"
        rol_str = f" · {stats.rol}" if stats.rol else ""
        elem_str = f" · {stats.elemento}" if stats.elemento else ""
        self.log_message.emit(
            f"[reconocido] S18 perfil agente: {nombre}{rol_str}{elem_str} "
            f"(conf {state.confidence:.2f})"
        )

        # Línea 2: TODOS los 11 stats con placeholder '-' para None
        self.log_message.emit(
            f"[stats] Nv={_v(stats.nivel)} PV={_v(stats.pv)} "
            f"ATK={_v(stats.ataque)} DEF={_v(stats.defensa)} "
            f"IMP={_v(stats.impacto)} "
            f"CR={_pct(stats.prob_crit)} CD={_pct(stats.dano_crit)} "
            f"TA={_v(stats.tasa_anomalia)} MA={_v(stats.maestria_anomalia)} "
            f"TP={_pct(stats.tasa_perforacion)} FB={_v(stats.fuerza_bruta)} "
            f"ER={_v(stats.recuperacion_energia)} AD={_v(stats.acumulacion_adrenalina)}"
        )

        # Línea 3: estado de la extracción
        if not missing:
            self.log_message.emit(
                f"[completo] extracción exitosa - {len(required_keys)}/{len(required_keys)} stats capturados"
            )
        else:
            self.log_message.emit(
                f"[parcial] extracción incompleta - faltan {len(missing)}/"
                f"{len(required_keys)}: {', '.join(missing_labels)} "
                f"- el aggregator completa en los próximos ciclos (extracción continua)"
            )

    def _backup_db_session(self, db_path) -> None:
        """
        Backup de sesión RNF-01: copia única de la DB antes de habilitar writes
        de captura. Gitignoreado (db/danibod_zzz_v2.backup_*.db). Best-effort: si
        falla (permiso/espacio) se loguea pero no bloquea el arranque.
        """
        import shutil
        from datetime import datetime
        try:
            src = Path(db_path)
            if not src.exists():
                return
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = src.with_name(f"{src.stem}.backup_session_{ts}.db")
            shutil.copy2(src, dst)
            log.info("Backup de sesión RNF-01: %s", dst)
        except Exception:
            log.exception("No se pudo crear backup de sesión (se continúa)")

    def _on_disc_from_monitor(self, disc_parsed, state):
        """
        El monitor parseó un disco. Calculamos la recomendación y emitimos
        el payload listo para que LivePanel + Toast lo consuman.

        S17 (disco equipado): persistencia ENFOCADA (disco + asignación PJ + bono,
        sin scoring — fase posterior) vía DiscSyncer.persist_s17_disc, y se loguea
        el disco completo. El resto (S3/S6/S7, discos nuevos) va al recommender.
        """
        try:
            if state.code in ("S17", "S9"):
                # S9 (inventario global) replica la captura de S17: misma persistencia
                # enfocada (disco + asignación por dueño). Los discos EQUIPADOS (badge
                # confiable) se upsertean por (PJ, slot); los LIBRES (sin dueño) no se
                # persisten aún (persist_s17_disc exige PJ confiable; loose = follow-up).
                result = None
                if self._disc_syncer is not None:
                    result = self._disc_syncer.persist_s17_disc(disc_parsed)
                # Persistió (cambió inventory_discs/asignación) → invalidar los índices del
                # tiebreaker para que el próximo desempate vea los datos nuevos (build en vivo).
                if result is not None and self._owner_tiebreaker is not None:
                    self._owner_tiebreaker.mark_dirty()
                # (El toast REEMPLAZADO ya NO se dispara acá: lo emite `_on_replacement_from_monitor`
                # cuando el monitor OBSERVA el cambio de dueño, sin depender de que la persistencia
                # haya movido una fila. Así sale también en read-only.)
                self._log_s17_extraction(disc_parsed, result)
                return
            payload = self._build_payload(disc_parsed, state)
            self.disc_detected.emit(payload)
        except Exception as exc:
            log.exception("Error procesando disco capturado")
            self.error_occurred.emit(f"Procesando disco: {exc}")

    def _on_replacement_from_monitor(self, ev: dict) -> None:
        """El monitor OBSERVÓ que un disco cambió de dueño → toast. Dos sabores según `kind`:

          - `reemplazo` — el disco era de otro PJ (diálogo S23 + check por badge) → REEMPLAZADO.
          - `equipado`  — el disco estaba LIBRE (badge ausente + botón) → AHORA EN.

        No toca la DB: resuelve el `set_id` con `_lookup_set_id` (lectura) y los assets por
        filesystem. Es a propósito — el toast afirma lo que se vio en pantalla, no lo que la
        persistencia logró escribir; por eso funciona igual en read-only. La corrección de la DB
        corre por su cuenta en `persist_s17_disc` y ya no gatilla nada visual."""
        try:
            set_name = ev.get("set_name")
            payload = self._build_replacement_payload({
                "set_name": set_name,
                "set_id": self._lookup_set_id(set_name),
                "slot": ev.get("slot", 0),
                "from_name": ev.get("from_name"),
                "to_name": ev.get("to_name"),
            })
            if ev.get("kind") == "equipado":
                self.disc_equipped.emit(payload)
            else:
                self.disc_replaced.emit(payload)
        except Exception:
            log.exception("Error armando el toast de equipamiento")

    def _build_replacement_payload(self, ev: dict) -> dict:
        """Evento {set_name, set_id, slot, from_name, to_name} → payload del toast (logo del set
        + avatares de los 2 PJs, resueltos por asset_resolver). Solo lecturas — mismo estilo que
        `_build_payload` del toast de recomendación."""
        from app.core.asset_resolver import set_logo_path, agent_avatar_path
        set_name = ev.get("set_name") or "?"
        set_logo = None
        set_id = ev.get("set_id")
        if set_id and self._disc_set_repo is not None:
            try:
                for s in self._disc_set_repo.get_all():
                    if s.id == set_id:
                        pth = set_logo_path(s.nombre_en)
                        set_logo = str(pth) if pth else None
                        set_name = s.nombre       # canónico de la DB
                        break
            except Exception:
                pass

        def _avatar(name):
            if not name:
                return None
            try:
                pth = agent_avatar_path(name, variant="ico")
                return str(pth) if pth else None
            except Exception:
                return None

        return {
            "set": set_name, "slot": ev.get("slot", 0), "rarity": "S", "set_logo": set_logo,
            "from_agent": ev.get("from_name") or "—", "from_avatar": _avatar(ev.get("from_name")),
            "to_agent": ev.get("to_name") or "—", "to_avatar": _avatar(ev.get("to_name")),
        }

    @staticmethod
    def _fmt_sub(s) -> str:
        """Formatea un substat con los rolls entre paréntesis tras el valor:
        'ATK 38 (+1)' · 'ATK% 3%' · 'Daño Crítico 9.6% (+1)'."""
        nombre = s.nombre_canon or s.nombre_raw or "?"
        val = ""
        if s.valor is not None:
            unit = "%" if s.unidad == "%" else ""
            val = f" {s.valor:g}{unit}"
        roll = f" (+{s.rolls})" if s.rolls else ""
        return f"{nombre}{val}{roll}"

    def _log_s17_extraction(self, disc, result=None) -> None:
        """Loguea la extracción completa de un disco equipado S17 (estilo S18)."""
        set_name = disc.set_name_canon or disc.set_name_raw or "?"
        rareza = f" · {disc.rareza}-rank" if disc.rareza in ("S", "A", "B") else ""
        nivel = f"Nivel {disc.nivel}/15" if disc.nivel else "Nivel ?"
        self.log_message.emit(
            f"[reconocido] S17 disco equipado: {set_name} (slot {disc.slot}) · "
            f"{nivel}{rareza} (conf {disc.confianza_global:.2f})"
        )
        main = disc.main_stat_canon or disc.main_stat_raw or "?"
        mval = ""
        if disc.main_valor is not None:
            unit = "%" if disc.main_unidad == "%" else ""
            mval = f" {disc.main_valor:g}{unit}"
        self.log_message.emit(f"[disco] main: {main}{mval}")
        if disc.subs:
            self.log_message.emit(
                "[disco] subs: " + " · ".join(self._fmt_sub(s) for s in disc.subs)
            )
        # PJ asignado (item #5): del DiscParsed (marcado por el monitor con guarda).
        if disc.agente_asignado_nombre:
            self.log_message.emit(
                f"[asignado] equipado en: {disc.agente_asignado_nombre} "
                f"(conf {disc.agente_asignado_conf:.2f})"
            )
        else:
            self.log_message.emit("[asignado] sin PJ confiable → no se tocó la asignación")
        # Estado de equipamiento (VISUALIZACIÓN, modo navegación de grilla): equipado
        # o no + qué PJ, independiente de si se persistió. None = no aplicable (S3/S6/S7).
        if disc.equip_detectado is not None:
            if disc.equip_pj_visual:
                self.log_message.emit(f"[equipamiento] equipado por: {disc.equip_pj_visual}")
            elif disc.equip_libre:
                self.log_message.emit("[equipamiento] LIBRE (disponible)")
            elif not disc.equip_detectado:
                self.log_message.emit("[equipamiento] badge no localizado (reposá sobre el disco)")
            else:
                self.log_message.emit("[equipamiento] equipado · dueño incierto")
        # Conjunto: tier ACTIVO para este disco (2pc vs 4pc, por color del texto)
        # + el bono 2pc curado (corto). NO se vuelca la descripción 4pc completa.
        set_name = disc.set_name_canon or disc.set_name_raw or "?"
        if disc.set_active_tier in (2, 4):
            self.log_message.emit(
                f"[conjunto] {set_name} · tier activo: {disc.set_active_tier}pc"
            )
        else:
            self.log_message.emit(f"[conjunto] {set_name} · tier activo: sin detectar")
        if result is not None and result.set_bonus_2p:
            self.log_message.emit(f"[conjunto] 2pc: {result.set_bonus_2p}")
        if result is not None:
            self.log_message.emit(
                f"[persistido] disco id={result.disc_id} ({result.trigger})"
            )
            if result.set_composition:
                self.log_message.emit(f"[composición] {result.set_composition}")
        self.log_message.emit(f"[completo] disco extraído — {len(disc.subs)}/4 substats")
        if disc.notas:
            self.log_message.emit(f"[disco] notas: {', '.join(disc.notas)}")

    def _build_payload(self, disc_parsed, state) -> dict:
        from app.core.recommender import recomendar
        from app.core.asset_resolver import set_logo_path, agent_avatar_path
        from app.db.repositories import Disc

        # Convertir DiscParsed → Disc para el recommender
        set_id = self._lookup_set_id(disc_parsed.set_name_canon or disc_parsed.set_name_raw)
        subs_tuples = [
            (s.nombre_canon, s.valor, s.unidad, s.rolls)
            for s in disc_parsed.subs
            if s.nombre_canon
        ]
        disc = Disc(
            id=-1,
            set_id=set_id or 0,
            slot=disc_parsed.slot,
            main_stat=disc_parsed.main_stat_canon,
            main_valor=disc_parsed.main_valor,
            main_unidad=disc_parsed.main_unidad,
            subs=subs_tuples,
            nivel=disc_parsed.nivel,
            equipado=0,
            agente_asignado=None,
        )

        rec = recomendar(
            disc,
            self._agent_repo,
            self._archetype_repo,
            self._disc_set_repo,
            self._scoring_ctx,
        )

        # Resolver set logo (necesitamos nombre_en desde DB)
        set_logo: str | None = None
        set_name_es = disc_parsed.set_name_canon or disc_parsed.set_name_raw
        if set_id and self._disc_set_repo is not None:
            try:
                for s in self._disc_set_repo.get_all():
                    if s.id == set_id:
                        p = set_logo_path(s.nombre_en)
                        set_logo = str(p) if p else None
                        set_name_es = s.nombre   # canónico de la DB (evita mostrar 'Salön' del OCR)
                        break
            except Exception:
                pass

        # Resolver avatar del target agent (extend = cuerpo entero)
        target_avatar: str | None = None
        target_mind = 0
        if rec.agente_id is not None and self._agent_repo is not None:
            try:
                agent = self._agent_repo.get_by_id(rec.agente_id)
                if agent is not None:
                    p = agent_avatar_path(agent.nombre, variant="extend")
                    target_avatar = str(p) if p else None
                    # mindscape no está en el Agent dataclass del repo actual; leer directo de DB
                    row = self._con.execute(
                        "SELECT mindscape FROM agents WHERE id=?", (rec.agente_id,)
                    ).fetchone()
                    target_mind = row["mindscape"] if row else 0
            except Exception:
                pass

        # Build payload final
        main_value = ""
        if disc_parsed.main_valor is not None:
            unit = "%" if disc_parsed.main_unidad == "%" else ""
            main_value = f"{disc_parsed.main_valor:.1f}{unit}"

        subs_summary = " · ".join(
            (s.nombre_canon or s.nombre_raw)[:8]
            for s in disc_parsed.subs[:4]
            if s.nombre_canon or s.nombre_raw
        )
        # Detalle completo de substats (nombre + valor + rolls) para el log y la card en vivo.
        subs_detail = [
            self._fmt_sub(s).strip()
            for s in disc_parsed.subs
            if s.nombre_canon or s.nombre_raw
        ]

        return {
            "variant":       rec.tipo,
            "set":           set_name_es or "?",
            "slot":          disc_parsed.slot,
            "rarity":        disc_parsed.rareza if disc_parsed.rareza in ("S", "A", "B") else "S",
            "main":          disc_parsed.main_stat_canon or disc_parsed.main_stat_raw or "?",
            "main_value":    main_value,
            "subs":          subs_summary,
            "subs_detail":   subs_detail,
            "target":        rec.agente_nombre or "—",
            "mind":          target_mind,
            "score":         round(rec.score_norm * 100, 1),
            "threshold":     0.75 if rec.tipo == "equipar" else 0.50,
            "urgency":       min(1.0, rec.score_norm * 1.1),
            "confianza":     disc_parsed.confianza_global,
            "state_code":    state.code,
            "set_logo":      set_logo,
            "target_avatar": target_avatar,
        }

    def _lookup_set_id(self, name: str | None) -> int | None:
        """Resuelve nombre de set (OCR) → set_id, insensible a tildes/mojibake: el OCR del
        crop lee la tilde inestable ('Salón'/'Salön') → normalizar con `_norm_key` (sin
        diacríticos) para que igual resuelva (si no, se perdía el logo y el nombre canónico).

        Fallback en flujo de farmeo: si el match exacto falla porque el OCR cambió una PALABRA
        entera del nombre ('Aria brillante'→'Aria radiante', que `_norm_key` no arregla), elegir
        entre los 2 sets PREDICHOS en S13 el de nombre más parecido (seguro con pocos candidatos;
        el resolver global de sync abstiene acá por su cutoff alto). QA farmeo 2026-07-09."""
        if not name or self._disc_set_repo is None:
            return None
        # Resolvedor robusto (exact → fuzzy sin acentos → difflib con guarda de ambigüedad),
        # el MISMO que usan S4/S5/sync. Antes era match EXACTO por _norm_key → frágil al ruido
        # OCR del título de disco ('Firmamento llameante'→'Firmamento Ilameante', ll→I) → no
        # resolvía → se perdía el logo/ICO y el nombre canónico (QA tienda música 2026-07-09).
        try:
            sid = self._disc_set_repo.resolve_id(name)
        except Exception:
            sid = None
        if sid is not None:
            return sid
        # Sin match confiable → probar contra los sets predichos del nodo (si hay farmeo activo).
        # Cubre el caso de PALABRA entera cambiada ('Aria brillante'→'Aria radiante'), que el
        # resolver global abstiene por su cutoff alto.
        if self._farm_session is not None:
            try:
                import time
                from app.core.farm_nodes import best_predicted_set_id
                pred = self._farm_session.predicted(time.monotonic())
                if pred:
                    by_id = {s.id: s.nombre for s in self._disc_set_repo.get_all()}
                    cands = [(sid, by_id[sid]) for sid, _en in pred[1] if sid in by_id]
                    return best_predicted_set_id(name, cands)
            except Exception:
                log.debug("fallback de set por predicción falló", exc_info=True)
        return None

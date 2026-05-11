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
    error_occurred = Signal(str)
    # Mensaje informativo crudo para el log (estado, captura descartada, etc).
    log_message = Signal(str)

    # Auto-start: el monitor arranca cuando se detecta el proceso de ZZZ
    auto_start_enabled = Signal(bool)        # True cuando se habilita el auto-arranque

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

        # Watcher de proceso ZZZ — arranca/detiene el monitor automáticamente
        # según la presencia de la ventana del juego.
        self._auto_detect_timer = QTimer(self)
        self._auto_detect_timer.setInterval(self.AUTO_DETECT_INTERVAL_S * 1000)
        self._auto_detect_timer.timeout.connect(self._check_zzz_window)
        self._auto_detect_enabled = False
        self._was_window_present = False

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

        from app.core.monitor import Monitor
        self._monitor = Monitor(
            ocr=self._ocr,
            detector=self._detector,
            on_disc=self._on_disc_from_monitor,
            on_state_change=self._on_state_from_monitor,
            on_disc_rejected=self._on_disc_rejected_from_monitor,
            set_repo=self._disc_set_repo,
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
        if self._con is not None:
            try:
                self._con.close()
            except Exception:
                pass
            self._con = None
        self.monitor_stopped.emit()

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
        # OCR
        tess = _find_tesseract()
        if tess is None:
            raise RuntimeError(
                "Tesseract OCR no esta instalado. Ejecutar:\n"
                "    winget install UB-Mannheim.TesseractOCR\n"
                "Despues reiniciar la app."
            )
        from app.core.ocr_tesseract import TesseractBackend
        self._ocr = TesseractBackend(tesseract_cmd=tess)

        # Detector
        from app.core.detector import ScreenDetector
        self._detector = ScreenDetector()
        if self._detector.loaded_count < 7:
            raise RuntimeError(
                f"Detector solo tiene {self._detector.loaded_count} templates. "
                f"Ejecutar: python tools/build_templates.py"
            )

        # DB + repos
        from app.db.connection import get_connection
        from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo
        from app.core.score_normalizer import ScoringContext
        self._con = get_connection(self._db_path)
        self._agent_repo = AgentRepo(self._con)
        self._archetype_repo = ArchetypeRepo(self._con)
        self._disc_set_repo = DiscSetRepo(self._con)
        self._scoring_ctx = ScoringContext()

    # ---- Callbacks desde el Monitor (thread daemon) ----------------------------

    def _on_state_from_monitor(self, state):
        # Signals son thread-safe en Qt (cross-thread auto-marshalled si hay event loop)
        from app.core.detector import describe_state
        self.state_changed.emit(state.code, state.confidence)
        desc = describe_state(state.code)
        if state.code == "S12":
            # No hubo match — mostrar el mejor match parcial para diagnóstico
            tmpl_hint = f" (mejor match parcial: {state.template_name}, conf={state.confidence:.2f})" if state.template_name else ""
            self.log_message.emit(f"[detector] sin match{tmpl_hint}")
        else:
            self.log_message.emit(f"[estado] {state.code} — {desc} (conf {state.confidence:.2f})")

    def _on_disc_rejected_from_monitor(self, disc, state, reason: str):
        """Disco parseado pero descartado por baja confianza u otro motivo."""
        notas_str = ", ".join(disc.notas) if disc.notas else "sin notas"
        msg = (
            f"[descartado] {reason}. "
            f"set_raw={disc.set_name_raw!r} slot={disc.slot} "
            f"main_raw={disc.main_stat_raw!r} | notas: {notas_str}"
        )
        self.log_message.emit(msg)

    def _on_disc_from_monitor(self, disc_parsed, state):
        """
        El monitor parseó un disco. Calculamos la recomendación y emitimos
        el payload listo para que LivePanel + Toast lo consuman.
        """
        try:
            payload = self._build_payload(disc_parsed, state)
            self.disc_detected.emit(payload)
        except Exception as exc:
            log.exception("Error procesando disco capturado")
            self.error_occurred.emit(f"Procesando disco: {exc}")

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

        return {
            "variant":       rec.tipo,
            "set":           set_name_es or "?",
            "slot":          disc_parsed.slot,
            "rarity":        disc_parsed.rareza if disc_parsed.rareza in ("S", "A", "B") else "S",
            "main":          disc_parsed.main_stat_canon or disc_parsed.main_stat_raw or "?",
            "main_value":    main_value,
            "subs":          subs_summary,
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
        if not name or self._disc_set_repo is None:
            return None
        try:
            for s in self._disc_set_repo.get_all():
                if s.nombre.lower().strip() == name.lower().strip():
                    return s.id
        except Exception:
            pass
        return None

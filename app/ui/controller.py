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
    agent_stats_detected = Signal(dict)      # stats de agente desde S18
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
        self._disc_syncer = None

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
            on_agent_stats=self._on_agent_stats_from_monitor,
            on_diagnostic=self._on_diagnostic_from_monitor,
            on_agent_detail=self._on_agent_detail_from_monitor,
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
        self._con = get_connection(self._db_path)
        self._agent_repo = AgentRepo(self._con)
        self._archetype_repo = ArchetypeRepo(self._con)
        self._disc_set_repo = DiscSetRepo(self._con)
        self._scoring_ctx = ScoringContext()

        # Persistencia S17 (disco equipado): escribe disco + asignación (sin
        # scoring). Usa la MISMA DB resuelta que las lecturas (en el .exe vive en
        # %LOCALAPPDATA%, no la relativa al source). Backup de sesión RNF-01 una
        # sola vez antes de habilitar writes.
        from app.core.sync_equip import DiscSyncer
        resolved_db = self._db_path or get_db_path()
        self._backup_db_session(resolved_db)
        self._disc_syncer = DiscSyncer(db_path=Path(resolved_db))

    # ---- Callbacks desde el Monitor (thread daemon) ----------------------------

    def _on_state_from_monitor(self, state):
        # Signals son thread-safe en Qt (cross-thread auto-marshalled si hay event loop)
        from app.core.detector import describe_state, CAPTURE_DISC_STATES, UPGRADE_STATES, NON_CAPTURE_STATES
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
                f"PJ sin identificar (entrá a Atributos base para registrarlo)"
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

        payload = asdict(stats)
        payload["state_code"] = state.code
        self.agent_stats_detected.emit(payload)

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
            if state.code == "S17":
                result = None
                if self._disc_syncer is not None:
                    result = self._disc_syncer.persist_s17_disc(disc_parsed)
                self._log_s17_extraction(disc_parsed, result)
                return
            payload = self._build_payload(disc_parsed, state)
            self.disc_detected.emit(payload)
        except Exception as exc:
            log.exception("Error procesando disco capturado")
            self.error_occurred.emit(f"Procesando disco: {exc}")

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

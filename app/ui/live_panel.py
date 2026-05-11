"""
Panel "Live" — tab principal del capturador (RF-04 / RF-11 §UI capturador).

Muestra:
- Estado del monitor (ON/OFF/PAUSADO) + botón toggle.
- Indicador "estado detectado" actual (S1-S12) con confianza.
- Log scrollable de eventos (captura, error, cambio de estado).
- Card del último disco detectado con score + recomendación.

Comunicación con el MonitorController vía signals Qt (thread-safe).
"""
from __future__ import annotations

import datetime

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.ui import tokens as T


def _load_scaled_pixmap(path_str: str | None, size: int) -> QPixmap | None:
    """Carga un PNG/WebP y lo escala manteniendo aspect ratio. None si no existe."""
    if not path_str or not Path(path_str).exists():
        return None
    pm = QPixmap(path_str)
    if pm.isNull():
        return None
    return pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ---------------------------------------------------------------------------
# Mini-card del último disco capturado
# ---------------------------------------------------------------------------

class LastDiscCard(QFrame):
    """Card que muestra metadata del último disco capturado y su recomendación."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("last_disc_card")
        self.setMinimumHeight(120)
        self.setStyleSheet(f"""
            QFrame#last_disc_card {{
                background: {T.BG_PANEL};
                border: 1px solid {T.BORDER_SUBTLE};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        self._build()

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        # ---- Columna izquierda: set logo (48×48) ----
        self._set_logo_lbl = QLabel()
        self._set_logo_lbl.setFixedSize(48, 48)
        self._set_logo_lbl.setStyleSheet(
            f"background: {T.BG_DEEP}; border: 1px solid {T.BORDER_SUBTLE}; border-radius: 8px;"
        )
        self._set_logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._set_logo_lbl, 0, Qt.AlignmentFlag.AlignTop)

        # ---- Columna central: metadata ----
        center = QVBoxLayout()
        center.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        self._title_lbl = QLabel("Último disco capturado")
        self._title_lbl.setFont(T.font_caps(9, bold=True))
        self._title_lbl.setStyleSheet(f"color: {T.TEXT_MUTED};")
        self._variant_lbl = QLabel("—")
        self._variant_lbl.setFont(T.font_caps(10, bold=True))
        self._variant_lbl.setStyleSheet(f"color: {T.YELLOW};")
        self._variant_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()
        hdr.addWidget(self._variant_lbl)
        center.addLayout(hdr)

        # Body: set + slot
        self._set_lbl = QLabel("— (esperando captura)")
        self._set_lbl.setFont(T.font_ui(14, bold=True))
        self._set_lbl.setStyleSheet(f"color: {T.TEXT_PRIMARY};")
        center.addWidget(self._set_lbl)

        self._main_lbl = QLabel("")
        self._main_lbl.setFont(T.font_mono(10))
        self._main_lbl.setStyleSheet(f"color: {T.TEXT_SECONDARY};")
        center.addWidget(self._main_lbl)

        # Footer: avatar + target agent + score
        ft = QHBoxLayout()
        ft.setSpacing(8)
        self._avatar_lbl = QLabel()
        self._avatar_lbl.setFixedSize(28, 28)
        self._avatar_lbl.setStyleSheet(
            f"border: 1px solid {T.BORDER_SUBTLE}; border-radius: 14px; background: {T.BG_DEEP};"
        )
        self._avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._target_lbl = QLabel("")
        self._target_lbl.setFont(T.font_ui(11))
        self._target_lbl.setStyleSheet(f"color: {T.TEXT_SECONDARY};")
        self._score_lbl = QLabel("")
        self._score_lbl.setFont(T.font_display(18, bold=True))
        self._score_lbl.setStyleSheet(f"color: {T.YELLOW};")
        self._score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        ft.addWidget(self._avatar_lbl)
        ft.addWidget(self._target_lbl)
        ft.addStretch()
        ft.addWidget(self._score_lbl)
        center.addLayout(ft)

        outer.addLayout(center, 1)

    @Slot(dict)
    def update_from(self, payload: dict):
        variant_info = T.variant(payload.get("variant", "reserva"))
        self._variant_lbl.setText(variant_info["label"])
        self._variant_lbl.setStyleSheet(f"color: {variant_info['color']};")
        self._score_lbl.setStyleSheet(f"color: {variant_info['color']};")

        set_text = payload.get("set", "?")
        slot = payload.get("slot", 0)
        rarity = payload.get("rarity", "?")
        self._set_lbl.setText(f"{set_text}  ·  Slot {slot}  ·  [{rarity}]")

        main = payload.get("main", "?")
        main_value = payload.get("main_value", "")
        self._main_lbl.setText(f"{main}  {main_value}")

        target = payload.get("target", "—")
        mind = payload.get("mind", 0)
        if target and target != "—":
            self._target_lbl.setText(f"→ {target}  M{mind}")
        else:
            self._target_lbl.setText("")

        score = payload.get("score", 0.0)
        self._score_lbl.setText(f"{score:.1f}")

        # Set logo
        logo_pm = _load_scaled_pixmap(payload.get("set_logo"), 44)
        if logo_pm:
            self._set_logo_lbl.setPixmap(logo_pm)
            self._set_logo_lbl.setText("")
        else:
            self._set_logo_lbl.clear()
            self._set_logo_lbl.setText("?")
            self._set_logo_lbl.setStyleSheet(
                f"background: {T.BG_DEEP}; border: 1px solid {T.BORDER_SUBTLE};"
                f" border-radius: 8px; color: {T.TEXT_MUTED}; font-size: 18px;"
            )

        # Avatar del target (28×28 redondo)
        avatar_pm = _load_scaled_pixmap(payload.get("target_avatar"), 28)
        if avatar_pm:
            # Recortar a círculo aplicando mask
            from PySide6.QtGui import QBitmap, QPainter, QBrush, QColor
            from PySide6.QtCore import QRect
            rounded = QPixmap(28, 28)
            rounded.fill(QColor(0, 0, 0, 0))
            p = QPainter(rounded)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QBrush(avatar_pm))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, 28, 28)
            p.end()
            self._avatar_lbl.setPixmap(rounded)
        else:
            self._avatar_lbl.clear()


# ---------------------------------------------------------------------------
# LivePanel principal
# ---------------------------------------------------------------------------

class LivePanel(QWidget):
    """Tab "Live" del panel principal. Controla y muestra estado del monitor."""

    # Signals → MonitorController
    start_monitor_requested = Signal()
    stop_monitor_requested = Signal()
    pause_toggle_requested = Signal()
    test_capture_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ---- Header: título + estado actual ----
        header = QHBoxLayout()
        title = QLabel("Captura en Vivo")
        title.setFont(T.font_display(20, bold=True))
        title.setStyleSheet(f"color: {T.YELLOW};")
        header.addWidget(title)
        header.addStretch()

        self._state_pill = QLabel("S? · conf —")
        self._state_pill.setFont(T.font_mono(10))
        self._state_pill.setStyleSheet(
            f"color: {T.TEXT_MUTED}; background: {T.BG_PANEL_HI}; "
            f"border: 1px solid {T.BORDER_SUBTLE}; padding: 4px 10px; border-radius: 6px;"
        )
        header.addWidget(self._state_pill)

        self._monitor_dot = QLabel("● OFF")
        self._monitor_dot.setFont(T.font_caps(10, bold=True))
        self._monitor_dot.setStyleSheet(f"color: {T.TEXT_DIM};")
        header.addWidget(self._monitor_dot)

        layout.addLayout(header)

        # ---- Controles ----
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._toggle_btn = QPushButton("Iniciar captura")
        self._toggle_btn.setMinimumHeight(34)
        self._toggle_btn.setStyleSheet(self._btn_style(T.POSITIVE))
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        controls.addWidget(self._toggle_btn)

        self._pause_btn = QPushButton("Pausa (F10)")
        self._pause_btn.setMinimumHeight(34)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setStyleSheet(self._btn_style(T.YELLOW))
        self._pause_btn.clicked.connect(self.pause_toggle_requested.emit)
        controls.addWidget(self._pause_btn)

        self._test_btn = QPushButton("Probar captura (F8)")
        self._test_btn.setMinimumHeight(34)
        self._test_btn.setStyleSheet(self._btn_style(T.INFO))
        self._test_btn.clicked.connect(self.test_capture_requested.emit)
        controls.addWidget(self._test_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # ---- Card último disco ----
        self.last_disc_card = LastDiscCard()
        layout.addWidget(self.last_disc_card)

        # ---- Log ----
        log_label = QLabel("Log de eventos")
        log_label.setFont(T.font_caps(9, bold=True))
        log_label.setStyleSheet(f"color: {T.TEXT_MUTED};")
        layout.addWidget(log_label)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(T.font_mono(9))
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: {T.BG_DEEP};
                border: 1px solid {T.BORDER_SUBTLE};
                color: {T.TEXT_SECONDARY};
                padding: 8px;
                border-radius: 6px;
            }}
        """)
        self._log.setMinimumHeight(160)
        layout.addWidget(self._log, 1)

        self._running = False
        self._paused = False
        self.append_log("[init] Monitor inactivo. Presioná 'Iniciar captura' o F9 para abrir el panel.")

    def _btn_style(self, accent: str) -> str:
        return f"""
            QPushButton {{
                background: {T.BG_PANEL};
                color: {accent};
                border: 1px solid {accent};
                padding: 6px 14px;
                border-radius: 6px;
                font-weight: bold;
                letter-spacing: 0.06em;
            }}
            QPushButton:hover {{
                background: {accent};
                color: {T.BG_DEEP};
            }}
            QPushButton:disabled {{
                color: {T.TEXT_DIM};
                border-color: {T.BORDER_SUBTLE};
                background: {T.BG_PANEL};
            }}
        """

    def _on_toggle_clicked(self):
        if self._running:
            self.stop_monitor_requested.emit()
        else:
            self.start_monitor_requested.emit()

    # ---- Slots invocados por MonitorController ---------------------------------

    @Slot()
    def on_monitor_started(self):
        self._running = True
        self._paused = False
        self._toggle_btn.setText("Detener captura")
        self._toggle_btn.setStyleSheet(self._btn_style(T.WARNING))
        self._pause_btn.setEnabled(True)
        self._monitor_dot.setText("● ON")
        self._monitor_dot.setStyleSheet(f"color: {T.POSITIVE};")
        self.append_log("[monitor] Capturando. F8 fuerza scan · F10 pausa.")

    @Slot()
    def on_monitor_stopped(self):
        self._running = False
        self._paused = False
        self._toggle_btn.setText("Iniciar captura")
        self._toggle_btn.setStyleSheet(self._btn_style(T.POSITIVE))
        self._pause_btn.setEnabled(False)
        self._monitor_dot.setText("● OFF")
        self._monitor_dot.setStyleSheet(f"color: {T.TEXT_DIM};")
        self.append_log("[monitor] Detenido.")

    @Slot(bool)
    def on_pause_changed(self, paused: bool):
        self._paused = paused
        if paused:
            self._monitor_dot.setText("● PAUSADO")
            self._monitor_dot.setStyleSheet(f"color: {T.YELLOW};")
            self.append_log("[monitor] Pausado.")
        else:
            self._monitor_dot.setText("● ON")
            self._monitor_dot.setStyleSheet(f"color: {T.POSITIVE};")
            self.append_log("[monitor] Reanudado.")

    @Slot(str, float)
    def on_state_changed(self, code: str, confidence: float):
        self._state_pill.setText(f"{code} · conf {confidence:.2f}")
        # Colorear según estado
        if code in ("S3", "S6", "S7"):
            color = T.POSITIVE  # estados de captura activa
        elif code == "S10":
            color = T.INFO
        elif code in ("S11", "S12"):
            color = T.TEXT_MUTED
        else:
            color = T.TEXT_SECONDARY
        self._state_pill.setStyleSheet(
            f"color: {color}; background: {T.BG_PANEL_HI}; "
            f"border: 1px solid {T.BORDER_SUBTLE}; padding: 4px 10px; border-radius: 6px;"
        )

    @Slot(dict)
    def on_disc_detected(self, payload: dict):
        self.last_disc_card.update_from(payload)
        variant_info = T.variant(payload.get("variant", "reserva"))
        self.append_log(
            f"[disco] {payload.get('set', '?')} slot {payload.get('slot', 0)} "
            f"→ {variant_info['label']} {payload.get('score', 0):.1f} "
            f"(→ {payload.get('target', '—')})"
        )

    @Slot(str)
    def on_error(self, msg: str):
        self.append_log(f"[error] {msg}")

    def append_log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append(f"{ts}  {msg}")
        # Scroll al final
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

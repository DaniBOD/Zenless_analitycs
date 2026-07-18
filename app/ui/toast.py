"""
Toast flotante con la card de recomendación — RF-04 §10 / RF-11 UI.
Portado de Documentacion/Interfaz/mockups/Codigos-claude-desing/toasts.jsx con fidelidad alta:

- Frame chamfered (esquina sup-izq y inf-der recortadas).
- Border + glow del color del variant.
- Carbon-fiber pattern sutil de background.
- Header con chevron + label + ID + countdown ring.
- Body con disc thumb (set logo + rarity badge) + meta + target agent + score.
- Urgency bar animada en el footer (pulsing).
- Hover congela el countdown (idle → hover state).
- Auto-fade después de N segundos (default 4s).

Uso:
    toast = DiscToast()
    toast.show_recommendation(disc_data, variant="equipar")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer,
    Signal, Property,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QGraphicsDropShadowEffect, QWidget,
)

from app.ui import tokens as T


# ---------------------------------------------------------------------------
# Datos que el toast renderiza
# ---------------------------------------------------------------------------

@dataclass
class ToastData:
    """Bundle de datos que renderiza el toast (mapea a 1 recomendación)."""
    variant:       str = "reserva"     # equipar / mejorar / reserva / descartar
    disc_id:       int | None = None
    set_name:      str = "Set desconocido"
    slot:          int = 1
    rarity:        str = "S"            # S / A / B
    main_stat:     str = "?"
    main_value:    str = ""             # "30 %" / "550" listo para mostrar
    subs_summary:  str = ""             # "CR · CD · ATK% · ATK"
    target_agent:  str = "—"
    target_mind:   int = 0
    target_avatar: str | None = None    # path absoluto a imagen
    set_logo:      str | None = None
    score:         float = 0.0
    delta:         float | None = None  # mejora vs disco actual del slot (en pts)
    urgency:       float = 0.7          # 0-1
    threshold:     float = 0.75         # threshold equip o stock
    timeout_secs:  float = 4.0
    # Variante "reemplazado" (swap origen→destino). El DESTINO reusa target_agent/target_avatar.
    from_agent:    str = "—"            # PJ que DEJA el disco (atenuado)
    from_avatar:   str | None = None


# ---------------------------------------------------------------------------
# Constantes de geometría (mockup)
# ---------------------------------------------------------------------------

WIDTH         = 380
HEIGHT        = 140          # 116 -> 140 para que header (label) no se solape con thumb
HEADER_GAP    = 28           # franja outer chrome arriba (texto pequeño "ALWAYS-ON-TOP · BR")
TOTAL_HEIGHT  = HEIGHT + HEADER_GAP
CHAMFER       = 12           # px de recorte en esquinas chamfered
URGENCY_BAR_H = 4
PADDING_X     = 14


# ---------------------------------------------------------------------------
# Disc thumbnail widget (cuadrado con set logo + rarity badge)
# ---------------------------------------------------------------------------

class DiscThumb(QWidget):
    def __init__(self, accent: str = T.YELLOW, tier: str = "S",
                 set_logo_path: str | None = None, size: int = 56,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._accent = accent
        self._tier = tier
        self._size = size
        self._pixmap: QPixmap | None = None
        if set_logo_path and Path(set_logo_path).exists():
            self._pixmap = QPixmap(set_logo_path)
        self.setFixedSize(size, size)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)

        # Background radial (acento muy tenue + negro)
        grad = QRadialGradient(rect.center(), self._size / 2.0)
        grad.setColorAt(0, T.color(self._accent, 0.10))
        grad.setColorAt(1, T.color("#050505", 1.0))
        p.setBrush(QBrush(grad))
        pen = QPen(T.color(self._accent, 0.40))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRoundedRect(rect, 12, 12)

        # Set logo (centrado, escalado al 78%)
        if self._pixmap and not self._pixmap.isNull():
            target_size = int(self._size * 0.78)
            scaled = self._pixmap.scaled(
                target_size, target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self._size - scaled.width()) // 2
            y = (self._size - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            # Fallback: hexágono simple del color de tono
            p.setBrush(T.color(self._accent, 0.65))
            p.setPen(Qt.PenStyle.NoPen)
            cx, cy = self._size // 2, self._size // 2
            r = int(self._size * 0.28)
            poly = QPolygonF([
                QPoint(cx, cy - r), QPoint(cx + r, cy - r // 2),
                QPoint(cx + r, cy + r // 2), QPoint(cx, cy + r),
                QPoint(cx - r, cy + r // 2), QPoint(cx - r, cy - r // 2),
            ])
            p.drawPolygon(poly)

        # Rarity badge (esquina inf-der)
        badge_color = {"S": T.YELLOW, "A": T.PURPLE, "B": T.INFO}.get(self._tier, T.YELLOW)
        badge_size = 14
        bx = self._size - badge_size - 3
        by = self._size - badge_size - 3
        p.setBrush(T.color(badge_color))
        p.setPen(QPen(T.color("#000000"), 1))
        p.drawEllipse(bx, by, badge_size, badge_size)
        p.setPen(QPen(T.color("#000000"), 1))
        p.setFont(T.font_caps(7, bold=True))
        p.drawText(QRect(bx, by, badge_size, badge_size),
                   int(Qt.AlignmentFlag.AlignCenter), self._tier)


# ---------------------------------------------------------------------------
# Toast principal
# ---------------------------------------------------------------------------

class DiscToast(QWidget):
    """
    Toast frameless always-on-top bottom-right.
    Llamar `show_recommendation(data)` para mostrar; se autoesconde tras data.timeout_secs.
    """

    clicked = Signal()  # click en cualquier parte abre el panel principal

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(WIDTH + 40, TOTAL_HEIGHT + 40)  # +padding para el glow

        self._data = ToastData()
        self._secs_remaining = 4.0
        self._paused = False
        self._urgency_phase = 0.0    # 0-1 para animación pulsing

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)  # 10 fps
        self._tick_timer.timeout.connect(self._on_tick)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._thumb: DiscThumb | None = None

    # ---- Public API ----------------------------------------------------------

    def show_recommendation(self, data: ToastData) -> None:
        """Muestra el toast con los datos provistos."""
        self._data = data
        self._secs_remaining = data.timeout_secs
        self._paused = False
        self._urgency_phase = 0.0

        # Posicionar bottom-right de la pantalla activa
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 24
        x = screen.right() - self.width() + 20  # compensar el padding del glow
        y = screen.bottom() - self.height() + 20 - margin
        self.move(x, y)

        # Recrear thumb por si el set cambió
        if self._thumb:
            self._thumb.deleteLater()
        accent = T.variant(data.variant)["color"]
        self._thumb = DiscThumb(
            accent=accent,
            tier=data.rarity,
            set_logo_path=data.set_logo,
            size=56,
            parent=self,
        )
        # Mover el thumb por debajo del label (label va y=10-30 desde oy=HEADER_GAP+20).
        # El thumb ocupa 56x56; con margen de seguridad, empieza en y = HEADER_GAP + 52.
        self._thumb.move(PADDING_X + 20, HEADER_GAP + 52)

        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim.stop()
        # Desconectar el `finished → hide` que dejó un `hide_with_fade` previo: si no, al
        # terminar ESTE fade-in la señal dispara hide() y el toast (2º disco en adelante)
        # aparece y desaparece al instante. Bug QA 2026-07-08 (solo se veía el 1er toast).
        try:
            self._fade_anim.finished.disconnect(self.hide)
        except (TypeError, RuntimeError):
            pass
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(0.96)
        self._fade_anim.start()
        self._tick_timer.start()
        self.update()

    def show_replacement(self, data: ToastData) -> None:
        """Toast de swap confirmado (variante 'reemplazado'): origen → disco → destino, sin score
        ni countdown. Reusa el marco/glow; el body lo pinta `_paint_body_replacement`. El thumb va
        CENTRADO (no a la izquierda como en las recomendaciones)."""
        data.variant = "reemplazado"
        self._data = data
        self._secs_remaining = data.timeout_secs or 3.0
        self._paused = False
        self._urgency_phase = 0.0

        screen = QApplication.primaryScreen().availableGeometry()
        margin = 24
        x = screen.right() - self.width() + 20
        y = screen.bottom() - self.height() + 20 - margin
        self.move(x, y)

        if self._thumb:
            self._thumb.deleteLater()
        accent = T.variant("reemplazado")["color"]
        self._thumb = DiscThumb(
            accent=accent, tier=data.rarity, set_logo_path=data.set_logo, size=48, parent=self,
        )
        # Centrado horizontalmente (ox=20), debajo del header.
        self._thumb.move(20 + WIDTH // 2 - 24, HEADER_GAP + 50)

        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect(self.hide)
        except (TypeError, RuntimeError):
            pass
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(0.96)
        self._fade_anim.start()
        self._tick_timer.start()
        self.update()

    def hide_with_fade(self):
        self._tick_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide, Qt.ConnectionType.UniqueConnection)
        self._fade_anim.start()

    # ---- Eventos -------------------------------------------------------------

    def enterEvent(self, _ev):
        self._paused = True
        self.setWindowOpacity(1.0)
        self.update()

    def leaveEvent(self, _ev):
        self._paused = False
        self.setWindowOpacity(0.96)
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self.hide_with_fade()

    def _on_tick(self):
        if not self._paused:
            self._secs_remaining = max(0.0, self._secs_remaining - 0.1)
            if self._secs_remaining <= 0:
                self._tick_timer.stop()
                self.hide_with_fade()
                return
        self._urgency_phase = (self._urgency_phase + 0.06) % 1.0
        self.update()

    # ---- Pintado -------------------------------------------------------------

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        v = T.variant(self._data.variant)
        accent = QColor(v["color"])

        # Origen del toast dentro del widget (offset por el padding del glow)
        ox, oy = 20, HEADER_GAP + 20

        # Outer chrome top: "EQUIPAR · 02:13"  ALWAYS-ON-TOP · BR
        p.setPen(T.color(T.TEXT_DIM))
        p.setFont(T.font_caps(7))
        p.drawText(ox + 4, oy - 8, "ALWAYS-ON-TOP · BR")

        # Background con chamfered corners (top-left + bottom-right)
        path = self._chamfered_path(QRect(ox, oy, WIDTH, HEIGHT), CHAMFER)

        # Glow (pintado fuera del path con opacidad alta del color del variant)
        # Lo simulamos pintando varios paths offset con baja opacidad
        for offset, alpha in [(8, 0.10), (5, 0.18), (3, 0.28)]:
            glow_path = self._chamfered_path(
                QRect(ox - offset, oy - offset, WIDTH + 2 * offset, HEIGHT + 2 * offset),
                CHAMFER + offset,
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.color(v["color"], alpha))
            p.drawPath(glow_path)

        # Background sólido (semi-transparente con leve gradient)
        bg = QLinearGradient(ox, oy, ox, oy + HEIGHT)
        bg.setColorAt(0, T.color("#0e0e0e", 0.97))
        bg.setColorAt(1, T.color("#070707", 0.97))
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

        # Border accent
        border_pen = QPen(accent)
        border_pen.setWidthF(1.5)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Glass top highlight (50% superior con gradient blanco translúcido)
        glass = QLinearGradient(ox, oy, ox, oy + HEIGHT // 2)
        glass.setColorAt(0, T.color("#ffffff", 0.06))
        glass.setColorAt(0.4, T.color("#ffffff", 0.018))
        glass.setColorAt(1, T.color("#ffffff", 0))
        glass_path = self._chamfered_path(QRect(ox, oy, WIDTH, HEIGHT // 2), CHAMFER)
        p.setBrush(QBrush(glass))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(glass_path)

        # ---- Contenido ----
        self._paint_header(p, ox, oy, accent, v)
        if self._data.variant == "reemplazado":
            self._paint_body_replacement(p, ox, oy, accent, v)
            self._paint_footer_static(p, ox, oy, accent, "EQUIPAMIENTO SINCRONIZADO", "inventory_discs ✓")
        else:
            self._paint_body(p, ox, oy, accent, v)
            self._paint_footer(p, ox, oy, accent, v)

    def _chamfered_path(self, rect: QRect, chamfer: int) -> QPainterPath:
        """Path con chamfer en top-left y bottom-right."""
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        c = chamfer
        path = QPainterPath()
        path.moveTo(x + c, y)
        path.lineTo(x + w, y)
        path.lineTo(x + w, y + h - c)
        path.lineTo(x + w - c, y + h)
        path.lineTo(x, y + h)
        path.lineTo(x, y + c)
        path.closeSubpath()
        return path

    def _paint_header(self, p: QPainter, ox: int, oy: int, accent: QColor, v: dict):
        """Label texto plano + #ID + countdown.

        Nota: el DiscThumb es un QWidget child que Qt renderiza después del paint
        del parent. Posicionarlo en (PADDING_X+20, HEADER_GAP+38) hacía que tapara
        la primera mitad del label. Solución: mover el thumb más abajo en
        show_recommendation() para que header y thumb no se solapen en Y.
        """
        label_x = ox + PADDING_X
        label_y = oy + 10
        label_h = 20

        # Fuente segura sin custom letterSpacing (evita negative left-bearings raros)
        label_font = QFont("Segoe UI", 10)
        label_font.setBold(True)
        p.setFont(label_font)
        label = v["label"].upper()
        text_w = p.fontMetrics().horizontalAdvance(label)

        # Underline bar debajo del label (decorativo con el color del variant)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRect(label_x, label_y + label_h - 2, text_w + 4, 2))

        # Label en color del variant
        p.setPen(accent)
        p.drawText(
            QRect(label_x, label_y, text_w + 12, label_h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label,
        )
        badge_y = label_y

        # Separador
        sep_x = label_x + text_w + 14
        p.setPen(QPen(T.color(T.BORDER_MID), 1))
        p.drawLine(sep_x, label_y + 3, sep_x, label_y + label_h - 3)

        # ID
        p.setPen(T.color(T.TEXT_MUTED))
        p.setFont(T.font_ui(8))
        id_str = f"#{self._data.disc_id:05d}" if self._data.disc_id else "#-----"
        id_rect = QRect(sep_x + 6, label_y, 60, label_h)
        p.drawText(id_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), id_str)

        # Variante confirmación (reemplazado): micro-badge "✓ SINCRONIZADO" estático, sin countdown.
        if self._data.variant == "reemplazado":
            badge_txt = "✓ SINCRONIZADO"
            p.setFont(T.font_caps(7))
            bw = p.fontMetrics().horizontalAdvance(badge_txt) + 14
            bx = ox + WIDTH - PADDING_X - bw
            p.setBrush(T.color(T.POSITIVE, 0.08))
            p.setPen(QPen(T.color(T.POSITIVE, 0.4), 1))
            p.drawRoundedRect(bx, label_y + 1, bw, label_h - 2, 3, 3)
            p.setPen(T.color(T.POSITIVE))
            p.drawText(QRect(bx, label_y, bw, label_h),
                       int(Qt.AlignmentFlag.AlignCenter), badge_txt)
            return

        # Countdown (derecha)
        cd_w = 64
        cd_x = ox + WIDTH - PADDING_X - cd_w
        cd_y = badge_y + 4
        # Punto pulsante
        if self._paused:
            dot_color = T.color(T.YELLOW)
        else:
            blink = abs(0.5 - (self._urgency_phase % 1.0)) * 2  # 0-1
            dot_color = T.color(v["color"], 0.4 + 0.6 * blink)
        p.setBrush(dot_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cd_x, cd_y + 4, 6, 6)

        # Texto countdown
        p.setFont(T.font_mono(8))
        p.setPen(T.color(T.YELLOW if self._paused else T.TEXT_SECONDARY))
        text = "PAUSE" if self._paused else f"{self._secs_remaining:.1f}s"
        p.drawText(cd_x + 12, cd_y + 12, text)

    def _paint_body(self, p: QPainter, ox: int, oy: int, accent: QColor, v: dict):
        """Disc thumb + meta + target + score."""
        # Disc thumb se pinta en el subwidget (DiscThumb)
        # Aquí pintamos solo el lado derecho

        meta_x = ox + PADDING_X + 56 + 12  # right of thumb
        meta_y = oy + 52                    # alineado con top del thumb (HEADER_GAP+52 abs)

        # Set name + slot
        p.setFont(T.font_ui(11, bold=True))
        p.setPen(T.color(T.TEXT_PRIMARY))
        set_text = self._data.set_name
        # Trim si es muy largo
        fm = p.fontMetrics()
        max_w = WIDTH - (PADDING_X + 56 + 12) - PADDING_X - 4
        elided = fm.elidedText(set_text, Qt.TextElideMode.ElideRight, max_w - 60)
        p.drawText(meta_x, meta_y, elided)

        # Slot label
        p.setFont(T.font_ui(9))
        p.setPen(T.color(T.TEXT_MUTED))
        slot_x = meta_x + fm.horizontalAdvance(elided) + 6
        p.drawText(slot_x, meta_y, f"· Slot {self._data.slot}")

        # Mainstat
        p.setFont(T.font_mono(9))
        p.setPen(T.color(T.TEXT_SECONDARY))
        main_y = meta_y + 14
        p.drawText(meta_x, main_y, self._data.main_stat)
        ms_w = p.fontMetrics().horizontalAdvance(self._data.main_stat)
        p.setPen(T.color(T.YELLOW))
        p.drawText(meta_x + ms_w + 6, main_y, self._data.main_value)

        # Subs summary (compacto)
        if self._data.subs_summary:
            mv_w = p.fontMetrics().horizontalAdvance(self._data.main_value)
            p.setPen(T.color(T.TEXT_MUTED))
            p.drawText(meta_x + ms_w + mv_w + 12, main_y, "· " + self._data.subs_summary)

        # Línea inferior: target agent + score
        bottom_y = oy + HEIGHT - 30
        # → Target
        p.setFont(T.font_caps(7))
        p.setPen(T.color(T.TEXT_MUTED))
        p.drawText(meta_x, bottom_y, "→")

        target_x = meta_x + 14

        # Avatar (si existe)
        if self._data.target_avatar and Path(self._data.target_avatar).exists():
            avatar = QPixmap(self._data.target_avatar).scaled(
                18, 18,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # Clip circular
            clip_path = QPainterPath()
            clip_path.addEllipse(target_x, bottom_y - 14, 18, 18)
            p.setClipPath(clip_path)
            p.drawPixmap(target_x, bottom_y - 14, avatar)
            p.setClipping(False)
            # Ring accent
            p.setPen(QPen(accent, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(target_x, bottom_y - 14, 18, 18)
            target_x += 22

        p.setFont(T.font_ui(11, bold=True))
        p.setPen(T.color(T.TEXT_PRIMARY))
        p.drawText(target_x, bottom_y, self._data.target_agent)
        ta_w = p.fontMetrics().horizontalAdvance(self._data.target_agent)
        p.setFont(T.font_mono(9))
        p.setPen(T.color(T.TEXT_SECONDARY))
        p.drawText(target_x + ta_w + 4, bottom_y, f"M{self._data.target_mind}")

        # Score (derecha)
        score_label_x = ox + WIDTH - PADDING_X - 80
        p.setFont(T.font_caps(7))
        p.setPen(T.color(T.TEXT_MUTED))
        p.drawText(score_label_x, bottom_y - 8, "SCORE")

        p.setFont(T.font_display(18, bold=True))
        p.setPen(accent)
        score_text = f"{self._data.score:.1f}"
        p.drawText(score_label_x, bottom_y + 4, score_text)

        # Delta
        if self._data.delta is not None:
            p.setFont(T.font_mono(8))
            p.setPen(T.color(T.POSITIVE if self._data.delta >= 0 else T.WARNING))
            delta_str = f"{'▲' if self._data.delta >= 0 else '▼'}{abs(self._data.delta):.1f}"
            p.drawText(score_label_x + 32, bottom_y + 4, delta_str)

    def _paint_footer(self, p: QPainter, ox: int, oy: int, accent: QColor, v: dict):
        """Urgency bar + label."""
        bar_y = oy + HEIGHT - URGENCY_BAR_H - 18
        bar_w = WIDTH - 2 * PADDING_X
        bar_x = ox + PADDING_X

        # Track
        p.setBrush(T.color("#ffffff", 0.06))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bar_x, bar_y, bar_w, URGENCY_BAR_H)

        # Fill (con pulse si activo)
        urgency = max(0.0, min(1.0, self._data.urgency))
        if not self._paused:
            pulse = 0.7 + 0.3 * abs(0.5 - self._urgency_phase) * 2
        else:
            pulse = 1.0
        fill_color = QColor(accent)
        fill_color.setAlphaF(pulse)
        p.setBrush(fill_color)
        p.drawRect(bar_x, bar_y, int(bar_w * urgency), URGENCY_BAR_H)

        # Label bottom: URGENCIA  ·  THR 0.75
        p.setFont(T.font_caps(7))
        p.setPen(T.color(T.TEXT_MUTED))
        urg_label = "URGENCIA ALTA" if urgency >= 0.7 else ("URGENCIA MEDIA" if urgency >= 0.4 else "URGENCIA BAJA")
        p.drawText(bar_x, bar_y + URGENCY_BAR_H + 13, urg_label)

        thr_str = f"thr {self._data.threshold:.2f}"
        thr_w = p.fontMetrics().horizontalAdvance(thr_str)
        p.setFont(T.font_mono(8))
        p.drawText(bar_x + bar_w - thr_w, bar_y + URGENCY_BAR_H + 13, thr_str)

    def _paint_avatar(self, p: QPainter, path_str: str | None, x: int, y: int, d: int,
                      ring: QColor | None, dim: bool = False):
        """Avatar circular en (x,y) diámetro d. `ring`=color del aro (None sin aro). `dim`=atenuado
        (el PJ que DEJA el disco). Si no hay imagen, dibuja un placeholder con el aro."""
        drew = False
        if path_str and Path(path_str).exists():
            av = QPixmap(path_str)
            if not av.isNull():
                av = av.scaled(d, d, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                clip = QPainterPath(); clip.addEllipse(x, y, d, d)
                p.setClipPath(clip)
                if dim:
                    p.setOpacity(0.55)
                p.drawPixmap(x, y, av)
                p.setOpacity(1.0)
                p.setClipping(False)
                drew = True
        if not drew:
            p.setBrush(T.color("#1a1a1a")); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(x, y, d, d)
        if ring is not None:
            p.setPen(QPen(ring, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(x, y, d, d)

    def _paint_body_replacement(self, p: QPainter, ox: int, oy: int, accent: QColor, v: dict):
        """Body del toast REEMPLAZADO: PJ origen (DEJA, atenuado) → disco (thumb central + set/slot)
        → PJ destino (EQUIPA, resaltado con aro violeta). Sin score ni substats (anti-sobrecarga)."""
        d = 38
        col_top = oy + 58
        name_y = col_top + d + 14
        # --- Origen (izquierda, atenuado) ---
        ox_l = ox + PADDING_X + 6
        p.setFont(T.font_caps(7)); p.setPen(T.color(T.TEXT_MUTED))
        p.drawText(QRect(ox_l - 4, col_top - 12, 56, 10), int(Qt.AlignmentFlag.AlignCenter), "DEJA")
        self._paint_avatar(p, self._data.from_avatar, ox_l + 8, col_top, d,
                           T.color(T.BORDER_MID), dim=True)
        p.setFont(T.font_ui(9)); p.setPen(T.color(T.TEXT_SECONDARY))
        p.drawText(QRect(ox_l - 6, name_y - 10, 60, 14),
                   int(Qt.AlignmentFlag.AlignCenter),
                   p.fontMetrics().elidedText(self._data.from_agent, Qt.TextElideMode.ElideRight, 58))
        # --- Destino (derecha, resaltado) ---
        ox_r = ox + WIDTH - PADDING_X - 56
        p.setFont(T.font_caps(7)); p.setPen(accent)
        p.drawText(QRect(ox_r - 4, col_top - 12, 56, 10), int(Qt.AlignmentFlag.AlignCenter), "EQUIPA")
        self._paint_avatar(p, self._data.target_avatar, ox_r + 8, col_top, d, accent)
        p.setFont(T.font_ui(9, bold=True)); p.setPen(T.color(T.TEXT_PRIMARY))
        p.drawText(QRect(ox_r - 6, name_y - 10, 60, 14),
                   int(Qt.AlignmentFlag.AlignCenter),
                   p.fontMetrics().elidedText(self._data.target_agent, Qt.TextElideMode.ElideRight, 58))
        # --- Flechas violeta origen→centro→destino ---
        cy = col_top + d // 2
        p.setFont(T.font_ui(13, bold=True)); p.setPen(accent)
        p.drawText(QRect(ox_l + 8 + d, cy - 8, (ox + WIDTH // 2 - 24) - (ox_l + 8 + d), 16),
                   int(Qt.AlignmentFlag.AlignCenter), "→")
        p.drawText(QRect(ox + WIDTH // 2 + 24, cy - 8, (ox_r + 8) - (ox + WIDTH // 2 + 24), 16),
                   int(Qt.AlignmentFlag.AlignCenter), "→")
        # --- Set + slot debajo del thumb central ---
        p.setFont(T.font_ui(9, bold=True)); p.setPen(T.color(T.TEXT_PRIMARY))
        set_txt = p.fontMetrics().elidedText(self._data.set_name, Qt.TextElideMode.ElideRight, 118)
        p.drawText(QRect(ox + WIDTH // 2 - 62, name_y - 12, 124, 12),
                   int(Qt.AlignmentFlag.AlignCenter), set_txt)
        p.setFont(T.font_ui(8)); p.setPen(T.color(T.TEXT_MUTED))
        p.drawText(QRect(ox + WIDTH // 2 - 62, name_y + 1, 124, 11),
                   int(Qt.AlignmentFlag.AlignCenter), f"Slot {self._data.slot}")

    def _paint_footer_static(self, p: QPainter, ox: int, oy: int, accent: QColor,
                             left_txt: str, right_txt: str):
        """Footer de confirmación: barra fina ESTÁTICA (sin pulso) + línea de estado."""
        bar_y = oy + HEIGHT - URGENCY_BAR_H - 18
        bar_w = WIDTH - 2 * PADDING_X
        bar_x = ox + PADDING_X
        p.setBrush(accent); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bar_x, bar_y, bar_w, URGENCY_BAR_H)
        p.setFont(T.font_caps(7)); p.setPen(T.color(T.TEXT_MUTED))
        p.drawText(bar_x, bar_y + URGENCY_BAR_H + 13, left_txt)
        p.setFont(T.font_mono(8))
        rw = p.fontMetrics().horizontalAdvance(right_txt)
        p.drawText(bar_x + bar_w - rw, bar_y + URGENCY_BAR_H + 13, right_txt)


# ---------------------------------------------------------------------------
# Helper: convertir Recommendation + DiscParsed a ToastData
# ---------------------------------------------------------------------------

def build_toast_data(
    recommendation,        # app.core.recommender.Recommendation
    disc_parsed,           # app.core.parser_disc.DiscParsed
    disc_id: int | None = None,
    set_logo_path: str | None = None,
    target_avatar_path: str | None = None,
    target_mind: int = 0,
) -> ToastData:
    """Convierte el resultado del recommender a un ToastData listo para mostrar."""
    main = disc_parsed.main_stat_canon or disc_parsed.main_stat_raw or "?"
    main_value = ""
    if disc_parsed.main_valor is not None:
        main_value = f"{disc_parsed.main_valor:.1f}{'%' if disc_parsed.main_unidad == '%' else ''}"

    subs_short = " · ".join(
        (s.nombre_canon or s.nombre_raw)[:6]
        for s in disc_parsed.subs[:4] if s.nombre_canon or s.nombre_raw
    )

    return ToastData(
        variant=recommendation.tipo,
        disc_id=disc_id,
        set_name=disc_parsed.set_name_canon or disc_parsed.set_name_raw or "Set ?",
        slot=disc_parsed.slot,
        rarity=disc_parsed.rareza if disc_parsed.rareza in ("S", "A", "B") else "S",
        main_stat=main,
        main_value=main_value,
        subs_summary=subs_short,
        target_agent=recommendation.agente_nombre or "—",
        target_mind=target_mind,
        target_avatar=target_avatar_path,
        set_logo=set_logo_path,
        score=round(recommendation.score_norm * 100, 1),
        urgency=min(1.0, recommendation.score_norm * 1.1),
        threshold=0.75 if recommendation.tipo == "equipar" else 0.50,
    )

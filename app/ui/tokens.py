"""
Design tokens portados de Documentacion/Interfaz/mockups/Codigos-claude-desing/tokens.css.
Centraliza colores, fuentes y constantes visuales para que los widgets PySide6
queden alineados con los mockups.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

# ---------------------------------------------------------------------------
# Colores (mismos hex que tokens.css)
# ---------------------------------------------------------------------------

# Surfaces
BG_BASE         = "#0a0a0a"
BG_DEEP         = "#050505"
BG_PANEL        = "#141414"   # versión sólida (rgba 0.92 → 0.94 aplanada)
BG_PANEL_HI     = "#1c1c1c"
BG_OVERLAY      = "#000000"   # con alpha 75% en runtime

# Borders
BORDER_SUBTLE   = "#2a2a2a"
BORDER_MID      = "#3a3a3a"
BORDER_STRONG   = "#555555"

# Text
TEXT_PRIMARY    = "#f5f5f5"
TEXT_SECONDARY  = "#a8a8a8"
TEXT_MUTED      = "#6b6b6b"
TEXT_DIM        = "#4a4a4a"

# Signature ZZZ yellow
YELLOW          = "#FFCB05"
YELLOW_SOFT     = "#f0c020"
YELLOW_DEEP     = "#b89008"

# Action colors (variants)
POSITIVE        = "#7BC91F"
POSITIVE_DEEP   = "#5a9d10"
WARNING         = "#FF6B47"
INFO            = "#5BC0EB"

# AI / RF tags
PURPLE          = "#9D4EDD"
PINK            = "#FF4D8A"


# ---------------------------------------------------------------------------
# Variant config para toasts (alineado con toasts.jsx)
# ---------------------------------------------------------------------------
VARIANTS: dict[str, dict] = {
    "equipar":   {"label": "EQUIPAR",   "color": POSITIVE, "tone": "yellow", "icon": "check"},
    "mejorar":   {"label": "MEJORAR",   "color": INFO,     "tone": "info",   "icon": "up"},
    "reserva":   {"label": "RESERVA",   "color": YELLOW,   "tone": "yellow", "icon": "stack"},
    "descartar": {"label": "DESCARTAR", "color": WARNING,  "tone": "purple", "icon": "trash"},
    "lategame":  {"label": "RUN REGISTRADA", "color": YELLOW, "tone": "yellow", "icon": "feed"},
    # Confirmación pasiva de un swap de disco entre PJs detectado por OCR (S23→S17). Acento
    # violeta (color "libre" del sistema, no usado por otra variante). Sin score ni countdown:
    # es una notificación de que YA pasó y la DB se sincronizó (ver BRIEF_card_reemplazado.md).
    "reemplazado": {"label": "REEMPLAZADO", "color": PURPLE, "tone": "purple", "icon": "swap"},
}


# ---------------------------------------------------------------------------
# Tipografía
# ---------------------------------------------------------------------------

# Familias preferidas en orden de fallback. tokens.css usa Saira / Saira Condensed / JetBrains Mono.
# Si no están instaladas en el sistema, caemos a las del sistema.
_FONT_UI_PREFERRED       = ["Saira", "Bahnschrift", "Segoe UI", "Arial"]
_FONT_DISPLAY_PREFERRED  = ["Saira Condensed", "Bahnschrift Condensed", "Segoe UI Semibold", "Arial Black"]
_FONT_MONO_PREFERRED     = ["JetBrains Mono", "Cascadia Code", "Consolas", "Courier New"]


def _first_available(candidates: list[str]) -> str:
    families = {f.lower() for f in QFontDatabase.families()}
    for name in candidates:
        if name.lower() in families:
            return name
    return candidates[-1]


def font_ui(size: int = 11, bold: bool = False) -> QFont:
    f = QFont(_first_available(_FONT_UI_PREFERRED), size)
    f.setBold(bold)
    return f


def font_display(size: int = 14, bold: bool = True) -> QFont:
    f = QFont(_first_available(_FONT_DISPLAY_PREFERRED), size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
    return f


def font_mono(size: int = 10) -> QFont:
    return QFont(_first_available(_FONT_MONO_PREFERRED), size)


def font_caps(size: int = 10, bold: bool = True) -> QFont:
    """Estilo 'caps' del CSS — se simula con uppercase + letter-spacing en runtime."""
    f = font_ui(size, bold=bold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
    return f


# ---------------------------------------------------------------------------
# Helpers QColor
# ---------------------------------------------------------------------------

def color(hex_str: str, alpha: float = 1.0) -> QColor:
    """Convierte un hex a QColor con alpha 0-1 (default 1)."""
    c = QColor(hex_str)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def variant(name: str) -> dict:
    """Devuelve la config del variant 'equipar' / 'mejorar' / 'reserva' / 'descartar' / 'lategame'."""
    return VARIANTS.get(name, VARIANTS["reserva"])

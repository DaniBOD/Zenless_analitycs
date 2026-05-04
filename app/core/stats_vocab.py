"""
Hito 2.0.2 — Vocabulario canónico de stats (RF-04 §7.2.1).
Fuente de verdad para nombres de stats en toda la app.
Aliases extraídos del audit 2026-05-04 (audit/inventory_discs_audit_20260504.md).
"""

# ---------------------------------------------------------------------------
# Canon substats (10 válidos en ZZZ)
# ---------------------------------------------------------------------------
CANONICAL_SUBSTATS: frozenset[str] = frozenset({
    "HP", "HP%",
    "ATK", "ATK%",
    "DEF", "DEF%",
    "Prob. Crítica",
    "Daño Crítico",
    "Perforación",
    "Maestría de Anomalía",
})

# ---------------------------------------------------------------------------
# Canon mains por slot (RF-04 §7.2.1)
# ---------------------------------------------------------------------------
CANONICAL_MAINS_FIXED: dict[int, str] = {1: "HP", 2: "ATK", 3: "DEF"}

CANONICAL_MAINS_VARIABLE: dict[int, frozenset[str]] = {
    4: frozenset({
        "Prob. Crítica", "Daño Crítico", "Maestría de Anomalía",
        "HP%", "ATK%", "DEF%", "Tasa de Perforación",
    }),
    5: frozenset({
        "Bono Daño Físico", "Bono Daño Fuego", "Bono Daño Hielo",
        "Bono Daño Eléctrico", "Bono Daño Éter",
        "HP%", "ATK%", "DEF%", "Tasa de Perforación",
    }),
    6: frozenset({
        "HP%", "ATK%", "DEF%",
        "Maestría de Anomalía",
        "Impacto",
        "Recarga de Energía",
    }),
}

ALL_CANONICAL: frozenset[str] = (
    CANONICAL_SUBSTATS
    | frozenset(CANONICAL_MAINS_FIXED.values())
    | frozenset().union(*CANONICAL_MAINS_VARIABLE.values())
)

# ---------------------------------------------------------------------------
# Mapa alias → canónico
# Origen: audit inventory_discs_audit_20260504.md
# Fuentes combinadas: OCR errors, variantes español juego, typos de transcripción
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # HP / HP%
    "PV":               "HP",
    "Pv":               "HP",
    "Hp":               "HP",
    "pv":               "HP",
    "PV%":              "HP%",
    "PV %":             "HP%",
    "pv%":              "HP%",

    # ATK / ATK%
    "Ataque":           "ATK",
    "ataque":           "ATK",
    "Atk":              "ATK",
    "ATK":              "ATK",
    "Ataque%":          "ATK%",
    "Ataque %":         "ATK%",
    "ataque%":          "ATK%",
    "ATK %":            "ATK%",

    # DEF / DEF%
    "Defensa":          "DEF",
    "defensa":          "DEF",
    "Def":              "DEF",
    "Defensa%":         "DEF%",
    "Defensa %":        "DEF%",
    "DEF %":            "DEF%",

    # Prob. Crítica
    "Prob Crítico":     "Prob. Crítica",
    "Prob Crítica":     "Prob. Crítica",
    "Prob. Crítico":    "Prob. Crítica",
    "Probabilidad de Crítico": "Prob. Crítica",
    "Probabilidad Crítica":    "Prob. Crítica",
    "CRIT Rate":        "Prob. Crítica",
    "CR":               "Prob. Crítica",

    # Daño Crítico
    "Daño Crítico ":    "Daño Crítico",
    "Crit DMG":         "Daño Crítico",
    "CD":               "Daño Crítico",

    # Maestría de Anomalía
    "Maestría Anomalía":       "Maestría de Anomalía",
    "Maestría Anom":           "Maestría de Anomalía",
    "Anom":                    "Maestría de Anomalía",
    "Tasa Anomalía":           "Maestría de Anomalía",  # OCR error frecuente
    "Tasa de Anomalía":        "Maestría de Anomalía",  # OCR error frecuente
    "Tasa Anomalía 30%":       "Maestría de Anomalía",  # ids 54, 185

    # Perforación
    "Pen":              "Perforación",

    # Recarga de Energía (main slot 6)
    "ER":                      "Recarga de Energía",
    "Rec Energía":             "Recarga de Energía",
    "Recuperación Energía":    "Recarga de Energía",
    "Recuperación de Energía": "Recarga de Energía",

    # Impacto (main slot 6)
    "Impact":           "Impacto",
    "Impacto (%)":      "Impacto",

    # Tasa de Perforación (main slots 4, 5)
    "Tasa Perforación": "Tasa de Perforación",
    "Pen Ratio":        "Tasa de Perforación",

    # Bono Daño — variantes nombre elemento en español del juego
    "Bono Daño Glacial":    "Bono Daño Hielo",
    "Bono Daño Ígneo":      "Bono Daño Fuego",
    "Bono Daño Etéreo":     "Bono Daño Éter",
    "Bono Daño Físico":     "Bono Daño Físico",   # ya canónico, sin alias
}


def normalize_stat_name(raw: str | None) -> str | None:
    """Devuelve el nombre canónico del stat, o None si es completamente desconocido."""
    if raw is None:
        return None
    s = raw.strip()
    if s in ALL_CANONICAL:
        return s
    canon = ALIASES.get(s)
    if canon is not None:
        return canon
    # Segundo intento: normalizar espacios y mayúsculas
    s_normalized = " ".join(s.split())
    if s_normalized != s:
        if s_normalized in ALL_CANONICAL:
            return s_normalized
        canon = ALIASES.get(s_normalized)
        if canon is not None:
            return canon
    return None


def parse_value(raw: str | float | int | None) -> tuple[float, str] | None:
    """
    Convierte un valor de stat a (float, unidad).
    '7.2%' → (7.2, '%')
    38     → (38.0, 'flat')
    '38'   → (38.0, 'flat')
    None   → None
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw), "flat"
    s = str(raw).strip().replace(" ", "")
    if s.endswith("%"):
        try:
            return float(s[:-1]), "%"
        except ValueError:
            return None
    try:
        return float(s), "flat"
    except ValueError:
        return None


def is_valid_main_for_slot(slot: int, stat: str | None) -> bool:
    """Valida que un main_stat (ya canónico) sea válido para el slot dado."""
    if stat is None:
        return False
    canon = normalize_stat_name(stat)
    if canon is None:
        return False
    if slot in CANONICAL_MAINS_FIXED:
        return canon == CANONICAL_MAINS_FIXED[slot]
    valid = CANONICAL_MAINS_VARIABLE.get(slot, frozenset())
    return canon in valid

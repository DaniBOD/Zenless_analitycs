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
        "Bono Daño Eléctrico", "Bono Daño Éter", "Bono Daño Viento",
        # NO falta "Bono Daño Lumen": ese main NO EXISTE en el juego.
        # Confirmado in-game por DaniBOD el 2026-07-29 (patch v3.1). Lumen es el
        # único elemento sin bono de daño elemental en slot 5, así que un agente
        # Lumen (Remielle Dan) solo puede llevar acá HP%/ATK%/DEF%/Perforación.
        # Está fijado como contrato en test_stats_vocab.py — no lo agregues
        # "para completar la lista": si algún día ZZZ lo suma, hace falta una
        # captura para saber el rótulo (el de Viento es "Bono de daño aéreo").
        "HP%", "ATK%", "DEF%", "Tasa de Perforación",
    }),
    6: frozenset({
        "HP%", "ATK%", "DEF%",
        # Slot VI lleva la variante PORCENTUAL del stat de anomalía: "Tasa de
        # Anomalía" (Anomaly Mastery %), NO la flat "Maestría de Anomalía"
        # (esa es main de slot IV + substat). Corregido 2026-06-02 contra
        # capturas reales (slot 6 main = "Tasa de Anomalía 30 %") tras detectar
        # que el modelo viejo las conflaba. Ver audit/correccion_tasa_anomalia_*.
        "Tasa de Anomalía",
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
    "Dafo Crítico":     "Daño Crítico",   # OCR: ñ→f (patrón recurrente)
    "Crit DMG":         "Daño Crítico",
    "CD":               "Daño Crítico",

    # Maestría de Anomalía (Anomaly Mastery, FLAT — substat + main slot IV)
    "Maestría Anomalía":       "Maestría de Anomalía",
    "Maestría Anom":           "Maestría de Anomalía",
    "Anom":                    "Maestría de Anomalía",

    # Tasa de Anomalía (Anomaly Mastery %, PORCENTUAL — main slot VI + bonus set)
    # NO es lo mismo que "Maestría de Anomalía": son dos stats distintas (una
    # flat, otra %). El modelo viejo las conflaba como error de OCR; corregido
    # 2026-06-02 contra capturas reales. Ver audit/correccion_tasa_anomalia_*.
    "Tasa Anomalía":           "Tasa de Anomalía",
    "Tasa Anom":               "Tasa de Anomalía",

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

    # Bono Daño Viento (Wind DMG) — elemento nuevo del roster (Velina, v2.7+).
    # El cliente ES rotula el main de Viento como "Bono de daño aéreo"; el
    # canónico interno sigue la convención "Bono Daño <elemento>". El OCR lo
    # captura pegado ("Bonode danoaéreo", id=362). Ambas variantes comparten
    # clave normalizada → un solo destino. Confirmado contra inventory_discs.
    "Bono de daño aéreo":   "Bono Daño Viento",
    "Bonode danoaéreo":     "Bono Daño Viento",
}


import re as _re
import unicodedata as _ud
import difflib as _difflib


def _norm_key(s: str) -> str:
    """
    Clave de matching robusta: sin acentos, minúscula, sin espacios. Hace que
    el OCR (que suele perder tildes y alterar mayúsculas) matchee igual:
      'Daño Crítico' == 'Dano Critico' == 'dano critico'  → 'danocritico'
      'PV %' == 'PV%'                                       → 'pv%'
    Preserva el '%' porque distingue stats (HP vs HP%).
    """
    s = "".join(
        c for c in _ud.normalize("NFD", s or "")
        if _ud.category(c) != "Mn"
    ).lower()
    return _re.sub(r"\s+", "", s)


# Lookup precompilado clave-normalizada → canónico, desde canónicos + aliases.
# Los canónicos se agregan primero; los aliases NO los pisan (un canónico nunca
# debe re-mapearse a otra cosa por un alias homónimo).
_NORM_LOOKUP: dict[str, str] = {}
for _canon in ALL_CANONICAL:
    _NORM_LOOKUP.setdefault(_norm_key(_canon), _canon)
for _alias, _canon in ALIASES.items():
    _NORM_LOOKUP.setdefault(_norm_key(_alias), _canon)

_NORM_KEYS: list[str] = list(_NORM_LOOKUP.keys())

# Umbral del fallback difuso. Calibrado (2026-06-06) para abarcar los mangles de
# la 'ñ' del OCR ('Daño'→'Dao'/'Daio'/'Dauo'/'Danio'/'Dafo', ratio ≥ 0.87) y
# excluir la colisión peligrosa 'Maestría de Anomalía'↔'Tasa de Anomalía' (0.812).
_FUZZY_CUTOFF = 0.84
# Margen mínimo para desempatar entre dos canónicos DISTINTOS cercanos: si el
# segundo candidato (de otro canónico) está más cerca que esto, no se adivina.
_FUZZY_MARGIN = 0.06


def _base(canon: str) -> str:
    """Quita el '%' final: ATK y ATK% comparten base (el parser desambigua por unidad)."""
    return canon[:-1] if canon.endswith("%") else canon


def normalize_stat_name(raw: str | None) -> str | None:
    """
    Devuelve el nombre canónico del stat, o None si es desconocido.

    Insensible a acentos, mayúsculas y espacios (robusto a OCR). Ver _norm_key.

    Fallback difuso: el OCR latino mangléa la 'ñ' de forma inconsistente
    ('Daño Crítico' → 'Dao'/'Daio'/'Dauo'/'Danio Critico') y los alias fijos no
    escalan a cada variante. Si la clave exacta falla, se busca el canónico más
    cercano con umbral alto; se ABSTIENE (None) si hay ambigüedad con otro
    canónico distinto (RNF-02: no adivinar). Las variantes X/X% no cuentan como
    ambiguas (misma base; el parser corrige el % por la unidad del valor).
    """
    if raw is None:
        return None
    key = _norm_key(raw)
    hit = _NORM_LOOKUP.get(key)
    if hit is not None:
        return hit
    matches = _difflib.get_close_matches(key, _NORM_KEYS, n=3, cutoff=_FUZZY_CUTOFF)
    if not matches:
        return None
    best = _NORM_LOOKUP[matches[0]]
    r_best = _difflib.SequenceMatcher(None, key, matches[0]).ratio()
    for m in matches[1:]:
        if _base(_NORM_LOOKUP[m]) != _base(best):
            r_m = _difflib.SequenceMatcher(None, key, m).ratio()
            if r_best - r_m < _FUZZY_MARGIN:
                return None  # ambiguo entre canónicos distintos → no adivinar
            break
    return best


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

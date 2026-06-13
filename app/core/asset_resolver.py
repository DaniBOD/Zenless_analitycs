"""
Asset resolver — mapea entidades del dominio (sets, agentes, armas) a rutas
de imagen en disco. Centraliza la lógica de normalización de nombres y
fallbacks para que la UI no tenga que conocer la convención de archivos.

Fuentes:
- Sets:    Documentacion/Interfaz/Set_Discos_Logo/Drive_Disc_<nombre_en_norm>_Icon.webp
- Agentes: Documentacion/Interfaz/splash_arts/<NombreEN>-{ico,extend}.webp
- Agentes (fallback): Pj_stats/<NombreNorm>.jpeg

Los nombres en la DB están en español. Algunos agentes tienen alias inglés
distinto al español (Sporos→Seed, Gatillo→Trigger, etc); se mantiene un dict
explícito de overrides.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SET_LOGOS_DIR    = REPO_ROOT / "Documentacion" / "Interfaz" / "Set_Discos_Logo"
SPLASH_ARTS_DIR  = REPO_ROOT / "Documentacion" / "Interfaz" / "splash_arts"
PJ_STATS_DIR     = REPO_ROOT / "Pj_stats"
ENGINES_DIR      = REPO_ROOT / "Documentacion" / "Interfaz" / "Engines_icons"
FACTIONS_DIR     = REPO_ROOT / "Documentacion" / "Interfaz" / "Facciones_Logos"


# ---------------------------------------------------------------------------
# Overrides — nombres irregulares que no siguen normalización mecánica
# ---------------------------------------------------------------------------

# DB nombre español → carpeta splash_arts (base sin sufijo -ico/-extend)
# Se aplica cuando el match directo no funciona.
_AGENT_SPLASH_OVERRIDES: dict[str, str] = {
    "Sporos":         "Seed",          # nombre EN del juego
    "Gatillo":        "Trigger",
    "Orfia y Magas":  "Orphie",
    "N.º 0: Anby": "Anby-Soldier-0",  # º = ordinal masculino (DB)
    "N.º 11":      "Soldier-11",
    "César":          "Caesar",
    "Astra Yao":      "Astra-yao",     # case lowercase del archivo
    "Cissia":         "cissia",        # archivo en lowercase con _
    "Billy Estelar":  "Billy-starlight",  # Billy Kid (v2.x); archivo EN. -extend usa "_"
                                          # → lo resuelve el fallback de separador.
}

# Algunos archivos cissia usan "_" en lugar de "-" como separador
_AGENT_SPLASH_SEPARATOR_OVERRIDES: dict[str, str] = {
    "cissia": "_",
}

# DB nombre español → archivo Pj_stats (base sin .jpeg)
_AGENT_PJ_STATS_OVERRIDES: dict[str, str] = {
    "César":          "Cesar",
    "Antón":          "Anton",
    "Lucía":          "Lucia",
    "N.º 0: Anby": "N0_Anby",
    "N.º 11":      "N11",
    "Astra Yao":      "Astra_Yao",
    "Ye Shunguang":   "Ye_Shunguang",
    "Pan Yinhu":      "Pan_Yinhu",
    "Orfia y Magas":  "Orfia_y_Magas",
    "Ju Fufu":        "Ju_Fufu",
    "Nangong Yu":     "Nangong_Yu",
    "Zhu Yuan":       "Zhu_Yuan",
}


# ---------------------------------------------------------------------------
# Normalización de strings (sin acentos, ASCII)
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Elimina acentos manteniendo el resto del string ASCII."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_for_pj_stats(name: str) -> str:
    """Convierte 'Astra Yao' → 'Astra_Yao', 'César' → 'Cesar', etc."""
    s = _strip_accents(name)
    s = s.replace(" ", "_")
    # Eliminar puntuación residual
    for ch in ".°:":
        s = s.replace(ch, "")
    return s


def _normalize_for_splash(name: str) -> str:
    """Convierte 'Astra Yao' → 'Astra-Yao', 'César' → 'Cesar', etc."""
    s = _strip_accents(name)
    s = s.replace(" ", "-")
    for ch in ".°:":
        s = s.replace(ch, "")
    return s


# Caracteres a URL-encode para nombres de set
_SET_NAME_REPLACEMENTS = [
    ("&", "%26"),
    ("'", "%27"),
    (" ", "_"),
]


def _set_filename_from_en(nombre_en: str) -> str:
    """Convierte 'Dawn's Bloom' → 'Drive_Disc_Dawn%27s_Bloom_Icon.webp'."""
    s = nombre_en
    for orig, repl in _SET_NAME_REPLACEMENTS:
        s = s.replace(orig, repl)
    return f"Drive_Disc_{s}_Icon.webp"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def set_logo_path(nombre_en: str | None) -> Path | None:
    """
    Devuelve la ruta del logo .webp del set, o None si no se encuentra.

    nombre_en : nombre INGLÉS canónico tal cual está en la columna
                disc_sets.nombre_en (ej. 'Dawn's Bloom', 'Branch & Blade Song').
                Si recibe español, devuelve None — usar set_logo_path_by_es().
    """
    if not nombre_en:
        return None
    filename = _set_filename_from_en(nombre_en)
    path = SET_LOGOS_DIR / filename
    if path.exists():
        return path
    return None


def set_logo_path_by_es(nombre_es: str | None, repo=None) -> Path | None:
    """
    Mismo que `set_logo_path` pero recibe el nombre en español. Requiere
    un DiscSetRepo (o None) para resolver es→en vía DB.
    """
    if not nombre_es:
        return None
    if repo is None:
        return None
    try:
        for s in repo.get_all():
            if s.nombre.lower().strip() == nombre_es.lower().strip():
                nombre_en = getattr(s, "nombre_en", None)
                if nombre_en:
                    return set_logo_path(nombre_en)
    except Exception:
        return None
    return None


@lru_cache(maxsize=128)
def agent_avatar_path(nombre: str | None, variant: str = "extend") -> Path | None:
    """
    Devuelve la ruta del avatar del agente, o None si no se encuentra.

    nombre  : nombre en español (tal como está en agents.nombre)
    variant : 'extend' (cuerpo entero ~400×x), 'ico' (cara redonda ~100×100),
              o 'pj_stats' (JPEG cuadrado ~512×512 del HoYoLAB profile).
    """
    if not nombre:
        return None

    if variant == "pj_stats":
        base = _AGENT_PJ_STATS_OVERRIDES.get(nombre) or _normalize_for_pj_stats(nombre)
        path = PJ_STATS_DIR / f"{base}.jpeg"
        return path if path.exists() else None

    # variant = extend / ico
    if variant not in ("extend", "ico"):
        return None

    base = _AGENT_SPLASH_OVERRIDES.get(nombre) or _normalize_for_splash(nombre)
    separator = _AGENT_SPLASH_SEPARATOR_OVERRIDES.get(base, "-")
    path = SPLASH_ARTS_DIR / f"{base}{separator}{variant}.webp"
    if path.exists():
        return path

    # Fallback: probar la otra convención
    other_sep = "-" if separator == "_" else "_"
    path = SPLASH_ARTS_DIR / f"{base}{other_sep}{variant}.webp"
    if path.exists():
        return path

    # Último recurso: fallback al jpeg de Pj_stats
    return agent_avatar_path(nombre, variant="pj_stats")


# ---------------------------------------------------------------------------
# Self-check (útil para diagnosticar gaps de assets)
# ---------------------------------------------------------------------------

def audit_coverage(set_repo, agent_repo, variant: str = "extend") -> dict:
    """
    Devuelve un dict con conteos de hits/misses y la lista de entidades
    sin asset. Usar para validar antes de QA.
    """
    out = {"sets": {"hits": [], "misses": []}, "agents": {"hits": [], "misses": []}}
    try:
        for s in set_repo.get_all():
            path = set_logo_path(getattr(s, "nombre_en", None))
            (out["sets"]["hits"] if path else out["sets"]["misses"]).append(s.nombre)
    except Exception as exc:
        out["sets"]["error"] = str(exc)
    try:
        for a in agent_repo.get_all():
            path = agent_avatar_path(a.nombre, variant=variant)
            (out["agents"]["hits"] if path else out["agents"]["misses"]).append(a.nombre)
    except Exception as exc:
        out["agents"]["error"] = str(exc)
    return out

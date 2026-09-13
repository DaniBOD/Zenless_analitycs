"""
Asset resolver — mapea entidades del dominio (sets, agentes, armas) a rutas
de imagen en disco. Centraliza la lógica de normalización de nombres y
fallbacks para que la UI no tenga que conocer la convención de archivos.

Fuentes:
- Sets:    app/resources/ui_assets/Set_Discos_Logo/Drive_Disc_<nombre_en_norm>_Icon.webp
- Agentes: app/resources/ui_assets/splash_arts/<NombreEN>-{ico,extend}.webp
- Armas:   app/resources/ui_assets/Engines_icons/W-Engine_<NombreEN>.webp (o el slug ES)
- Agentes (fallback): Pj_stats/<NombreNorm>.jpeg

Los nombres en la DB están en español. Algunos agentes tienen alias inglés
distinto al español (Sporos→Seed, Gatillo→Trigger, etc); se mantiene un dict
explícito de overrides.
"""
from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# Los assets de interfaz viven DENTRO de `app/` (regla D1). Estuvieron en `Documentacion/Interfaz/`
# hasta el 2026-09-12, resueltos con un `parents[2]` que se escapa del paquete: andaba perfecto en
# desarrollo y sólo fallaba empaquetado, que es cuando ya no hay nadie mirando. Uno de esos
# directorios —`Set-Discos_Package_Logo`, el que alimenta al matcher de sets por badge— el spec de
# PyInstaller no lo copiaba, así que en el `.exe` el matcher arrancaba con 0 referencias EN SILENCIO.
#
# `app/resources/` se copia ENTERA al bundle, así que desde acá un recurso nuevo entra sin tocar el
# spec. Enumerar carpeta por carpeta ya falló tres veces (farm_nodes.toml, los baselines de badges,
# y este). Lo cuida `app/tests/unit/test_asset_paths_dentro_de_app.py`.
UI_ASSETS_DIR    = Path(__file__).resolve().parents[1] / "resources" / "ui_assets"

SET_LOGOS_DIR    = UI_ASSETS_DIR / "Set_Discos_Logo"
# Renders del disco (arte del tile de S2), 3 tiers S/A/B por set. Distinto de SET_LOGOS_DIR
# (emblemas redondos): estos alimentan el matcher de badges (SetBadgeMatcher), no el display.
SET_BADGES_DIR   = UI_ASSETS_DIR / "Set-Discos_Package_Logo"
SPLASH_ARTS_DIR  = UI_ASSETS_DIR / "splash_arts"
ENGINES_DIR      = UI_ASSETS_DIR / "Engines_icons"
FACTIONS_DIR     = UI_ASSETS_DIR / "Facciones_Logos"
# Fallback de avatares (46 JPEG, 6 MB). Único directorio de imágenes que sigue afuera de `app/`:
# no es de interfaz —son las capturas de las fichas de PJ— y el spec lo enumera explícitamente.
PJ_STATS_DIR     = REPO_ROOT / "Pj_stats"


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
    "Jane":           "Jane-Doe",      # DB usa el nombre corto; los archivos, el completo
    "Remielle Dan":   "Remielle",      # al revés que Jane: la DB usa el completo, el archivo el corto
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


def _set_badge_filename(nombre_en: str, tier: str) -> str:
    """Convierte ('Dawn's Bloom', 'S') → 'Drive_Disc_Dawn%27s_Bloom_S.webp'.

    Misma convención url-encode que `_set_filename_from_en`, pero con sufijo de tier
    (S/A/B) en vez de '_Icon' (son los renders del disco, no el emblema)."""
    s = nombre_en
    for orig, repl in _SET_NAME_REPLACEMENTS:
        s = s.replace(orig, repl)
    return f"Drive_Disc_{s}_{tier}.webp"


def set_package_badge_paths(nombre_en: str | None) -> list[Path]:
    """Rutas de los renders del disco (tiers S/A/B) del set, para el matcher de badges S2.

    Devuelve solo los tiers presentes en disco (lista vacía si ninguno). Ej.: 'Branch & Blade
    Song' no tiene package badge (endpoint caído al descargar) → []. `nombre_en` = nombre
    inglés canónico de disc_sets.nombre_en."""
    if not nombre_en:
        return []
    out: list[Path] = []
    for tier in ("S", "A", "B"):
        p = SET_BADGES_DIR / _set_badge_filename(nombre_en, tier)
        if p.exists():
            out.append(p)
    return out


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


def _norm_slug(s: str | None) -> str:
    """'Cilindro neumático de Bigger' → 'cilindro_neumatico_de_bigger'. Sin tildes, sin puntuación."""
    if not s:
        return ""
    t = _strip_accents(s).lower()
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "_", t).strip("_")


@lru_cache(maxsize=1)
def _engine_icon_index() -> tuple[dict[str, str], dict[str, str]]:
    """Índice del directorio de engines: (por nombre inglés, por slug español).

    Se lee una vez. Los `_pendiente_*.webp` quedan AFUERA a propósito: son archivos que nadie
    confirmó a qué arma corresponden, y servirlos sería afirmar un dato que no se verificó.
    """
    por_en: dict[str, str] = {}
    por_es: dict[str, str] = {}
    if not ENGINES_DIR.exists():
        return por_en, por_es
    for p in sorted(ENGINES_DIR.glob("*.webp")):
        if p.stem.startswith("_pendiente"):
            continue
        if p.stem.startswith("W-Engine_"):
            por_en[_norm_slug(p.stem[len("W-Engine_"):])] = p.name
        else:
            por_es[_norm_slug(p.stem)] = p.name
    return por_en, por_es


@lru_cache(maxsize=256)
def engine_icon_path(nombre: str | None, nombre_en: str | None = None) -> Path | None:
    """Ícono del W-Engine para mostrar, o None si no se puede saber cuál es.

    El directorio tiene dos convenciones conviviendo: los originales del wiki
    (`W-Engine_<NombreEN>.webp`) y slugs en español renombrados a mano. Se prueba **primero el
    inglés**, porque esos nombres vienen del wiki; el slug español lo puso una sesión pasada y su
    README tiene al menos un mapeo dudoso (`camara_acorazada` como *Bashful Demon*, cuando la DB
    dice *The Vault*).

    El tercer intento es por PREFIJO, y existe por la migración `_28`: el catálogo pasó a los
    nombres completos (`Cilindro neumático de Bigger`) y los archivos quedaron con el corto
    (`cilindro_neumatico`). El prefijo tiene que cortar en un borde de palabra — si no, el slug más
    corto del directorio (`cuter`, 5 letras) se queda con cualquier nombre que empiece igual.

    Si nada resuelve devuelve **None** y la vista dibuja un hueco. Adivinar el ícono de un arma es
    peor que no mostrarlo: hay una familia entera (`W-Engine_29_*`) cuya correspondencia con los
    nombres en español nadie verificó.
    """
    por_en, por_es = _engine_icon_index()

    ke = _norm_slug(nombre_en)
    if ke and ke in por_en:
        return ENGINES_DIR / por_en[ke]

    ks = _norm_slug(nombre)
    if not ks:
        return None
    if ks in por_es:
        return ENGINES_DIR / por_es[ks]

    candidatos = [v for fk, v in por_es.items() if ks.startswith(fk + "_")]
    if len(candidatos) == 1:
        return ENGINES_DIR / candidatos[0]
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

    if variant == "ico":
        # SIN fallback al jpeg de Pj_stats: son estilos incompatibles. El -ico es la cara
        # redonda limpia; el de Pj_stats es el cuadrado del perfil de HoYoLAB (con marco y
        # fondo). Sustituirlo silenciosamente rompía la estética del toast — pasó con Jane,
        # cuyo archivo es 'Jane-Doe-ico' y no matcheaba el nombre corto de la DB (QA
        # 2026-07-20). Mejor devolver None: el toast degrada a placeholder, que es honesto,
        # y el warning deja el asset faltante a la vista en vez de disimularlo.
        log.warning("Falta el ico limpio de '%s' (%s) — el toast usará placeholder.",
                    nombre, SPLASH_ARTS_DIR / f"{base}-ico.webp")
        return None
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
